# X402 Micropayment Implementation

Mercator uses the x402 protocol to enable instant, atomic micropayments for AI commerce. This document explains the architecture, payment flow, and integration patterns.

## What is X402?

**x402** is a protocol for **user-initiated micropayments** that combines:
- **Payment Authorization**: Explicit user confirmation before funds transfer
- **Atomicity**: Payment + verification in a single transaction
- **Programmability**: Smart contracts handle conditional releases
- **Instant Settlement**: No intermediaries, funds transfer in seconds

**Why x402 for Mercator?**
- AI agents need to pay autonomously, but never without user approval
- Micropayments (< $1) need instant settlement (no bank processing)
- Blockchain transactions can include smart logic (escrow + reputation)
- Zero intermediaries = lower fees and full transparency

---

## Payment Architecture

### High-Level Flow

```
┌─────────────────────────────────────────────────────────┐
│ BUYER INITIATES: Clicks "Buy Insight"                  │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
┌─────────────────────────────────────────────────────────┐
│ CHECKOUT: Show insight + price + reputation            │
│ Action: User types "approve"                            │
└────────────────┬────────────────────────────────────────┘
                 │
                 ▼
    ┌─────────────────────────────┐
    │ APPROVAL GATE VALIDATION    │
    │ Input: "approve" (required) │
    └──────────┬──────────────────┘
               │
      ┌────────┴──────────┐
      │                   │
  [FAIL]              [PASS]
      │                   │
      ▼                   ▼
 Reject            Payment Simulation
 (retry)           ├─ Validate addresses
                   ├─ Check amount > 0
                   ├─ Estimate fees
                   ├─ Verify balance
                   └─ Result: SAFE
                        │
                        ▼
              ┌──────────────────────────┐
              │ ATOMIC TRANSACTION GROUP │
              │ (Submitted to Algorand)  │
              ├──────────────────────────┤
              │ Tx1: USDC Transfer      │
              │ From: Buyer             │
              │ To: Seller              │
              │ Amount: 0.5 USDC        │
              ├──────────────────────────┤
              │ Tx2: Escrow Release     │
              │ Verify payment received │
              │ Unlock content CID      │
              ├──────────────────────────┤
              │ Tx3: Reputation Update  │
              │ Seller reputation +10   │
              └──────────┬───────────────┘
                         │
                    (4-5 seconds)
                         │
                         ▼
              ┌──────────────────────────┐
              │ [CONFIRMED]             │
              │ Atomic: all 3 or none   │
              └──────────┬───────────────┘
                         │
                         ▼
              ┌──────────────────────────┐
              │ RECEIPT PAGE             │
              │ [Confirmed] Payment      │
              │ [Confirmed] Content      │
              │ [Confirmed] Reputation   │
              │ → Explorer link          │
              └──────────────────────────┘
```

---

## Request Lifecycle

### 1. User Clicks "Buy"

**API Endpoint**: `POST /demo_purchase`

**Request**:
```json
{
  "user_query": "Show me best NIFTY trading setup",
  "user_approval_input": "",
  "listing_id": 47,
  "force_buy_for_test": true
}
```

**Response (Initial)**:
```json
{
  "status": "BUY_PENDING_APPROVAL",
  "message": "Payment requires explicit user approval. Type 'approve' to continue.",
  "insight_preview": "NIFTY will break 24,500 resistance...",
  "price_usdc": 0.5,
  "seller_reputation": 65,
  "listing_id": 47
}
```

### 2. User Types "Approve"

**API Endpoint**: `POST /demo_purchase` (same, with approval input)

**Request**:
```json
{
  "user_query": "Show me best NIFTY trading setup",
  "user_approval_input": "approve",
  "listing_id": 47,
  "force_buy_for_test": true
}
```

