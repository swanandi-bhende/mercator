# CONTRACTS

## AgentRegistry

Schema for AgentRegistry contract data model (implementation checklist):

- Per-agent Box record (`AgentRecord`):
  - `agent_name`: string, max 64 characters
  - `role`: string, one of "buyer", "curator", or "seller"
  - `registered_at_round`: UInt64 (Algorand round number at registration)
  - `active`: Bool (True on registration, False on deregistration)
  - `signed_manifest`: string (base64-encoded signature produced by `algosdk.util.sign_bytes`)
  - `total_transactions`: UInt64 (increments each time the agent successfully interacts with InsightListing or Escrow)

- Global state (contract-level):
  - `owner`: arc4.Address (deployer wallet; only this address may call `deregister`)
  - `total_registered`: arc4.UInt64 (count of currently active registered agents)
  - `registry_version`: arc4.UInt64 (start at 1; increment on upgrades)

- Box map configuration:
  - Box map keyed by `arc4.Address` (wallet address)
  - `key_prefix` MUST be set and stable (use `b"reg_"`) — changing it later invalidates existing keys
  - Remember Box MBR: contract account must fund additional ALGO for each Box created; Box reads on non-existent keys must be guarded by `.exists` checks

Notes / constraints:
- `signed_manifest` stored as base64 string on-chain; on-chain verification must decode to raw 64-byte signature bytes before calling `op.ed25519verify_bare`.
- All Box reads must check `.exists` first because reading a non-existent Box raises an error.
- Box key encoding must be consistent across all callers — use `arc4.Address` typed keys and the same `key_prefix`.

This CONTRACTS.md entry is the authoritative data-model reference for `AgentRegistry` and will be used as the implementation checklist.

## FeeConfig

Schema for FeeConfig contract (fee calculation and collection management):

### Fee Math and Edge Cases

The fee system operates on **basis points** where 1 basis point = 0.01%, so:
- 250 basis points = 2.5%
- Formula: `fee = (amount * rate_bps) / 10000` using integer arithmetic
- All values are in microUSDC (USDC has 6 decimals)

**Test cases (fee rate = 250 bps):**
1. Amount: 500000 microUSDC (0.50 USDC) → fee = (500000 * 250) / 10000 = 12500 microUSDC (0.0125 USDC), seller payout = 487500 microUSDC (0.4875 USDC)
2. Amount: 100000 microUSDC (0.10 USDC) → fee = (100000 * 250) / 10000 = 2500 microUSDC (0.0025 USDC), seller payout = 97500 microUSDC (0.0975 USDC)
3. Amount: 10000 microUSDC (0.01 USDC) → fee = (10000 * 250) / 10000 = 250 microUSDC (0.00025 USDC), seller payout = 9750 microUSDC (0.0075 USDC)
4. **Edge case: dust amount** 39 microUSDC at 250 bps → (39 * 250) / 10000 = 0 (integer division floors to zero)

**Minimum fee floor rule:** If calculated fee is zero and the fee rate is greater than 0%, the fee must be 1 microUSDC minimum. This prevents zero-value USDC transfers which some Algorand nodes reject. Dust amounts (≤ 39 microUSDC at 250 bps) produce a 1 microUSDC fee. When fee rate is legitimately 0%, the fee is 0 (no minimum floor applied).

### Data Model

- **owner**: arc4.Address — deployer address; only wallet allowed to update fee parameters
- **fee_rate_bps**: arc4.UInt64 — current fee rate in basis points (initial = 250, range 0–1000)
- **treasury_address**: arc4.Address — Algorand wallet receiving all collected fees
- **total_fees_collected**: arc4.UInt64 — running total of all fees collected (microUSDC); gives Operations dashboard "platform revenue to date"
- **usdc_asset_id**: arc4.UInt64 — USDC ASA ID (TestNet = 10458941, MainNet = 31566704); stored to allow network-agnostic deployment

### Methods

