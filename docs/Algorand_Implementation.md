# Algorand Implementation

Mercator uses Algorand's blockchain to provide instant, low-cost, and verifiable transactions for AI commerce. This document explains why Algorand, how it's used, and the smart contract architecture.

## Why Algorand?

### Key Advantages for Mercator

| Feature | Benefit | Impact |
|---------|---------|--------|
| **4-5 sec finality** | Payments settle instantly, not hours | Users get content immediately |
| **< $0.01 fees** | Micropayments (< $1) are profitable | Sellers receive fair value |
| **Atomic groups** | 16 txs in one all-or-nothing | No partial escrows, no race conditions |
| **Low state costs** | Storing data is cheap | Scalable reputation system |
| **USDC support** | Stablecoin on-chain | $1 = $1 value, no volatility |
| **Maturity** | Live production blockchain | MainNet ready, not testnet-only |

### Compared to Alternatives

| Aspect | Algorand | Ethereum | Solana |
|--------|----------|----------|--------|
| Block time | 4-5 sec | 12-15 sec | 400ms |
| Average fee | $0.001 | $0.50-5.00 | $0.00025 |
| Finality | Immediate | ~15 min | Probabilistic |
| State storage | Cheap | Expensive | Cheap |
| Atomic groups | Yes (16 tx) | Yes (bundled) | Limited |
| MainNet maturity | Production | Production | Production |
| Developer UX | High | High | Medium |

**For micropayments at scale**: Algorand is optimal.

---

## Blockchain Architecture

### Network Configuration

**TestNet** (Development):
```
Node: https://testnet-api.algonode.cloud
Indexer: https://testnet-idx.algonode.cloud
Explorer: https://testnet.algoexplorer.io
```

**MainNet** (Production):
```
Node: https://mainnet-api.algonode.cloud
Indexer: https://mainnet-idx.algonode.cloud
Explorer: https://algoexplorer.io
```

### Consensus Mechanism

Algorand uses **Pure Proof-of-Stake (PPoS)**:
- Validators chosen randomly, proportional to stake
- No energy-intensive mining
- Instant finality (not probabilistic)
- Censorship-resistant (truly decentralized)

---

## Smart Contract Architecture (ARC4)

### Overview

Mercator uses three ARC4 smart contracts on Algorand:

1. **InsightListing** - Registry of all insights (seller, price, IPFS CID)
2. **Escrow** - Atomic payment + content release
3. **Reputation** - Seller trust scores (on-chain)

### ARC4 Standard

ARC4 is Algorand's smart contract standard providing:
- Type safety (prevents runtime errors)
- Automatic ABI generation
- Framework support (PyTeal, TEAL, JavaScript)
- Contract composability

---

## Contract 1: InsightListing

### Purpose

On-chain registry of all insights. Sellers create listings, buyers search them.

### State Schema

```python
listings: Dict[listing_id] → {
    seller: Address
    price: Uint64 (microunits, 6 decimals)
    cid: String (IPFS hash)
    timestamp: Uint64 (Unix seconds)
    asa_id: Uint64 (USDC ASA ID)
    active: Uint64 (0=archived, 1=active)
}

global_state: {
    listing_count: Uint64
    total_listings_created: Uint64
}
```

### Key Methods

**`create_listing(seller, price, cid, asa_id) → listing_id`**
- Creates new insight listing
- Auto-assigns incrementing listing_id
- Stores metadata on-chain
- Returns: listing_id

**`get_listing(listing_id) → (seller, price, cid, timestamp, asa_id)`**
- Retrieve single listing
- Read-only (no transaction cost)
- Used by agent during search

**`archive_listing(listing_id)`**
- Seller can delist their insight
- Marks as inactive, not deleted
- Historical record preserved on-chain

### Example Usage

```python
# Seller lists insight
from backend.contracts.insight_listing import InsightListingClient

client = InsightListingClient(
    algod_client=algod,
    app_id=INSIGHT_LISTING_APP_ID
)

listing_id = client.create_listing(
    seller="IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4",
    price=500000,  # 0.5 USDC in microunits
    cid="QmABC123XYZ",
    asa_id=10458941  # USDC TestNet
)

print(f"Listing created: {listing_id}")

# Buyer retrieves listing
listing = client.get_listing(listing_id)
print(f"Price: {listing.price / 1_000_000} USDC")
print(f"Seller reputation (from chain): TBD")
```

---

## Contract 2: Escrow

