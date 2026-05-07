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