- **`create(initial_fee_rate_bps, treasury, usdc_id)`**: Create-time initializer; validates rate ≤ 1000 (10% hard cap enforced on-chain)
- **`calculate_fee(amount_micro_usdc) → UInt64`**: Pure read-only method; returns fee (with 1 microUSDC minimum for non-zero amounts)
- **`calculate_seller_payout(amount_micro_usdc) → UInt64`**: Read-only method; returns amount - fee
- **`set_fee_rate(new_rate_bps)`**: Owner-only; updates fee_rate_bps with range check; emits event
- **`set_treasury(new_treasury)`**: Owner-only; updates treasury_address; emits event
- **`record_fee_collected(fee_amount_micro_usdc)`**: Called by Escrow contract after payment split; increments total_fees_collected; validates caller is registered Escrow app
- **`get_config() → (fee_rate_bps, treasury_address, total_fees_collected, usdc_asset_id)`**: Read-only; returns current configuration for Operations dashboard

## SubscriptionManager

Subscription timing and pricing are round-based, not wall-clock based.

### Algorand round timing

- `Global.round` inside a contract call returns the confirmation round for the transaction currently being processed, not the round when the transaction was first built.
- Subscription expiry must always be calculated from the actual confirmation round.
- Algorand rounds are a time proxy, so the same round count represents different wall-clock durations on MainNet and TestNet.

### Network-specific month constants

- `MAINNET_ROUNDS_PER_MONTH = 172800`
- `TESTNET_ROUNDS_PER_MONTH = 17280`
- The contract does not hardcode either value at runtime; it accepts `rounds_per_month` during deployment so the same code can be used on MainNet or TestNet demo deployments.

### Data model

- `owner`: arc4.Address — deployer wallet; only the owner may update configuration or register the Escrow app ID.
- `escrow_app_id`: arc4.UInt64 — Escrow application ID, set after Escrow deployment.
- `monthly_rate_micro_usdc`: arc4.UInt64 — current monthly price in microUSDC; default deployment value is 50,000,000.
- `rounds_per_month`: arc4.UInt64 — deployment-time month length in rounds.
- `usdc_asset_id`: arc4.UInt64 — USDC ASA ID for the target network.
- `total_subscribers`: arc4.UInt64 — count of genuinely new subscribers only.
- `total_revenue_micro_usdc`: arc4.UInt64 — running total of all microUSDC collected from subscriptions and renewals.
- `subscriptions`: BoxMap keyed by arc4.Address with key prefix `b"sub_"`.

**SubscriptionRecord struct:**
- `subscribed_at_round`: arc4.UInt64 — round the subscription was first created for the current active cycle.
- `expiry_round`: arc4.UInt64 — round after which `is_active` returns false.
- `total_months_paid`: arc4.UInt64 — cumulative months paid by this subscriber.
- `total_usdc_paid`: arc4.UInt64 — cumulative microUSDC paid by this subscriber.
- `last_payment_round`: arc4.UInt64 — confirmation round of the most recent payment.
- `source_type`: arc4.String — must always be exactly `"subscription"`.

### Pricing math

- USDC has 6 decimals.
- 50 USDC = 50,000,000 microUSDC.
- Formula: `price_micro_usdc = months * MONTHLY_RATE_MICRO_USDC`
- `MONTHLY_RATE_MICRO_USDC` is stored in global state so the owner can change pricing without redeploying.

Example prices:
- 1 month = 50,000,000 microUSDC
- 2 months = 100,000,000 microUSDC
- 12 months = 600,000,000 microUSDC

### Expiry formulas

- New subscriber: `expiry_round = Global.round + (months * ROUNDS_PER_MONTH)`
- Active renewal: `new_expiry_round = current_expiry_round + (months * ROUNDS_PER_MONTH)`
- Lapsed renewal: `new_expiry_round = Global.round + (months * ROUNDS_PER_MONTH)`

### Payment-in-group verification

