from algopy import ARC4Contract, BoxMap, Global, GlobalState, Txn, UInt64, arc4, gtxn, itxn, op


class SubscriptionRecord(arc4.Struct):
    subscribed_at_round: arc4.UInt64
    expiry_round: arc4.UInt64
    total_months_paid: arc4.UInt64
    total_usdc_paid: arc4.UInt64
    last_payment_round: arc4.UInt64
    source_type: arc4.String


class SubscriptionManager(ARC4Contract):
    owner: GlobalState[arc4.Address]
    treasury_address: GlobalState[arc4.Address]
    escrow_app_id: GlobalState[UInt64]
    monthly_rate_micro_usdc: GlobalState[arc4.UInt64]
    rounds_per_month: GlobalState[arc4.UInt64]
    usdc_asset_id: GlobalState[arc4.UInt64]
    total_subscribers: GlobalState[arc4.UInt64]
    total_revenue_micro_usdc: GlobalState[arc4.UInt64]
    subscriptions: BoxMap[arc4.Address, SubscriptionRecord]

    def __init__(self) -> None:
        self.owner = GlobalState(arc4.Address)
        self.treasury_address = GlobalState(arc4.Address)
        self.escrow_app_id = GlobalState(UInt64)
        self.monthly_rate_micro_usdc = GlobalState(arc4.UInt64)
        self.rounds_per_month = GlobalState(arc4.UInt64)
        self.usdc_asset_id = GlobalState(arc4.UInt64)
        self.total_subscribers = GlobalState(arc4.UInt64)
        self.total_revenue_micro_usdc = GlobalState(arc4.UInt64)
        self.subscriptions = BoxMap(arc4.Address, SubscriptionRecord, key_prefix=b"sub_")

        self.owner.value = arc4.Address(Txn.sender)
        self.treasury_address.value = arc4.Address(Txn.sender)
        self.escrow_app_id.value = UInt64(0)
        self.monthly_rate_micro_usdc.value = arc4.UInt64(0)
        self.rounds_per_month.value = arc4.UInt64(0)
        self.usdc_asset_id.value = arc4.UInt64(0)
        self.total_subscribers.value = arc4.UInt64(0)
        self.total_revenue_micro_usdc.value = arc4.UInt64(0)

    @arc4.abimethod(create="require", allow_actions=["NoOp"])
    def create(self, monthly_rate: arc4.UInt64, rounds_per_month: arc4.UInt64, usdc_id: arc4.UInt64) -> None:
        monthly_rate_native = monthly_rate.native
        assert 1000000 <= monthly_rate_native <= 1000000000, (
            "monthly_rate must be between 1,000,000 and 1,000,000,000 microUSDC"
        )
        self.owner.value = arc4.Address(Txn.sender)
        self.treasury_address.value = arc4.Address(Txn.sender)
        self.monthly_rate_micro_usdc.value = monthly_rate
        self.rounds_per_month.value = rounds_per_month
        self.usdc_asset_id.value = usdc_id

        arc4.emit(
            "SubscriptionManagerCreated",
            arc4.Address(Txn.sender),
            monthly_rate,
            rounds_per_month,
            usdc_id,
        )

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_escrow_app(self, escrow_app_id: arc4.UInt64) -> None:
        assert Txn.sender == self.owner.value.native, "Only the contract owner can set the Escrow app ID"
        self.escrow_app_id.value = escrow_app_id.as_uint64()
        arc4.emit("SubscriptionEscrowAppSet", escrow_app_id)

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_monthly_rate(self, monthly_rate: arc4.UInt64) -> None:
        assert Txn.sender == self.owner.value.native, "Only the contract owner can update the monthly rate"
        monthly_rate_native = monthly_rate.native
        assert 1000000 <= monthly_rate_native <= 1000000000, (
            "monthly_rate must be between 1,000,000 and 1,000,000,000 microUSDC"
        )
        self.monthly_rate_micro_usdc.value = monthly_rate
        arc4.emit("SubscriptionMonthlyRateUpdated", monthly_rate)

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_rounds_per_month(self, rounds_per_month: arc4.UInt64) -> None:
        assert Txn.sender == self.owner.value.native, "Only the contract owner can update rounds_per_month"
        assert rounds_per_month.native > 0, "rounds_per_month must be greater than 0"
        self.rounds_per_month.value = rounds_per_month
        arc4.emit("SubscriptionRoundsPerMonthUpdated", rounds_per_month)

    @arc4.abimethod(allow_actions=["NoOp"])
    def opt_in_usdc(self) -> None:
        assert Txn.sender == self.owner.value.native, "Only the contract owner can opt the app into USDC"

        itxn.AssetTransfer(
            xfer_asset=self.usdc_asset_id.value.native,
            asset_receiver=Global.current_application_address,
            asset_amount=0,
            fee=UInt64(1000),
        ).submit()

    @arc4.abimethod(allow_actions=["NoOp"])
    def subscribe(self, months: arc4.UInt64) -> None:
        """Subscribe to insight access for multiple months with USDC payment.
        
        Atomicity Guarantee:
        - This method is called as part of an outer ATC group (index 1)
        - Index 0 of the group is an AssetTransfer transaction sending USDC to this contract
        - If this method reverts for ANY reason (validation, state write, etc.), the payment
          transaction at index 0 also reverts automatically
        - Either payment + subscription both succeed, or both are rolled back
        
        Conservation Check:
        - Validates that the payment amount meets the minimum required for the duration
        - Formula: payment_tx.asset_amount >= months * monthly_rate_micro_usdc
        - Overpayment is allowed; underpayment reverts the entire transaction
        
        Args:
            months: Number of months to subscribe (1-12)
        
        Raises:
            AssertionError if months not in range [1, 12]
            AssertionError if payment asset ID doesn't match configured USDC
            AssertionError if payment amount is insufficient
            AssertionError if payment is not sent to this contract
            AssertionError if payment sender doesn't match subscriber wallet
        """
        months_native = months.native
        assert 1 <= months_native <= 12, "months must be between 1 and 12"
        caller = arc4.Address(Txn.sender)

        payment_tx = gtxn.AssetTransferTransaction(0)
        required_payment = months_native * self.monthly_rate_micro_usdc.value.native

        # Conservation checks: validate payment details before any state updates
        assert payment_tx.xfer_asset.id == self.usdc_asset_id.value, "Payment must use the configured USDC asset"
        assert payment_tx.asset_amount >= required_payment, "Payment amount is below the required subscription price"
        assert payment_tx.asset_receiver == Global.current_application_address, (
            "Payment must be sent to this contract"
        )
        assert payment_tx.sender == Txn.sender, "Payment sender must match the subscribing wallet"

        current_round = Global.round
        payment_amount = payment_tx.asset_amount
        exists = self.subscriptions.maybe(caller)[1]

        if exists:
            current_expiry_round = self.subscriptions[caller].expiry_round.native
            if current_expiry_round > current_round:
                expiry_base = current_expiry_round
                subscribed_at_round = self.subscriptions[caller].subscribed_at_round
            else:
                expiry_base = current_round
                subscribed_at_round = arc4.UInt64(current_round)
            is_new_subscriber = False
            total_months_paid = self.subscriptions[caller].total_months_paid.native
            total_usdc_paid = self.subscriptions[caller].total_usdc_paid.native
        else:
            expiry_base = current_round
            subscribed_at_round = arc4.UInt64(current_round)
            is_new_subscriber = True
            total_months_paid = UInt64(0)
            total_usdc_paid = UInt64(0)

        extension_rounds_high, extension_rounds_low = op.mulw(months_native, self.rounds_per_month.value.native)
        assert extension_rounds_high == UInt64(0), "Subscription length overflow"

        expiry_high, new_expiry_round = op.addw(expiry_base, extension_rounds_low)
        assert expiry_high == UInt64(0), "Expiry round overflow"

        months_high, new_total_months_paid = op.addw(total_months_paid, months_native)
        assert months_high == UInt64(0), "Month counter overflow"

        revenue_high, new_total_usdc_paid = op.addw(total_usdc_paid, payment_amount)
        assert revenue_high == UInt64(0), "Subscriber payment counter overflow"

        if is_new_subscriber:
            subscribers_high, new_total_subscribers = op.addw(self.total_subscribers.value.native, 1)
            assert subscribers_high == UInt64(0), "Subscriber counter overflow"
            self.total_subscribers.value = arc4.UInt64(new_total_subscribers)

        revenue_total_high, new_total_revenue = op.addw(self.total_revenue_micro_usdc.value.native, payment_amount)
        assert revenue_total_high == UInt64(0), "Revenue counter overflow"
        self.total_revenue_micro_usdc.value = arc4.UInt64(new_total_revenue)

        self.subscriptions[caller] = SubscriptionRecord(
            subscribed_at_round=subscribed_at_round,
            expiry_round=arc4.UInt64(new_expiry_round),
            total_months_paid=arc4.UInt64(new_total_months_paid),
            total_usdc_paid=arc4.UInt64(new_total_usdc_paid),
            last_payment_round=arc4.UInt64(current_round),
            source_type=arc4.String("subscription"),
        )

        arc4.emit(
            "SubscriptionRecorded",
            caller,
            months,
            arc4.UInt64(new_expiry_round),
            arc4.UInt64(payment_amount),
        )

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def is_active(self, wallet: arc4.Address) -> arc4.Bool:
        exists = self.subscriptions.maybe(wallet)[1]
        if not exists:
            return arc4.Bool(False)
        return arc4.Bool(self.subscriptions[wallet].expiry_round.native > Global.round)

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def get_subscription(self, wallet: arc4.Address) -> SubscriptionRecord:
        exists = self.subscriptions.maybe(wallet)[1]
        assert exists, "No subscription record found for this wallet"
        return self.subscriptions[wallet]

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def get_expiry_round(self, wallet: arc4.Address) -> arc4.UInt64:
        exists = self.subscriptions.maybe(wallet)[1]
        assert exists, "No subscription record found for this wallet"
        return self.subscriptions[wallet].expiry_round

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def get_config(self) -> arc4.Tuple[arc4.UInt64, arc4.UInt64, arc4.UInt64, arc4.UInt64, arc4.UInt64]:
        return arc4.Tuple(
            (
                self.monthly_rate_micro_usdc.value,
                self.rounds_per_month.value,
                self.total_subscribers.value,
                self.total_revenue_micro_usdc.value,
                self.usdc_asset_id.value,
            )
        )

    @arc4.abimethod(allow_actions=["NoOp"])
    def release_for_subscriber(self, buyer: arc4.Address, listing_id: arc4.UInt64) -> arc4.Bool:
        assert Global.caller_application_id == self.escrow_app_id.value, (
            "release_for_subscriber can only be called by the Escrow contract"
        )

        assert self.is_active(buyer).native, "Subscription is not active or has expired"
        exists = self.subscriptions.maybe(buyer)[1]
        assert exists, "No subscription record found for this wallet"
        assert self.subscriptions[buyer].source_type == arc4.String("subscription"), "Invalid subscription source type"

        return arc4.Bool(True)

    @arc4.abimethod(allow_actions=["NoOp"])
    def withdraw_subscription_revenue(self) -> None:
        assert Txn.sender == self.owner.value.native, "Only the contract owner can withdraw subscription revenue"

        revenue = self.total_revenue_micro_usdc.value.native
        if revenue == 0:
            return

        itxn.AssetTransfer(
            xfer_asset=self.usdc_asset_id.value.native,
            asset_receiver=self.treasury_address.value.native,
            asset_amount=revenue,
            fee=UInt64(1000),
        ).submit()

        self.total_revenue_micro_usdc.value = arc4.UInt64(0)