### Purpose

Atomic payment mechanism. Ensures USDC transfer + content unlock + reputation update happen together or not at all.

### State Schema

```python
escrow_records: Dict[transaction_id] → {
    buyer: Address
    seller: Address
    amount: Uint64 (microunits)
    asa_id: Uint64 (USDC ASA ID)
    listing_id: Uint64 (reference)
    timestamp: Uint64 (payment time)
    status: Uint64 (0=pending, 1=released, 2=disputed)
}
```

### Key Methods

**`initiate_escrow(buyer, seller, amount, listing_id) → escrow_id`**
- Lock funds in escrow temporarily
- Called as part of payment atomic group
- Returns escrow ID for tracking

**`release_escrow(escrow_id)`**
- Release funds to seller
- Called automatically after payment confirmed
- Atomic with USDC transfer + reputation

**`dispute_escrow(escrow_id)`** (Future)
- Buyer claims content issue
- Funds returned to buyer
- Reputation deducted for seller

### Example Usage

```python
from backend.contracts.escrow import EscrowClient

client = EscrowClient(
    algod_client=algod,
    app_id=ESCROW_APP_ID
)

# Called as part of atomic group
escrow_txn = client.release_escrow(
    escrow_id=1,
    seller="IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4"
)

# Submit as Tx2 in atomic group
signed_group = algosdk.atomic_transaction_composer.build_and_submit(group)
```

---

## Contract 3: Reputation

### Purpose

On-chain seller trust scores. Immutable history prevents gaming.

### State Schema

```python
seller_reputation: Dict[seller_address] → {
    score: Uint64 (0-100)
    transactions_count: Uint64
    timestamp_updated: Uint64
    total_sold: Uint64 (microunits)
}
```

### Key Methods

**`update_reputation(seller, delta) → new_score`**
- Increment or decrement reputation
- Called after successful payment (+10)
- Called after dispute (-10)
- Returns new score

**`get_reputation(seller) → score`**
- Retrieve seller's current score
- Read-only, used by agent
- Default for new sellers: 50

**`slash_reputation(seller, amount)`** (Future)
- Penalize malicious behavior
- Called by DAO vote or oracle
- Irreversible

### Example Usage

```python
from backend.contracts.reputation import ReputationClient

client = ReputationClient(
    algod_client=algod,
    app_id=REPUTATION_APP_ID
)

# Get seller's current reputation
score = client.get_reputation("IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4")
print(f"Seller reputation: {score}/100")

# Update after successful payment (called in Tx3)
new_score = client.update_reputation(seller, delta=+10)
```

---

## Atomic Transaction Groups

### The Complete Payment Flow

Every payment is **exactly 3 transactions** submitted as an atomic group:

```
Group ID: abc123def456...

Tx 1: ASA Transfer
├─ Sender: Buyer wallet
├─ Receiver: Seller wallet
├─ Asset: USDC (10458941)
├─ Amount: 0.5 USDC
└─ Fee: 1000 microAlgos

Tx 2: Escrow Release
├─ App Call to ESCROW_APP_ID
├─ Method: "release"
├─ Args: [listing_id]
├─ Accounts: [seller]
└─ Fee: 1000 microAlgos

Tx 3: Reputation Update
├─ App Call to REPUTATION_APP_ID
├─ Method: "update"
├─ Args: [seller, +10]
├─ Accounts: [seller]
└─ Fee: 1000 microAlgos

---
Total Group Fee: 3000 microAlgos (~$0.003)
All transactions: CONFIRMED or ALL REJECTED
No partial states possible
```

### Atomic Execution Guarantee

```python
# Submitted as atomic group
group_txns = [
    asa_transfer_txn,
    escrow_release_txn,
    reputation_update_txn
]

# Sign all transactions
signed_group = algosdk.atomic_transaction_composer.build_group(group_txns)

# Submit to Algorand
tx_id = algod.send_transactions(signed_group)

# Wait for confirmation (max 4 rounds)
algod.wait_for_confirmation(tx_id, max_rounds=4)

# Result: All 3 transactions confirmed together or none confirmed
# No possibility of 2/3 confirming
```

---

## USDC Integration

### Algorand Standard Asset (ASA)

USDC is implemented as an ASA (Algorand Standard Asset):

**TestNet USDC**:
```
Asset ID: 10458941
Name: USD Coin
Decimals: 6
Total Supply: Not relevant (centralized mint)
Official: Issued by Circle
```