- `subscribe()` receives USDC as an `AssetTransfer` in the same atomic group as the app call.
- The USDC transfer is at group index 0 and the contract call is at group index 1.
- The contract verifies the payment by inspecting `gtxn.AssetTransferTransaction(0)` and checking the asset id, amount, receiver, and sender.
- This is the subscription payment path; the contract does not rely on inner transactions for the incoming USDC.

### Methods

- `__init__(monthly_rate, rounds_per_month, usdc_id)`: validates the monthly rate is between 1,000,000 and 1,000,000,000 microUSDC, sets all global state, and emits a creation event.
- `subscribe(months)`: validates months are between 1 and 12, verifies the grouped USDC payment, and writes or renews the caller’s subscription box record.
- `is_active(wallet) → Bool`: fast read-only check used by Escrow before free purchases.
- `get_subscription(wallet) → SubscriptionRecord`: returns the full subscription record.
- `get_expiry_round(wallet) → UInt64`: returns only the expiry round for frontend display.
- `get_config() → (monthly_rate_micro_usdc, rounds_per_month, total_subscribers, total_revenue_micro_usdc, usdc_asset_id)`: returns the current pricing and usage counters.

### Operational notes

- `total_subscribers` increases only when a brand-new wallet subscribes.
- Renewals never increment `total_subscribers`.
- Active renewals stack on top of the existing expiry.
- Lapsed renewals start fresh from the confirmation round.
- `source_type` must always be `"subscription"` so Escrow can reject manually crafted Box entries.
- `is_active` treats a subscription expiring on the current round as expired because the comparison is strictly greater-than.

**InsightListing State Machine**

- **States:** `ACTIVE`, `SOLD`, `EXPIRED`.
- **Overview:** Each listing moves through a single lifecycle: created (`NONE` → `ACTIVE`), possibly purchased (`ACTIVE` → `SOLD`), or expired (`ACTIVE` → `EXPIRED`). A sold listing never expires (no `SOLD` → `EXPIRED` transition). An expired listing cannot be reactivated.

Transitions (each transition lists: Trigger, Guard(s), Side effects, and explicit revert messages):

- **Transition 1 — Creation: `NONE` → `ACTIVE`**
  - Trigger: `create_listing()` app call.
  - Guards:
    - Caller must be registered in `AgentRegistry` — revert message: "Unregistered agent — call AgentRegistry.register() first".
    - `price_micro_usdc` must be > 0 — revert message: "Price must be greater than zero".
    - `ipfs_cid` must be non-empty (CIDv0 length check) — revert message: "IPFS CID must be at least 46 characters".
    - `source_type` must be either "curator_agent" or "human" — revert message: "source_type must be curator_agent or human".
  - Side effects:
    - `expiry_round = Global.round() + expiry_rounds` where `expiry_rounds` is `custom_expiry_rounds` if >0 else `default_expiry_rounds`.
    - `listing_count` / `total_active_listings` increments.
    - Emit `ListingCreated(listing_id, seller_wallet, expiry_round, source_type)` log.
    - Return the `listing_id` to the caller.

- **Transition 2 — Purchase: `ACTIVE` → `SOLD`**
  - Trigger: `mark_sold(listing_id, buyer)` invoked by Escrow.
  - Guards (checked in exact order):
    - Caller must be the registered `Escrow` app: revert message: "Only Escrow can mark a listing as sold".
    - The listing Box must exist: revert message: "Listing not found".
    - Listing must be in `ACTIVE` state: revert message: "Listing not in ACTIVE state".
    - Listing must not be expired: `Global.round() <= expiry_round` — revert message: "Listing has expired — purchase window closed".
  - Side effects:
    - `buyer_wallet = buyer`.
    - `sold_at_round = Global.round()`.
    - `state = SOLD`.
    - `total_active_listings` decremented, `total_sold_listings` incremented.
    - Emit `ListingSold(listing_id, buyer_wallet, sold_at_round)`.
    - Call `Reputation.record_purchase(seller_wallet, buyer_wallet, listing_id)` (inner-call from Escrow/mark_sold flow).

