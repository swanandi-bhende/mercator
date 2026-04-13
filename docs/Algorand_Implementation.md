# Algorand Technology Stack

This document explains how Mercator leverages Algorand's blockchain to enable verifiable, atomic, and reputation-aware micropayments for digital content commerce.

## Overview

Mercator uses Algorand TestNet with three core smart contracts (ARC4) to manage:
1. **Insight Listing**: Content metadata and pricing
2. **Escrow**: Atomic payment and fulfillment lockbox
3. **Reputation**: Seller trust scores and verification

This architecture ensures payments are atomic (all-or-nothing), transactions are finalized in seconds, and seller reputation is immutable and on-chain.

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
