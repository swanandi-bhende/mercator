from algopy import ARC4Contract, arc4, GlobalState, Txn, Global, op, UInt64, itxn


class FeeConfig(ARC4Contract):
    """
    FeeConfig contract manages USDC fee collection for the Mercator insight marketplace.
    
    Stores:
    - owner: deployer address (only wallet allowed to update fee parameters)
    - fee_rate_bps: fee rate in basis points (1 bps = 0.01%, range 0-1000)
    - treasury_address: wallet receiving all collected fees
    - total_fees_collected: running total of fees collected in microUSDC
    - usdc_asset_id: USDC ASA ID (TestNet=10458941, MainNet=31566704)
    
    Methods:
    - calculate_fee: pure read-only; returns fee with 1 microUSDC minimum for non-zero amounts
    - calculate_seller_payout: convenience method returning amount - fee
    - set_fee_rate: owner-only; validates rate <= 1000 (10% hard cap)
    - set_treasury: owner-only; updates treasury address
    - get_config: returns current fee_rate_bps, treasury_address, total_fees_collected, usdc_asset_id
    """

    # Global state
    owner: GlobalState[arc4.Address]
    fee_rate_bps: GlobalState[arc4.UInt64]
    treasury_address: GlobalState[arc4.Address]
    total_fees_collected: GlobalState[arc4.UInt64]
    usdc_asset_id: GlobalState[arc4.UInt64]
    escrow_app_id: GlobalState[UInt64]

    def __init__(self) -> None:
        """
        Initializes FeeConfig contract with owner-controlled parameters.
        
        Args:
            initial_fee_rate_bps: starting fee rate in basis points (0-1000)
            treasury: wallet address to receive all collected fees
            usdc_id: USDC ASA ID for the network (TestNet 10458941, MainNet 31566704)
        """
        self.owner = GlobalState(arc4.Address)
        self.fee_rate_bps = GlobalState(arc4.UInt64)
        self.treasury_address = GlobalState(arc4.Address)
        self.total_fees_collected = GlobalState(arc4.UInt64)
        self.usdc_asset_id = GlobalState(arc4.UInt64)
        self.escrow_app_id = GlobalState(UInt64)

        self.owner.value = arc4.Address(Txn.sender)
        self.fee_rate_bps.value = arc4.UInt64(250)
        self.treasury_address.value = arc4.Address(Txn.sender)
        self.usdc_asset_id.value = arc4.UInt64(0)
        self.total_fees_collected.value = arc4.UInt64(0)
        self.escrow_app_id.value = UInt64(0)

    @arc4.abimethod(create="require", allow_actions=["NoOp"])
    def create(
        self,
        initial_fee_rate_bps: arc4.UInt64,
        treasury: arc4.Address,
        usdc_id: arc4.UInt64,
    ) -> None:
        # Validate initial fee rate: must be between 0% and 10% (1000 bps)
        assert (
            initial_fee_rate_bps.as_uint64() <= 1000
        ), "Fee rate cannot exceed 10% (1000 basis points)"

        # Set deployer as owner
        self.owner.value = arc4.Address(Txn.sender)

        # Initialize global state
        self.fee_rate_bps.value = initial_fee_rate_bps
        self.treasury_address.value = treasury
        self.usdc_asset_id.value = usdc_id
        self.total_fees_collected.value = arc4.UInt64(0)
        self.escrow_app_id.value = UInt64(0)  # Set to 0 until Escrow is deployed

        # Emit creation event for indexers
        arc4.emit(
            "FeeConfigCreated",
            arc4.Address(Txn.sender),
            initial_fee_rate_bps,
            treasury,
            usdc_id,
        )

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def calculate_fee(self, amount_micro_usdc: arc4.UInt64) -> arc4.UInt64:
        """
        Calculates fee for a given USDC amount using integer arithmetic.
        
        Formula: fee = (amount * rate_bps) / 10000
        
        Applies 1 microUSDC minimum fee for any non-zero amount when rate > 0 to prevent
        zero-value USDC transfers which some Algorand nodes reject. Does NOT apply minimum
        when fee rate is legitimately 0%.
        
        Example (rate = 250 bps = 2.5%):
        - 500000 microUSDC → fee = 12500 microUSDC
        - 100000 microUSDC → fee = 2500 microUSDC
        - 39 microUSDC → fee = 1 microUSDC (minimum floor for dust)
        - 0 microUSDC → fee = 0 microUSDC
        
        Edge case (rate = 0 bps):
        - 100000 microUSDC → fee = 0 microUSDC (no minimum floor when rate is 0%)
        
        Args:
            amount_micro_usdc: amount in microUSDC (USDC has 6 decimals)
            
        Returns:
            fee in microUSDC with minimum 1 for non-zero amounts at non-zero rates
        """
        amount = amount_micro_usdc.as_uint64()
        rate = self.fee_rate_bps.value.as_uint64()

        if amount == 0:
            return arc4.UInt64(0)

        # Use wide math for audit-safe 128-bit multiplication and division.
        product_high, product_low = op.mulw(amount, rate)
        quotient_high, calculated_fee, remainder_high, remainder_low = op.divmodw(
            product_high, product_low, UInt64(0), UInt64(10000)
        )

        # Apply minimum fee floor ONLY when rate > 0:
        # Dust amounts at non-zero rates produce 0 fee due to integer division,
        # but zero-value USDC transfers are rejected by some nodes, so enforce minimum 1.
        # When rate is 0%, allow legitimate zero fee.
        if calculated_fee == 0 and rate > 0:
            return arc4.UInt64(1)

        return arc4.UInt64(calculated_fee)

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def calculate_seller_payout(self, amount_micro_usdc: arc4.UInt64) -> arc4.UInt64:
        """
        Convenience method: calculates seller payout as amount minus fee.
        
        This allows Escrow to fetch both fee and payout in one call rather than
        calculating the subtraction on the backend.
        
        Args:
            amount_micro_usdc: amount in microUSDC
            
        Returns:
            seller_payout = amount - fee
        """
        amount = amount_micro_usdc.as_uint64()
        fee = self.calculate_fee(amount_micro_usdc).as_uint64()
        return arc4.UInt64(amount - fee)

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_fee_rate(self, new_rate_bps: arc4.UInt64) -> None:
        """
        Owner-only method to update the fee rate.
        
        Validation:
        1. Caller must be owner (checked first, fails fast before state reads)
        2. New rate must be <= 1000 (10% hard cap; enforced on-chain)
        
        Emits event with old and new rates for indexers.
        
        Args:
            new_rate_bps: new fee rate in basis points (0-1000)
        """
        # Owner check FIRST: must fail immediately for unauthorized callers
        assert (
            Txn.sender == self.owner.value.native
        ), "Only the contract owner can update the fee rate"

        # Range check: hard cap at 10% (1000 bps) enforced on-chain
        assert (
            new_rate_bps.as_uint64() <= 1000
        ), "Fee rate cannot exceed 10% (1000 basis points)"

        old_rate = self.fee_rate_bps.value
        self.fee_rate_bps.value = new_rate_bps

        # Emit event for Operations dashboard / indexers
        arc4.emit("FeeRateUpdated", old_rate, new_rate_bps)

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_treasury(self, new_treasury: arc4.Address) -> None:
        """
        Owner-only method to update the treasury address.
        
        Validation:
        1. Caller must be owner (checked first)
        
        Emits event with old and new treasury addresses.
        
        Args:
            new_treasury: new treasury address
        """
        # Owner check FIRST
        assert (
            Txn.sender == self.owner.value.native
        ), "Only the contract owner can update the treasury address"

        old_treasury = self.treasury_address.value
        self.treasury_address.value = new_treasury

        # Emit event for indexers
        arc4.emit("TreasuryUpdated", old_treasury, new_treasury)

    @arc4.abimethod(allow_actions=["NoOp"])
    def set_escrow_app(self, escrow_app_id: UInt64) -> None:
        """
        Owner-only method to register the Escrow application ID.
        
        Called once after Escrow is deployed to establish the approved caller.
        Only the Escrow contract can then call record_fee_collected.
        
        Args:
            escrow_app_id: Application ID of the Escrow contract
        """
        # Owner check FIRST
        assert (
            Txn.sender == self.owner.value.native
        ), "Only the contract owner can set the Escrow app ID"

        self.escrow_app_id.value = escrow_app_id

        # Emit event for indexers
        arc4.emit("EscrowAppSet", escrow_app_id)

    @arc4.abimethod(allow_actions=["NoOp"])
    def record_fee_collected(self, fee_amount_micro_usdc: arc4.UInt64) -> None:
        """
        Records collected fee amount to the running total.
        
        Called by Escrow after successful fee transfer to update total_fees_collected.
        
        Caller Guard: Only the Escrow contract (identified by escrow_app_id) may call this.
        This prevents unauthorized callers from inflating the revenue counter.
        
        Implementation: Checks that either:
        1. Caller is the current application (self-call), OR
        2. Caller app ID matches registered escrow_app_id
        
        Args:
            fee_amount_micro_usdc: Fee amount in microUSDC to add to running total
        """
        # Caller verification: only Escrow contract can record fees
        escrow_id = self.escrow_app_id.value
        caller_app_id = Global.caller_application_id

        # Allow self-calls or calls from registered Escrow app
        is_self_call = Txn.sender == Global.current_application_address
        is_escrow_call = escrow_id != UInt64(0) and caller_app_id == escrow_id

        assert (
            is_self_call or is_escrow_call
        ), "Only the Escrow contract can record fees"

        # Add fee to running total using checked addw semantics.
        fee_amount = fee_amount_micro_usdc.as_uint64()
        current_total = self.total_fees_collected.value.as_uint64()
        carry, new_total = op.addw(current_total, fee_amount)
        assert carry == UInt64(0), "Fee accumulator overflow"

        self.total_fees_collected.value = arc4.UInt64(new_total)

        # Emit event with fee amount and new total for indexers
        arc4.emit("FeeCollected", fee_amount_micro_usdc, arc4.UInt64(new_total))

    @arc4.abimethod(readonly=True, allow_actions=["NoOp"])
    def get_config(
        self,
    ) -> arc4.Tuple[arc4.UInt64, arc4.Address, arc4.UInt64, arc4.UInt64]:
        """
        Returns current FeeConfig state for Operations dashboard.
        
        Called frequently (e.g., every 10 seconds) to display:
        - Current fee rate
        - Treasury address
        - Cumulative fees collected (platform revenue to date)
        - USDC asset ID (confirms network)
        
        Returns:
            Tuple of (fee_rate_bps, treasury_address, total_fees_collected, usdc_asset_id)
        """
        return arc4.Tuple(
            (
                self.fee_rate_bps.value,
                self.treasury_address.value,
                self.total_fees_collected.value,
                self.usdc_asset_id.value,
            )
        )