- **Transition 2b — Subscriber Purchase (subscription listings): `ACTIVE` → `ACTIVE`**
  - Trigger: `mark_sold_to_subscriber(listing_id, buyer)` invoked by Escrow for subscription purchases.
  - Guards:
    - Listing Box must exist: revert message: "Listing not found".
    - Listing must be in `ACTIVE` state: revert message: "Listing not in ACTIVE state".
    - Listing must not be expired: revert message: "Listing has expired — purchase window closed".
  - Side effects:
    - Increment `subscription_purchase_count` on the ListingRecord.
    - Append buyer address to `subscriber_purchases` storage (or Box array keyed by listing_id).
    - Emit `ListingSubscriberPurchase(listing_id, buyer_wallet, Global.round())`.
    - Do NOT change listing `state` or global active/sold counters.

- **Transition 3 — Expiry: `ACTIVE` → `EXPIRED`**
  - Trigger: `check_and_expire(listing_id)` (any caller may invoke).
  - Guards / Behavior:
    - If Box does not exist: revert message: "Listing not found".
    - If state != `ACTIVE`: no-op and return silently (do not revert) — calling this on `SOLD` or `EXPIRED` is a harmless noop.
    - Require `Global.round() > expiry_round` to perform expiry; otherwise no-op.
  - Side effects:
    - `state = EXPIRED`.
    - `expired_at_round = Global.round()`.
    - Decrement `total_active_listings`, increment `total_expired_listings`.
    - Emit `ListingExpired(listing_id, expired_at_round)`.

Guard failure messages (exact strings shown here are used for on-chain revert logs and frontend error display):

- "Listing has expired — purchase window closed"
- "Listing already sold to {buyer}"
- "Listing not in ACTIVE state"

Notes and implications:

- `Global.round()` inside a contract method reflects the confirmation round of the transaction being processed, not the round the transaction was submitted. Frontend timers MUST add a safety buffer (recommend +10 rounds) to account for TestNet congestion.
- `Global.round()` is available only in contract code; off-chain tests must use the Algod client (`algod.Status()["last-round"]`) when constructing fixtures.
- Define state string constants at module level and use constants (not inline string literals) in equality checks to get compile-time safety against typos.

## Escrow

Schema for Escrow contract (payment settlement and buyer access unlock):

### Purpose

Records post-payment buyer access after x402 USDC payment settlement. Atomically splits payment between seller and platform treasury with guaranteed fee enforcement. Acts as immutable audit log: buyer can only fetch content after payment confirmed and Escrow release called.

### Payment Flow Integration

1. Buyer pays 0.50 USDC (500000 microUSDC) via x402 atomic payment group
2. `post_payment_flow.py` waits for indexer confirmation
3. Backend calls `Escrow.release_after_payment()` with seller, amount, and treasury details
4. Escrow calls `FeeConfig.calculate_fee()` to determine split (fee = 12500, payout = 487500)
5. Escrow submits two atomic inner `itxn.AssetTransfer` transactions:
   - Transfer 487500 microUSDC (seller payout) to seller wallet
   - Transfer 12500 microUSDC (fee) to treasury wallet
6. If either inner transaction fails, both revert (atomic group guarantee)
7. Escrow calls `FeeConfig.record_fee_collected()` to update revenue counter
8. Escrow stores `UnlockRecord` for audit trail

### Data Model

- **registry_app_id**: GlobalState[UInt64] — reference to AgentRegistry (optional validation)
- **fee_config_app_id**: GlobalState[UInt64] — reference to FeeConfig contract for fee calculation
- **insight_listing_app_id**: GlobalState[UInt64] — reference to InsightListing contract for purchase tracking
- **unlocked_listings**: BoxMap[listing_id, UnlockRecord] — maps listing ID to unlock proof

