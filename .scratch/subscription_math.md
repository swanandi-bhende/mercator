# Subscription math scratch

## Network round constants
- MainNet: `MAINNET_ROUNDS_PER_MONTH = 172800`
- TestNet demo: `TESTNET_ROUNDS_PER_MONTH = 17280`
- Subscription contract accepts `rounds_per_month` at deployment time instead of hardcoding either value.

## Timing notes
- Algorand rounds are a time proxy, not a fixed wall-clock clock.
- A transaction sees the confirmation round during execution, so expiry must be calculated from the actual processing round.

## Pricing
- USDC has 6 decimals.
- 50 USDC = 50,000,000 microUSDC.
- Monthly rate default: 50,000,000 microUSDC.
- Price formula: `price_micro_usdc = months * MONTHLY_RATE_MICRO_USDC`.

## Example prices
- 1 month = 50,000,000 microUSDC
- 2 months = 100,000,000 microUSDC
- 12 months = 600,000,000 microUSDC

## Expiry formulas
- New subscriber: `expiry_round = Global.round + (months * rounds_per_month)`
- Active renewal: `new_expiry_round = current_expiry_round + (months * rounds_per_month)`
- Lapsed renewal: `new_expiry_round = Global.round + (months * rounds_per_month)`

## Record fields per subscriber
- subscriber_address key in BoxMap, not duplicated in the record
- subscribed_at_round
- expiry_round
- total_months_paid
- total_usdc_paid
- last_payment_round
- source_type = "subscription"

## Operational rule
- Existing active subscription stacks time on top of the current expiry.
- Existing lapsed subscription starts fresh from the actual confirmation round.