**Backend Processing**:
```python
# 1. Validate approval
if user_approval_input != "approve":
    return "BUY_PENDING_APPROVAL"  # Reject

# 2. Simulate payment locally
simulation = x402_client.simulate_payment(
    sender=buyer_address,
    receiver=seller_address,
    amount=price_usdc,
    asa_id=USDC_ASA_ID
)

if simulation.status != "SAFE":
    return {"error": simulation.reason}

# 3. Execute atomic group
txn_group = [
    ASA_TRANSFER(buyer → seller, amount),
    ESCROW_RELEASE(verify + unlock),
    REPUTATION_UPDATE(seller +10)
]

signed_group = sign_atomic_group(txn_group)
tx_id = algod_client.send_transaction(signed_group)

# 4. Wait for confirmation
wait_for_confirmation(tx_id, max_rounds=4)

return {
    "status": "PAYMENT_SUCCESS",
    "tx_id": tx_id,
    "insight_cid": "QmABC123...",
    "seller_reputation_new": 75
}
```

**Response (Success)**:
```json
{
  "status": "PAYMENT_SUCCESS",
  "transaction_id": "XXXXXXX3VEE4XXXXXX",
  "insight_cid": "QmABC123DEF456GHI",
  "amount_usdc": 0.5,
  "seller_address": "IXPLWQSP...",
  "seller_reputation_after": 75,
  "blockchain_url": "https://testnet.algoexplorer.io/tx/...",
  "timestamp": "2026-05-20T10:30:00Z"
}
```

### 3. Error Cases

**Insufficient Balance**:
```json
{
  "status": "PAYMENT_EXECUTION_FAILED",
  "error": "Buyer has insufficient USDC balance (need 0.5, have 0.0)"
}
```

**Invalid Approval**:
```json
{
  "status": "BUY_PENDING_APPROVAL",
  "message": "Payment requires explicit user approval. Type 'approve' to continue."
}
```

**Simulation Failure**:
```json
{
  "status": "PAYMENT_SIMULATION_FAILED",
  "error": "Invalid sender address format"
}
```

**Transaction Rejected**:
```json
{
  "status": "TRANSACTION_REJECTED",
  "error": "Group not valid: transaction group size should not exceed 16"
}
```

---

## Smart Contract Integration

### Atomic Group Structure

Every payment consists of exactly **3 transactions**, submitted as an atomic group:

**Transaction 1: ASA Transfer**
```
Type: ASA Transfer
Sender: Buyer wallet
Receiver: Seller wallet
Asset: USDC (10458941)
Amount: price_usdc (in microunits)
Memo: "Insight purchase: {listing_id}"
```

**Transaction 2: Escrow Release**
```
Type: Application Call
App ID: ESCROW_APP_ID
OnComplete: NoOp
Args: ["release", listing_id]
Foreign Assets: [USDC_ASA_ID]
Accounts: [seller_wallet]
```

Smart contract verifies:
- Payment received in Tx1
- Buyer approved in frontend
- Releases content CID to buyer

**Transaction 3: Reputation Update**
```
Type: Application Call
App ID: REPUTATION_APP_ID
OnComplete: NoOp
Args: ["update", seller_wallet, "+10"]
Accounts: [seller_wallet]
```

Smart contract updates:
- Seller reputation: current +10
- Timestamp: current block time
- Verification: immutable record on-chain

### Atomic Guarantee

**All-or-Nothing Execution**:
- If any transaction in group fails, entire group fails
- No partial payments, no stuck escrows
- Buyer's USDC stays in wallet if any part fails
- Seller doesn't receive payment if any part fails

**Example Failure Scenario**:
```
Group submitted:
├─ Tx1: Transfer 0.5 USDC [PASSED]
├─ Tx2: Escrow release [PASSED]
└─ Tx3: Reputation update [FAILED]: account not opt-in to app

Result: ENTIRE GROUP REJECTED
        Tx1 and Tx2 rolled back automatically
        Buyer still has 0.5 USDC
        Seller receives nothing
```

---

## Payment Authorization Flow

### Explicit User Approval

The "approve" gate is **critical security**:

```
Why "approve" is required:

1. AI agents cannot be fully trusted
   └─ They might spend all money on spam

2. Blockchain is irreversible
   └─ No undo button; funds gone forever

3. Micropayments add up fast
   └─ 100 purchases × $0.50 = $50 in minutes

Solution: Explicit confirmation per payment
└─ User sees what's happening
└─ User makes conscious choice
└─ Audit trail is clear
```