**UnlockRecord struct:**
- **buyer**: arc4.Address — wallet address of the buyer
- **seller**: arc4.Address — wallet address of the insight creator  
- **unlocked**: arc4.Bool — always True on creation (allows future extensions)
- **payment_amount_micro_usdc**: arc4.UInt64 — original payment amount before fee split (audit trail)

### Methods

- **`create(fee_config_app_id, insight_listing_app_id, registry_app_id)`**: Create-time initializer for linked app IDs
- **`set_app_ids(fee_config_app_id, insight_listing_app_id, registry_app_id)`**: Owner-only updater for linked app IDs after redeploys
- **`release_after_payment(buyer, seller, listing_id, amount_micro_usdc, usdc_asset_id, treasury_address) → Bool`**: 
  - Validates caller is buyer (prevents spoofing)
  - Calls FeeConfig.calculate_fee() for split amounts
  - Submits two atomic inner transfers (seller payout, treasury fee)
  - Records fee collection and unlock state
  - Stores UnlockRecord with payment audit trail
  - Returns True on success

### Fee Split Example

**Input:** 500000 microUSDC at 250 bps fee rate
- Call FeeConfig.calculate_fee(500000) → returns 12500
- Calculate payout: 500000 - 12500 = 487500
- Submit inner transfer: 487500 to seller
- Submit inner transfer: 12500 to treasury
- Invariant check: 12500 + 487500 == 500000 ✓
- Both transfers atomic (both succeed or both revert)

### Transaction Fee Calculation

The outer transaction that calls `release_after_payment` must account for 4 inner transactions:
1. FeeConfig.calculate_fee() → 1 cross-contract call
2. USDC transfer to seller → 1 inner itxn.AssetTransfer
3. USDC transfer to treasury → 1 inner itxn.AssetTransfer  
4. FeeConfig.record_fee_collected() → 1 cross-contract call
5. Unlock state write in Escrow box storage

**Fee formula:** Outer fee = 1000 microALGO (base) + 1000 × (number of inner transactions)

For 4 inner transactions: **sp.fee = 5000 microALGO** (must be set explicitly, never use default 1000)

### Deployment Notes (TestNet)

- FeeConfig App ID: 761839101
- Escrow App ID (fee-aware build): 761839258
- InsightListing App ID: 758025190
- Treasury Address: M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM

## Reputation (Seller) — Design Decisions and Data Model

Important preface:
- Algorand Boxes store opaque byte blobs. Variable-length arrays inside a single Box are not appendable in place — you must read the full Box, deserialize, mutate the in-memory array, then reserialize and write the Box. This read-modify-write pattern makes unbounded arrays expensive in opcode budget and in Box size.
- To bound cost and keep opcode usage predictable, the on-chain purchase history stored per-seller will be capped at the most recent 20 purchases. Older entries are discarded using a sliding-window approach. This decision limits Box size and amortises the cost of writes while still providing useful recent-history to frontends.

Boxes & Opcode budget notes:
- The default single-call opcode budget is 700. When using pooled fees (inner transactions called from another app), the available budget scales with the number of transactions in the group. The `record_purchase` method is invoked as an inner transaction from `Escrow.release_after_payment`, so its budget is pooled with the outer group — design accordingly.
- Because exact opcode costs for `box_get`, `box_put`, `box_len`, and `ed25519verify_bare` can vary across AVM versions, implementations SHOULD consult the Algorand AVM opcode cost table before optimizing further. The cap of 20 entries is chosen to keep Box read/serialise/write operations bounded and predictable.

Data model (per-seller Box entry)
- `SellerRecord` (arc4.Struct):
  - `raw_score`: arc4.UInt64 — cumulative points assigned at purchase time (no decay applied)
  - `last_purchase_round`: arc4.UInt64 — round of the most recent completed purchase
  - `total_purchases`: arc4.UInt64 — all-time purchase counter (not limited by history cap)
  - `history_count`: arc4.UInt64 — number of valid entries in `purchase_history` (0..20)
  - `purchase_history`: StaticArray[PurchaseRecord, 20] — sliding window of most recent 20 purchases

