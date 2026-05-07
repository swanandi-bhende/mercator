# Business Model

## Fee Enforcement

The 2.5% platform fee is enforced on-chain inside the Escrow contract. The fee is calculated by calling FeeConfig.calculate_fee() before any money moves. The seller payout and treasury fee are transferred in the same inner transaction group - if either transfer fails for any reason, both revert. This means the fee cannot be bypassed by interacting with the Escrow contract directly without going through the backend.

## Subscription Model

Mercator now supports recurring curator-insights subscriptions through SubscriptionManager. Buyers pay a monthly USDC rate into the contract, the contract tracks the active subscription window in rounds, and Escrow checks entitlement before delivering subscriber-gated content. Revenue accumulates in the contract until the owner withdraws it to the treasury address.

The first live TestNet subscription payment tx id will be recorded here after deployment and end-to-end confirmation. The exact tx id is intentionally left blank until a real on-chain run produces it.