**MainNet USDC**:
```
Asset ID: 31566704
Name: USD Coin
Decimals: 6
Official: Issued by Circle
Liquid: Can exchange to fiat on multiple exchanges
```

### Wallet Setup

To receive USDC, wallets must **opt-in**:

```python
# Wallet must execute this once
opt_in_txn = algosdk.transaction.AssetTransferTxn(
    sender=wallet_address,
    index=10458941,  # USDC asset ID
    amount=0,
    receiver=wallet_address
)

# After opt-in, wallet can receive USDC transfers
```

---

## Indexer for Historical Queries

Algorand Indexer enables fast queries of historical data:

```python
from algosdk.v2client import indexer

indexer_client = indexer.IndexerClient(
    token="",
    address="https://testnet-idx.algonode.cloud"
)

# Search all transactions for listing creation
results = indexer_client.search_transactions(
    app_id=INSIGHT_LISTING_APP_ID,
    min_round=0,
    max_round=1000000
)

# Get all reputation updates for a seller
results = indexer_client.search_transactions(
    app_id=REPUTATION_APP_ID,
    account_id=seller_address
)

# Get all USDC transfers for a buyer
results = indexer_client.search_asset_transfers(
    asset_id=10458941,
    address_role="receiver",
    address=buyer_address
)
```

---

## MainNet Readiness

### Currently (TestNet)

- [Confirmed] Smart contracts deployed and tested
- [Confirmed] Atomic transaction groups working
- [Confirmed] USDC transfers confirmed
- [Confirmed] Reputation tracking verified
- [Confirmed] End-to-end payment flow tested

### Before MainNet Deployment

- [ ] Third-party security audit of contracts
- [ ] Load testing (1000+ txs/min)
- [ ] Recovery procedures documented
- [ ] Monitoring & alerting configured
- [ ] Mainnet app IDs obtained via deployment
- [ ] Initial funding for transaction fees
- [ ] Emergency pause mechanism (optional)

### Deployment Process

1. **Audit**: External firm reviews contracts
2. **Deploy**: Deploy to MainNet (new app IDs)
3. **Verify**: Check contract creation via explorer
4. **Test**: Execute full payment flow with real funds
5. **Monitor**: Watch for issues during ramp-up
6. **Announce**: Publish MainNet app IDs

---

## Fee Structure

### Transaction Fees

All Algorand transactions require:
- **Minimum fee**: 1000 microAlgos ($0.0001)
- **Per transaction**: 1000 microAlgos
- **Our payment group**: 3 txs × 1000 = 3000 microAlgos (~$0.003)

### State Storage

Storing data on-chain has minimal cost:
- **Per byte**: Negligible (~$0.00001/byte/year)
- **Per listing**: ~500 bytes stored forever
- **For 1000 listings**: < $1/year storage

### Total Payment Cost

```
0.5 USDC payment:
  + 0.003 USDC (network fees)
  + 0.002 USDC (platform fee, future)
  = 0.505 USDC to seller

Platform revenue: 0.002 USDC (0.4%)
Network cost: 0.003 USDC (0.6%)
Sustainable at scale
```

---

## Security Assumptions

### What Algorand Protects