`PurchaseRecord` (arc4.Struct):
- `buyer_address`: arc4.Address
- `listing_id`: arc4.UInt64
- `purchase_round`: arc4.UInt64

Global state (contract-level)
- `owner`: GlobalState(arc4.Address)
- `escrow_app_id`: GlobalState(arc4.UInt64) — only this app may call `record_purchase`
- `points_per_purchase`: GlobalState(arc4.UInt64) — default 5 (must be 1..50)
- `decay_threshold_rounds`: GlobalState(arc4.UInt64) — default 30000 (no decay before this)
- `decay_rate_rounds`: GlobalState(arc4.UInt64) — default 10000 (1 point per 10000 rounds)
- `min_score`: GlobalState(arc4.UInt64) — floor for effective score (default 0)
- `total_sellers_tracked`: GlobalState(arc4.UInt64) — incremented on first-box creation

Decisions & simplifications
- Tracking unique buyers on-chain is expensive (would require a per-seller set). To keep storage/opcode costs reasonable, the contract records `total_purchases` as a transaction count rather than unique buyers. This is documented and accepted as a simplification for on-chain storage limits.
- Purchase history is a fixed-size sliding window (20 most recent entries). `history_count` indicates how many entries are valid (0..20). When `history_count` == 20, new entries shift the array left and insert the new record at index 19.

Decay formula (precise)
- Parameters: `decay_threshold_rounds = 30000`, `decay_rate_rounds = 10000` (defaults shown, configurable by owner)
- Compute `rounds_since_purchase = Global.round() - last_purchase_round`.
- If `rounds_since_purchase <= decay_threshold_rounds` → `decay_points = 0`.
- Else `decay_points = (rounds_since_purchase - decay_threshold_rounds) // decay_rate_rounds` using integer division.
- `effective_score = max(min_score, raw_score - decay_points)` (floor at `min_score` to avoid underflow).

Concrete examples (for CONTRACTS.md):
- Example A: `raw_score = 5`, `rounds_since_purchase = 70000` → `decay_points = (70000 - 30000) // 10000 = 4` → `effective_score = max(0, 5 - 4) = 1`.
- Example B: `raw_score = 3`, `rounds_since_purchase = 100000` → `decay_points = (100000 - 30000) // 10000 = 7` → `effective_score = max(0, 3 - 7) = 0`.
- Edge-case: If `Global.round() < last_purchase_round` (possible in testing environments where ledger state was reset), treat as no-decay and return `raw_score` unchanged; this avoids unsigned underflow on subtraction.

API surface (methods to implement in contract)
- `record_purchase(seller, buyer, listing_id)`: inner-call only (guarded by `Global.caller_app_id == escrow_app_id`). Creates or updates `SellerRecord`, increments `raw_score` by `points_per_purchase`, updates `last_purchase_round`, updates `total_purchases`, and updates sliding-window `purchase_history`. Emits a concise log with seller, new raw score, and total purchases.
- `get_score(seller) -> arc4.UInt64 (readonly)`: returns `effective_score` after applying decay formula; returns 0 if no Box exists.
- `get_full_record(seller) -> SellerRecord (readonly)`: returns full seller record including `purchase_history` for frontend display.
- `get_effective_score_with_breakdown(seller) -> (effective_score, raw_score, decay_points_applied, rounds_since_last_purchase, rounds_until_decay_starts) (readonly)`: returns breakdown used by frontend seller profile.

Operational note
- Because `record_purchase` runs as an inner transaction from `Escrow.release_after_payment`, gas/opcode budget must be considered. Keep Box read/serialise/write minimal and bounded by the 20-entry cap. If additional analytics are required (e.g., unique buyer counts), prefer off-chain indexing or secondary contracts with richer storage paid by operators.

