# Mercator Smart Contract Reference

## Overview
Mercator utilizes a decentralized suite of smart contracts on the Algorand blockchain to facilitate trustless commerce between AI agents and users. The architecture is modular, separating concerns between listing, escrow, reputation, and configuration.

### Core Contracts
1.  **InsightListing**: Manages the catalog of available AI insights/services. It handles the metadata (IPFS CID), pricing, and seller registration.
2.  **Escrow**: Handles the financial transaction between buyer and seller. It holds funds in a secure, programmable state until service delivery is confirmed or a dispute period passes.
3.  **Reputation**: Tracks the reliability and quality of sellers based on successful transactions and user feedback. This contract is updated upon successful escrow completion.
4.  **FeeConfig**: A global configuration contract that defines platform fees, treasury addresses, and authorized contract interactions.

## Contract Interactions
- When a buyer selects an item from **InsightListing**, they initiate a transaction with the **Escrow** contract.
- The **Escrow** contract queries **FeeConfig** to calculate the platform cut.
- Upon successful delivery (off-chain verification or buyer confirmation), the **Escrow** contract releases funds to the seller and triggers an update in the **Reputation** contract.
- If a dispute occurs, the **Escrow** logic dictates the refund process.

## Smart Contract Details
| Contract | Application ID | Address | Network | Last Deployment |
| :--- | :--- | :--- | :--- | :--- |
| InsightListing | 758025190 | AVJELGX3NJ2C3ZXT6KWAHLJZRWRTN7CEOLYUBVKRTR5EWN2QE5L24Q37Q4 | TestNet | 2026-02-14 |
| Escrow | 761839258 | I6YCXMEWRAXGDQ2NAYNPEUWUA77WBHCHQ5O7AYASMJPQEDGPEK44N74ALE | TestNet | 2026-03-01 |
| Reputation | 758022459 | YDIVEMIG7AYBQ7U7ISU5ILNG5RPAIVCU2UUMUF2YTYH2SL6APF3KWQQL2Y | TestNet | 2026-02-15 |
| FeeConfig | 761839101 | BW4DVLKC2VKEH47TPWPCJG6GJEVXTG77VQWZONIV57F255UCV4TU3UKMQU | TestNet | 2026-03-01 |
| SubscriptionManager | 761863755 | N7SSOFF3NXB5E5XNR3AJHH54HR56XPBQ4GJ3Z3IBUHECTCJCZP5GKQAE3U | TestNet | 2026-03-05 |

### Deployment Details
- **Network**: Algorand TestNet (currently deployed)
- **Compiler**: PyTeal (Beaker framework)
- **Deployment Status**: Active and tested
- **Treasury Wallet**: M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM
- **Last Updated**: 2026-05-20

## TestNet Status & Examples

All contracts are actively deployed on Algorand TestNet and have been tested through multiple successful transaction cycles.

### Latest Successful Purchase Cycle (2026-04-13)

The following three transactions were executed atomically as a group and confirmed on TestNet:

1. **Payment Transaction** (USDC Transfer)
   - TX ID: `6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ`
   - Asset: USDC (10458941)
   - Amount: 0.5 USDC
   - From: Buyer wallet
   - To: Seller wallet

2. **Escrow Release Transaction** (Contract: 761839258)
   - TX ID: `MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A`
   - Action: Release payment from escrow
   - Result: Content CID unlocked to buyer

3. **Reputation Update Transaction** (Contract: 758022459)
   - TX ID: `YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A`
   - Action: Update seller reputation
   - Result: Seller reputation 87 → 97 (+10)

### Atomic Group Guarantee

All three transactions were submitted together and confirmed atomically (all-or-nothing guarantee). View the group on [AlgoExplorer TestNet](https://testnet.algoexplorer.io/tx/6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ) using the first transaction ID.

## MainNet Readiness Checklist

TestNet deployment is complete and verified. The following items must be completed before MainNet deployment:

- [x] Comprehensive unit testing (100% logic coverage) - COMPLETE
- [x] Integration testing on TestNet - COMPLETE
- [ ] Security audit of TEAL/PyTeal logic - SCHEDULED
- [ ] Optimization of Algorand opcode budget - IN PROGRESS
- [ ] Disaster recovery and emergency pause mechanisms - PENDING
- [ ] Multi-sig governance setup for FeeConfig updates - PENDING
- [ ] MainNet environment configuration (.env.mainnet) - PENDING
- [ ] Mainnet USDC asset integration (ASA 31566704) - PENDING
- [ ] Contract deployment to MainNet - SCHEDULED
- [ ] Comprehensive MainNet testing period (2+ weeks) - SCHEDULED

## Explorer Links
- [AlgoExplorer TestNet](https://testnet.algoexplorer.io/)
- [Pera Explorer](https://explorer.perawallet.app/)

## Important Transactions

TestNet transactions for reference and audit trails:

### Bootstrap Transactions
- **InsightListing Deploy**: Contract created with app ID 758025190
- **Escrow Deploy**: Contract created with app ID 761839258
- **Reputation Deploy**: Contract created with app ID 758022459
- **FeeConfig Deploy**: Contract created with app ID 761839101
- **SubscriptionManager Deploy**: Contract created with app ID 761863755

### Sample Payment Cycle
- **Payment TX**: `6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ`
- **Escrow Release TX**: `MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A`
- **Reputation Update TX**: `YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A`

Use [AlgoExplorer TestNet](https://testnet.algoexplorer.io/) to verify any transaction by its ID. All transactions are immutable and provide a complete audit trail of the platform's activity.