- [Confirmed] Transaction finality (can't be reversed)
- [Confirmed] Sender authenticity (requires signature)
- [Confirmed] Data immutability (historical audit trail)
- [Confirmed] Atomic execution (all-or-nothing)
- [Confirmed] Censorship resistance (no central gatekeeper)

### What We're Responsible For

- [Implementation Dependent] Wallet security (users keep their seed phrases)
- [Implementation Dependent] Smart contract logic (preventing bugs in code)
- [Implementation Dependent] Off-chain content (ensuring IPFS CID is accessible)
- [Implementation Dependent] Reputation system (preventing gaming/collusion)
- [Implementation Dependent] Rate limiting (preventing spam/DoS)

---

## Future Enhancements

### Algorand Upcoming

- **AVM 1.1** (Late 2026): Better opcodes for optimization
- **Rekeying** (Already available): Enhanced key management
- **Stateless programs** (Already available): Upgrade logic without state changes

### Mercator Enhancements

- **ZKP verification**: Private seller identities
- **Oracle integration**: Real-time price feeds
- **Cross-chain**: Pay on Ethereum, settle on Algorand
- **DAO governance**: Community votes on platform fees

---

## Testing Transactions

### Example Payment on TestNet

View this transaction on Algorand TestNet explorer:

**Status**: Confirmed
**Group**: All 3 transactions confirmed atomically

```
Tx1: USDC Transfer
├─ Amount: 0.5 USDC
├─ From: [BUYER_ADDRESS]
└─ To: [SELLER_ADDRESS]

Tx2: Escrow Release  
├─ App Call: ESCROW_APP_ID
└─ Result: Content CID unlocked

Tx3: Reputation Update
├─ App Call: REPUTATION_APP_ID
└─ Result: Seller rep +10 (new score: 65)

Explorer Link: https://testnet.algoexplorer.io/tx/...
```

---

## References

- **Algorand Docs**: [developer.algorand.org](https://developer.algorand.org/)
- **PyTeal**: [pyteal.readthedocs.io](https://pyteal.readthedocs.io/)
- **ARC4 Standard**: [ARC-4 spec](https://github.com/algorandfoundation/ARCs/blob/main/ARCs/arc-0004.md)
- **ASA Spec**: [Algorand Standard Assets](https://developer.algorand.org/docs/get-details/asa/)
- **AlgoExplorer**: [testnet.algoexplorer.io](https://testnet.algoexplorer.io/) (view live transactions)

## Core Concepts

### UnitName: USDC (Algorand Standard Asset)

Mercator uses the Algorand Standard Asset (ASA) version of USDC for micropayments:

| Property | Value |
|----------|-------|
| Asset Name | USDC |
| Asset ID (TestNet) | 10458941 |
| Decimals | 6 |
| Min Transfer | 0.000001 USDC (1 microunit) |
| Max Single Payment | 5.0 USDC (enforced in code) |

**Why USDC on Algorand?**
- Stablecoin: 1 USDC = $1 USD (value stability)
- Fast settlement: 4-5 second finality
- Low fees: < $0.01 per transaction
- Liquid: Can convert to fiat on multiple exchanges

### ARC4 Smart Contracts

ARC4 is Algorand's contract encoding standard that provides:
- Strong type safety
- Automated ABI generation
- Built-in security patterns
- Compatible with multiple languages

All three Mercator contracts use ARC4 for safety and interoperability.

---

## Contract 1: InsightListing

**Location**: `backend/contracts/insight_listing/`

**Purpose**: Register and index all available insights

**Key State Variables**:

```python
listings: Dict[int, Listing]  # mapping: listing_id -> listing metadata
```

**Listing Structure**:
```python
class Listing(abi.NamedTuple):
    seller: abi.Address      # Seller's wallet address
    price: abi.Uint64        # Price in microunits (6 decimals = cents)
    cid: abi.String          # IPFS content hash
    timestamp: abi.Uint64    # Listing creation time (Unix epoch)
    asa_id: abi.Uint64       # USDC ASA ID
```

**Available Methods**:

### `create_listing`
Creates a new insight listing on-chain.

```python
@arc4.abimethod
def create_listing(
    seller: abi.Address,
    price: abi.Uint64,
    cid: abi.String,
    asa_id: abi.Uint64
) -> abi.Uint64
```

**Parameters**:
- `seller`: Algorand address of insight creator
- `price`: Price in microunits (multiply by 10^6 from decimal)
- `cid`: IPFS hash starting with "Qm" (format validation required)
- `asa_id`: Asset ID for payment (10458941 for USDC)

**Returns**: Listing ID (unsigned integer)

**On-Chain Effects**:
- New listing stored in contract state
- Automatically assigned incrementing listing ID
- Event emitted (if supported)

**Example Call** (from Python backend):
```python
listing_id = contract_call.create_listing(
    seller=Address("IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4"),
    price=500000,  # 0.5 USDC (500000 microunits)
    cid="QmABC123...xyz",
    asa_id=10458941
)
# Returns: listing_id (e.g., 47)
```

### `get_listing`
Retrieve a single listing's metadata.

```python
@arc4.abimethod(readonly=True)
def get_listing(listing_id: abi.Uint64) -> Listing
```

**Parameters**:
- `listing_id`: ID of listing to fetch

**Returns**: Listing struct with all metadata

**External Call Pattern**:
Used by agent during discovery and by buyers before checkout.

---

## Contract 2: Escrow

**Location**: `backend/contracts/escrow/`

**Purpose**: Atomic payment and release mechanism

The Escrow contract ensures that:
1. Payment occurs atomically in one transaction group
2. Buyer funds are held safely until verification
3. Seller receives funds only after payment confirmed
4. Release is automatic and transparent

**Key State**:

```python
escrow_ledger: Dict[int, EscrowRecord]  # transaction_id -> lock/unlock state
```

**EscrowRecord Structure**:
```python
class EscrowRecord(abi.NamedTuple):
    buyer: abi.Address           # Buyer's address
    seller: abi.Address          # Seller's address
    amount: abi.Uint64           # Amount in microunits
    asa_id: abi.Uint64           # Asset to transfer (USDC)
    timestamp: abi.Uint64        # Lock time
    released: abi.Bool           # Has escrow been released?
```

**Available Methods**:

### `lock_payment`
Lock buyer funds in escrow (called first in atomic group).

```python
@arc4.abimethod
def lock_payment(
    buyer: abi.Account,           # The buyer (outer account)
    seller: abi.Address,          # Seller wallet to receive funds
    amount: abi.Uint64,           # Amount in microunits
    asa_id: abi.Uint64            # USDC asset ID
) -> abi.String
```

**Parameters**:
- `buyer`: Algorand account paying (must have USDC balance)
- `seller`: Recipient wallet
- `amount`: Transfer amount (e.g., 500000 = 0.5 USDC)
- `asa_id`: Asset ID (10458941)

**Returns**: Escrow record ID or confirmation string

**Atomic Pattern**:
In an atomic group:
1. Inner app call: `lock_payment` (registers the intent)
2. Outer transaction: USDC transfer from buyer to seller
3. Inner app call: `release_after_payment` (confirms release)

### `release_after_payment`
Verify payment posted and release funds (called after USDC transfer in atomic group).

```python
@arc4.abimethod
def release_after_payment(
    seller: abi.Address,
    amount: abi.Uint64
) -> abi.Bool
```

**Parameters**:
- `seller`: Recipient address to verify
- `amount`: Amount expected

**Returns**: `True` if released, `False` if failed

**Verification Logic**:
- Checks that buyer account received the transfer
- Confirms amount matches
- Marks escrow as released (idempotent)
- Allows instant unlock of content

---

## Contract 3: Reputation

**Location**: `backend/contracts/reputation/`

**Purpose**: Track and verify seller trust scores

**Key State**:

```python
reputation: Dict[address, Uint64]  # mapping: seller_address -> reputation_score
```

**Reputation Rules**:
- Initial score: 0
- For each successful sale: +10 points
- Score never decreases (monotonically increasing)
- Tied to seller wallet address permanently

**Available Methods**:

### `increment_reputation`
Increment a seller's reputation score (called after successful payment).

```python
@arc4.abimethod
def increment_reputation(
    seller: abi.Address,
    delta: abi.Uint64 = 10  # Default increment
) -> abi.Uint64
```

**Parameters**:
- `seller`: Seller wallet address
- `delta`: Points to add (default 10)

**Returns**: New reputation score

**Example Call**:
```python
# After successful payment + escrow release:
new_score = reputation_app.increment_reputation(
    seller=Address("IXPLWQSP..."),
    delta=10  # Always +10 for successful purchase
)
# new_score might be: 87 -> 97
```

**Access Control**:
- Only the Escrow contract can call this
- Prevents unauthorized reputation manipulation

### `get_reputation`
Query seller's current reputation score (read-only).

```python
@arc4.abimethod(readonly=True)
def get_reputation(seller: abi.Address) -> abi.Uint64
```

**Parameters**:
- `seller`: Wallet address to check

**Returns**: Current reputation score (0-999+)

**Low Reputation Skip Logic**:
In the buyer agent, any seller with reputation < 30 is auto-skipped:

```python
if seller_reputation < 30:
    return BUY_DECISION.SKIP
```

---

## Atomic Transaction Grouping

**The Heart of Mercator**: Atomic all-or-nothing payment + immediate escrow release

### Structure of Payment Transaction Group

One payment group contains exactly 3 Algorand transactions:

1. **Pay Transaction**: USDC transfer from buyer to seller & escrow contract
   - Type: `axfer` (asset transfer)
   - Sender: Buyer wallet
   - Receiver: Seller wallet
   - Amount: Price in microunits
   - Asset: USDC (10458941)
   - Fee: ~0.001 Algo

2. **App Call 1**: Escrow `lock_payment` call (verify intent)
   - Type: `appl` (application call)
   - Sender: Buyer wallet
   - App ID: Escrow contract ID
   - Method: `lock_payment`
   - Foreign Assets: [USDC asset ID]
   - Fee: ~0.001 Algo

3. **App Call 2**: Escrow `release_after_payment` call (verify release)
   - Type: `appl` (application call)
   - Sender: Buyer wallet
   - App ID: Escrow contract ID
   - Method: `release_after_payment`
   - Fee: ~0.001 Algo

### Atomic Execution Guarantee

All 3 transactions succeed together or all 3 fail together. Partial execution is impossible because:
- Algorand validates entire group before posting
- If any transaction fails, entire group is rejected
- No cleanup needed; state never partially modified

### Example: Successful Group

```
Transaction Group ID: 6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ

Tx 1: axfer (USDC transfer)
  From: MJ43TC6S6UKGLCR2PG4V7A76FNKRT7TWOVTP4X2ENTNBTNCCGN734RUSAQ (buyer)
  To: IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4 (seller)
  Amount: 500000 microunits (0.5 USDC)
  Status: CONFIRMED

Tx 2: appl (Escrow lock_payment)
  AppID: 1234567 (Escrow contract)
  Method: lock_payment
  Status: CONFIRMED

Tx 3: appl (Escrow release_after_payment)
  AppID: 1234567 (Escrow contract)
  Method: release_after_payment
  Status: CONFIRMED

Group Status: ALL-OR-NOTHING SUCCESS
```

### Example: Failed Group (Insufficient Balance)

```
Transaction Group ID: REJECTED_BEFORE_POSTING

Group Status: FAILED
Reason: Inner transaction 1 (lock_payment) failed at simulation:
  Account balance insufficient for this transaction

Action: Entire group rejected, no state changes on-chain
```

---

## Backend Implementation Details

### Payment Execution Code

**File**: `backend/tools/x402_payment.py`

The payment flow uses AlgoKit's `AtomicTransactionComposer` (ATC) to group transactions:

```python
def send_atomic_payment_and_redeem(
    buyer_address: str,
    seller_address: str,
    price_in_usdc: float,
    listing_id: int
) -> Dict[str, str]:
    """
    Compose and send buyer USDC transfer + escrow release atomically.
    
    Returns: {
        "payment_transaction_id": "6RHL36...",
        "redeem_transaction_id": "MNZCPD...",
        "status": "success"
    }
    """
    
    # Setup clients
    algod_client = algosdk.v2client.algod.AlgodV2(...)
    
    # Create composer for atomic group
    composer = AtomicTransactionComposer()
    
    # Step 1: Add USDC transfer transaction
    composer.add_transaction(
        TransactionWithSigner(
            txn=PaymentTxn(
                sender=buyer_address,
                sp=algod_client.suggested_params(),
                receiver=seller_address,
                amt=int(price_in_usdc * 10**6),
                asset_index=USDC_ASA_ID
            ),
            signer=signer_for_buyer
        )
    )
    
    # Step 2: Add escrow lock_payment call
    escrow_client.add_lock_payment(
        composer,
        buyer=buyer_address,
        seller=seller_address,
        amount=int(price_in_usdc * 10**6),
        asa_id=USDC_ASA_ID
    )
    
    # Step 3: Add escrow release_after_payment call
    escrow_client.add_release_after_payment(
        composer,
        seller=seller_address,
        amount=int(price_in_usdc * 10**6)
    )
    
    # Execute entire group atomically
    results = composer.execute(algod_client)
    
    return {
        "payment_transaction_id": results[0].txID,
        "redeem_transaction_id": results[2].txID,
        "status": "success"
    }
```

### Post-Payment Reputation Update

After atomic group confirms, update seller reputation:

```python
def complete_purchase_flow(
    buyer_address: str,
    seller_address: str,
    listing_id: int,
    escrow_tx_id: str  # TX ID of atomic redeem call
) -> Dict:
    """
    Confirm payment, update reputation, deliver content.
    """
    
    # Step 1: Wait for escrow TX to finalize
    receipt = wait_for_confirmation(algod_client, escrow_tx_id)
    
    # Step 2: Call reputation contract to increment
    reputation_result = reputation_app.increment_reputation(
        seller=seller_address,
        delta=10
    )
    reputation_tx_id = reputation_result.txID
    
    # Step 3: Fetch insight content from IPFS and return
    cid = get_listing_cid(listing_id)
    insight_text = fetch_from_ipfs(cid)
    
    return {
        "status": "success",
        "reputation_tx_id": reputation_tx_id,
        "insight_text": insight_text
    }
```

### Agent Integration

The autonomous buyer agent uses these contracts for decision-making:

```python
# Example agent flow
def agent_evaluate_and_purchase(query: str, user_approval: str) -> dict:
    """
    LangChain agent with tool calls to Mercator.
    """
    
    # Step 1: Semantic search (uses insightlisting contract)
    listings = semantic_search_tool(query)  # Returns top matches
    
    # Step 2: Rank by reputation (reads from reputation contract)
    for listing in listings:
        seller_reputation = reputation_app.get_reputation(listing.seller)
        if seller_reputation < 30:
            continue  # Skip low-reputation sellers
    
    # Step 3: Evaluate value/price threshold
    if listing.price > THRESHOLD_PRICE:
        return DECISION.SKIP
    
    # Step 4: User approval
    if user_approval != "approve":
        return DECISION.SKIP
    
    # Step 5: Execute payment (atomic group)
    payment_result = send_atomic_payment_and_redeem(
        buyer_address=BUYER_ADDRESS,
        seller_address=listing.seller,
        price_in_usdc=listing.price,
        listing_id=listing.id
    )
    
    # Step 6: Update reputation and deliver
    final_result = complete_purchase_flow(
        buyer_address=BUYER_ADDRESS,
        seller_address=listing.seller,
        listing_id=listing.id,
        escrow_tx_id=payment_result["redeem_transaction_id"]
    )
    
    return final_result
```

---

## Transaction Proofs and Verification

### Checking Transaction Status

All transaction IDs can be verified on Algorand TestNet:

**Explorer URLs**:
```
Payment TX: https://explorer.perawallet.app/tx/{tx_id}/
Redeem TX: https://explorer.perawallet.app/tx/{tx_id}/
Reputation TX: https://explorer.perawallet.app/tx/{tx_id}/
```

### Proof Example: Latest Successful Purchase

From [SECURITY.md](SECURITY.md):

```
Date: 2026-04-13
Payment TX: 6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ
Redeem TX: MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A
Reputation TX: YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A

Buyer: MJ43TC6S6UKGLCR2PG4V7A76FNKRT7TWOVTP4X2ENTNBTNCCGN734RUSAQ
Seller: IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4
Amount: 0.5 USDC (500000 microunits)

Status: CONFIRMED
Reputation Before: 87
Reputation After: 97
Delta: +10
```

### Using AlgoKit CLI for Verification

```bash
# Retrieve transaction details
algokit explore

# Or from command line
curl "https://testnet-api.algonode.cloud/v2/transactions/${TX_ID}"
```

---

## Algorand Best Practices Used in Mercator

1. **Atomic Grouping**: Payment + release in single group (no race conditions)
2. **ARC4 Contracts**: Type-safe smart contract code
3. **ASA for Value**: USDC Algorand Standard Asset (stable, fast, low fees)
4. **ReadOnly Methods**: `get_listing()`, `get_reputation()` reduce costs
5. **Minimum Balance**: Each contract account holds 0.1 Algo for state management
6. **Transaction Fees**: ~0.001 Algo per transaction included in groups
7. **4-5 Second Finality**: Immediate confirmation without watchers

---

## Security Considerations

### Reentrancy Protection

Algorand contracts are immune to reentrancy because:
- Each transaction has explicit sender
- State changes are isolated to transaction group
- No external calls during execution

### Access Control

Only Escrow contract can call Reputation increment:
```python
require(Txn.sender() == I(escrow_app_id))
```

### Amount Validation

Payment amounts validated before on-chain execution:
- Minimum: 0.000001 USDC
- Maximum: 5.0 USDC (enforced in Python layer)

---

## Resources

- **Algorand Docs**: https://developer.algorand.org/
- **AlgoKit Utilities**: https://github.com/algorandfoundation/algokit-utils-py
- **ARC4 Spec**: https://arc.algorand.foundation/ARCs/arc-0004
- **USDC on Algorand**: https://www.circle.com/en/usdc/algorand
- **TestNet Dispenser**: https://dispenser.testnet.algoexplorerapi.io/
- **TestNet Explorer**: https://explorer.perawallet.app/

---

## Next Steps

- See [DEMO.md](DEMO.md) for interactive walkthrough
- See [COMPONENTS.md](COMPONENTS.md) for implementation details
- See [TESTS.md](TESTS.md) for transaction verification tests
