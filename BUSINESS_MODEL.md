# Business Model

## Fee Enforcement

The 2.5% platform fee is enforced on-chain inside the Escrow contract. The fee is calculated by calling FeeConfig.calculate_fee() before any money moves. The seller payout and treasury fee are transferred in the same inner transaction group - if either transfer fails for any reason, both revert. This means the fee cannot be bypassed by interacting with the Escrow contract directly without going through the backend.