### Implementation

**Frontend (React)**:
```typescript
const [approvalInput, setApprovalInput] = useState("");

function handleCheckout() {
  if (approvalInput !== "approve") {
    setError("Type 'approve' exactly to confirm payment");
    return;
  }
  
  // Only then submit payment
  await submitPayment({
    user_approval_input: approvalInput,
    listing_id: selectedInsight.id
  });
}
```

**Backend (Python)**:
```python
def trigger_x402_payment(user_approval_input: str, ...):
    # Reject anything except exact match
    if user_approval_input != "approve":
        raise UserApprovalRequiredException(
            "Type 'approve' to continue"
        )
    
    # Proceed to simulation + payment
    return execute_payment(...)
```

---

## Error Handling & Retry Logic

### Payment Validation

**Before submission**, validate:
```python
# 1. Addresses valid
assert is_valid_algorand_address(buyer_address)
assert is_valid_algorand_address(seller_address)

# 2. Amount valid
assert amount_usdc > 0
assert amount_usdc <= 5.0  # MAX_MICROPAYMENT

# 3. Approval confirmed
assert user_approval_input == "approve"

# 4. Balance sufficient
buyer_balance = get_usdc_balance(buyer_address)
assert buyer_balance >= amount_usdc
```

### Simulation (Local Validation)

Before touching blockchain:
```python
def simulate_payment(sender, receiver, amount, asa_id):
    """
    Local simulation to catch errors early.
    Does NOT modify blockchain.
    """
    simulation_report = {
        "sender_valid": is_valid_address(sender),
        "receiver_valid": is_valid_address(receiver),
        "amount_positive": amount > 0,
        "amount_under_cap": amount <= MAX_MICROPAYMENT,
        "estimated_fee": 1000,  # microAlgos
        "status": "SAFE" if all checks pass else "FAILED"
    }
    return simulation_report
```

### Retry Strategies

**Transaction Submitted**:
- Wait for confirmation (max 4 blocks = ~20 sec)
- If not confirmed in 4 blocks, transaction expires
- User can retry with new group ID

**Transient Network Errors**:
- Retry up to 3 times with exponential backoff
- Only for errors < 400 (not auth/validation)
- Stop on 400+ errors (likely permanent)

**Partial Failures**:
- Atomic group ensures no partial states
- If group fails, entire payment fails
- Clear error message to user

---

## Future X402 Improvements

### Batching

**Current**: Single payment per transaction group

**Future**: Batch multiple purchases atomically
```
Group: [Tx1_Pay, Tx2_Pay, Tx3_Reputation] × N
Benefit: Reduced fees when agent buys multiple
```

### Streaming Payments

**Current**: Lump sum at checkout

**Future**: Pay-per-unit with streaming escrow
```
Seller streams content line-by-line
Buyer pays incrementally as content validates
Neither party loses money mid-stream
```

### Multi-Asset Support

**Current**: USDC only

**Future**: Support ALGO, other ASAs
```
Generic ASA payment with price feed
Seller receives USDC or preferred ASA
Exchange happens atomically
```

### Cross-Chain Settlements

**Current**: Algorand only

**Future**: Buy on Ethereum, settle on Algorand
```
User approves on MetaMask (Ethereum)
Relay bridge to Algorand payment
Seller receives USDC on Algorand
```

---

## Production Checklist (MainNet Ready)

- [x] User approval gate working
- [x] Payment simulation tested
- [x] Atomic grouping verified
- [x] Error handling comprehensive
- [x] Retry logic implemented
- [ ] Security audit (external)
- [ ] Rate limiting at API level
- [ ] Monitoring/alerting in place
- [ ] Mainnet contract deployment
- [ ] Production wallet security

---

## See Also

- [Algorand_Implementation.md](Algorand_Implementation.md): Smart contract details
- [contracts.md](contracts.md): Contract ABIs and addresses
- [Security.md](Security.md): Payment security model
- [Setup.md](Setup.md): How to run locally
