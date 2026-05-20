# Demo Guide

This guide walks you through Mercator's full user experience, from listing to payment to receipt. Follow this for a 5-minute demo that demonstrates the complete AI commerce and x402 payment flow.

**Live Demo**: [mercator-algorand.vercel.app](https://mercator-algorand.vercel.app/)

**Demo Video**: [Watch on YouTube](https://youtu.be/k5caPDtFi3c)

---

## What Problem Does Mercator Solve?

**The Problem**: 
- AI agents can't transact trustlessly with each other today
- There's no standard way for autonomous systems to pay for digital content
- Existing payment systems are designed for humans, not machines
- Commerce infrastructure is siloed (payment processor, escrow, reputation tracking all separate)

**Mercator's Solution**:
- A unified platform where AI agents autonomously discover, evaluate, and pay for insights
- x402 micropayments enable instant, atomic, programmable transactions
- On-chain reputation ensures trust without intermediaries
- Smart contracts handle escrow and verification automatically

---

## The Product in 5 Minutes

### Part 1: Seller Lists an Insight (1 minute)

**Step**: Go to [mercator-algorand.vercel.app](https://mercator-algorand.vercel.app/) → Click **"Sell Insight"**

**What the Seller Does**:
1. Enters their insight text: `"NIFTY will break 24,500 resistance if RBI rates stay elevated"`
2. Sets price: `0.5 USDC` (micro-payments, not micro-fees)
3. Enters seller Algorand wallet address
4. Clicks "List Insight"

**What Happens Behind the Scenes**:
- Content is uploaded to IPFS (Pinata)
- Listing is created on `InsightListing` smart contract
- Listing gets an ID and is indexed on-chain
- Seller reputation starts at 50 (baseline)

**Success Signal**: Transaction ID appears, explorer link shows on-chain listing

---

### Part 2: Agent Discovers & Evaluates (2 minutes)

**Step**: Click **"Discover Insights"** tab

**What the Agent Does**:
1. **Semantic Search**: Finds all listings matching the buyer's query
   - Example query: `"Best NIFTY trading setup"`
   - Returns: Top insights ranked by relevance + reputation
2. **Evaluation**: For each insight, calculates:
   - **Relevance**: How well does it match the query? (0-100)
   - **Reputation**: Is the seller trustworthy? (0-100)
   - **Value-for-Price**: Is it worth the cost? (relevance / price)
3. **Decision**: BUY if value-for-price > 8.0, otherwise SKIP

**What Judges Should Observe**:
- Real semantic search ranking (not fake data)
- Reputation as a trust signal
- Agent skips low-quality or high-price listings
- Rankings change based on query relevance

**Example Evaluation** (visible in UI):
```
Insight: "NIFTY resistance at 24,500"
├─ Relevance: 92/100 (highly relevant to query)
├─ Seller Reputation: 65/100 (verified seller)
├─ Price: 0.5 USDC
├─ Value-for-Price: 92 / 0.5 = 184 (GOOD VALUE)
└─ Decision: [BUY]
```

---

### Part 3: Buyer Approves Payment (1 minute)

**Step**: From search results, click **"Buy"** on selected insight

**What Happens**:
1. **Checkout screen** shows:
   - Insight preview (truncated content)
   - Price in USDC
   - Seller reputation
   - Buyer wallet address
   - Call-to-action: "Type 'approve' to pay"

2. **User Types "approve"**:
   - This is the explicit user authorization gate
   - x402 protocol requires human confirmation before payment
   - Mitigates unauthorized spending and agent-gone-rogue scenarios

**What Judges Should Observe**:
- Explicit approval gate (security feature)
- Clear transaction details before payment
- No hidden fees or dark patterns

---

### Part 4: X402 Micropayment Execution (1 minute)

**What Happens After User Types "approve"**:

1. **Payment Simulation** (local, no blockchain):
   ```
   ├─ Validate sender address format
   ├─ Validate receiver address format
   ├─ Check amount > 0
   ├─ Estimate network fee
   └─ Result: SAFE_TO_PROCEED
   ```

2. **Atomic Transaction Group** (on-chain):
   ```
   ┌─ Transaction 1: USDC Transfer (buyer → contract)
   ├─ Transaction 2: Escrow Release (contract → seller)
   ├─ Transaction 3: Reputation Update (+10 for seller)
   └─ ALL-or-NOTHING guarantee (atomic grouping)
   ```

3. **Finality**: Algorand confirms in ~4-5 seconds

4. **Result**:
   ```
   [Confirmed] Payment: 0.5 USDC transferred
   [Confirmed] Content unlocked: IPFS CID revealed
   [Confirmed] Seller reputation: +10
   [Confirmed] Transaction ID: [HASH]
   ```

**What Judges Should Observe**:
- Payment completes instantly (no waiting)
- Transaction ID appears in real-time
- Seller's reputation increased visibly
- Explorer link shows atomic group of 3 transactions
- No intermediaries, fully on-chain

---

### Part 5: Buyer Receives Receipt (1 minute)

**Step**: Automatically redirected to **"Receipt"** page

**What Buyer Sees**:
- [Confirmed] Payment confirmed
- [Confirmed] Content unlocked (full IPFS text displayed)
- [Confirmed] Seller reputation updated
- Transaction details:
  - From (buyer address)
  - To (seller address)
  - Amount (0.5 USDC)
  - Block/transaction ID
  - Explorer link to Algorand TestNet

**What Judges Should Observe**:
- Instant receipt generation
- Full transaction transparency
- IPFS content delivery (not stored on backend)
- All verifiable on public explorer

---

## Complete Flow Diagram

```
┌──────────────────────────────────────────────────────────────────┐
│                    SELLER LISTS INSIGHT                          │
│  1. Write insight text                                           │
│  2. Set price (0.5 USDC)                                         │
│  3. Click "List"                                                 │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ InsightListing Contract     │
         │ + IPFS Upload               │
         │ → Listing ID created        │
         │ → On-chain metadata stored  │
         └─────────────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│               BUYER SEARCHES & AGENT EVALUATES                   │
│  1. Enter query: "Best NIFTY setup"                              │
│  2. Semantic search finds matching listings                      │
│  3. Agent evaluates: relevance + reputation + price              │
│  4. Ranked results: BUY → Search → Evaluate → Rank → Display     │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
             ┌────────────────────┐
             │  Results Displayed │
             │  "Buy" button      │
             │  visible           │
             └────────────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│              BUYER CLICKS "BUY" → CHECKOUT SCREEN                │
│  1. Show insight preview                                         │
│  2. Show price: 0.5 USDC                                         │
│  3. Show seller reputation: 65/100                               │
│  4. Prompt: "Type 'approve' to pay"                              │
└──────────────────────┬───────────────────────────────────────────┘
                       │
                       ▼
         ┌─────────────────────────────┐
         │ User Types "approve"        │
         │ Explicit Authorization Gate │
         └──────────────┬──────────────┘
                        │
                        ▼
        ┌────────────────────────────┐
        │ Payment Simulation         │
        │ (Local validation)         │
        │ Result: SAFE               │
        └───────────┬────────────────┘
                    │
                    ▼
  ┌────────────────────────────────────┐
  │ Atomic Transaction Group (x402)    │
  │ Algorand TestNet                   │
  ├────────────────────────────────────┤
  │ Tx1: USDC Transfer (0.5)           │
  │      buyer → seller                │
  ├────────────────────────────────────┤
  │ Tx2: Escrow Release                │
  │      verify & unlock               │
  ├────────────────────────────────────┤
  │ Tx3: Reputation Update             │
  │      seller +10                    │
  └───────────┬────────────────────────┘
              │
              ▼ (4-5 sec finality)
        ┌─────────────────────────────┐
        │ ALL TRANSACTIONS CONFIRMED  │
        │ Atomic grouping = No risk   │
        └──────────────┬──────────────┘
                       │
                       ▼
┌──────────────────────────────────────────────────────────────────┐
│                    RECEIPT PAGE                                  │
│  [Confirmed] Payment: 0.5 USDC confirmed                          │
│  [Confirmed] Content: IPFS CID revealed                           │
│  [Confirmed] Reputation: +10 for seller                           │
│  → Explorer link shows all 3 txs                                 │
│  → Full transaction transparency                                 │
└──────────────────────────────────────────────────────────────────┘
```

---

## Key Moments to Highlight (For Judges)

### 1. **Mainnet-Ready Architecture**
- Works on Algorand TestNet (ready for MainNet)
- All transactions on public blockchain
- No intermediaries, no custodial wallets
- Full explorer transparency

### 2. **Real x402 Micropayment Flow**
- Atomic payment + escrow + reputation in ONE transaction group
- Instant finality (4-5 seconds)
- Low fees (<$0.01)
- User approval gate prevents agent abuse

### 3. **AI Agent Autonomy**
- Agent makes real economic decisions
- Evaluation based on data (relevance, reputation, price)
- Agent respects human guardrails ("approve" gate)
- Fully auditable reasoning chain

### 4. **Real Content Delivery**
- Content stored on IPFS (decentralized)
- Unlocked only after payment confirmed
- Seller reputation stake prevents fraud
- Buyer can verify content before rating

### 5. **Scalability & Efficiency**
- Atomic grouping = no partial failures
- Reputation system replaces escrow deposits
- Supports unlimited sellers/buyers
- Ready for multi-agent marketplaces

---

## Demo Script (Suggested Pitch)

**30-Second Elevator Pitch**:

> "Mercator is a marketplace where AI agents autonomously buy and sell trading insights. When a buyer asks for a NIFTY trading setup, our agent searches real listings, evaluates them using on-chain reputation and price, and executes instant x402 micropayments—all atomically on Algorand. The seller gets paid in 5 seconds, the buyer gets content immediately, and reputation protects the ecosystem. It's the infrastructure for AI-to-AI commerce."

**Full 5-Minute Demo**:

1. **Show listing page** (30 sec): "A seller creates an insight with a price and content—stored on IPFS, indexed on-chain."

2. **Run semantic search** (1 min): "When a buyer searches, our agent ranks results by relevance AND seller reputation—not just recency or popularity."

3. **Show evaluation logic** (1 min): "The agent calculates value-for-price and decides BUY only if it's worth it. This is real economic reasoning, not just keyword matching."

4. **Execute payment** (2 min): "The buyer types 'approve' as a safety gate. The system simulates the payment, then atomically transfers USDC, releases content, and updates reputation—all in one transaction group on Algorand."

5. **Show receipt** (30 sec): "Instant receipt, explorer link shows all 3 transactions grouped together. No intermediaries. Full blockchain transparency."

**Closing**: "This is production-ready infrastructure for AI agents to transact trustlessly. Imagine thousands of agents autonomously buying and selling insights, with Mercator handling payments, reputation, and verification."

---

## Edge Cases & How They're Handled

### What if the seller has low reputation?
- Agent skips them (reputation filter: ≥50 required)
- Buyer must explicitly choose, sees warning

### What if payment fails?
- Atomic grouping: Either all 3 transactions pass or all fail
- No partial payments, no stuck escrows
- User sees error with reason (insufficient balance, network issue, etc.)

### What if the buyer doesn't type "approve"?
- Payment waits indefinitely (no auto-timeout)
- User must explicitly confirm
- Mitigates agent spending sprees

### What if seller tries to list spam?
- Reputation starts at 50
- Buyer sees reputation score before buying
- After 1 failed purchase, reputation drops to 40
- Spam becomes economically unviable

---

## Testing the Demo Locally

### Option 1: One-Click Demo

```bash
./demo.sh
```

Runs tests, starts backend + frontend, and executes a complete purchase scenario.

### Option 2: Manual Steps

```bash
# Terminal 1: Backend
source .venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Run a test purchase
PYTHONPATH=. pytest backend/tests/test_payment_flow.py -v -s
```

---

## FAQ During Demo

**Q: Is this on TestNet or MainNet?**
A: TestNet now, but fully MainNet-ready. We just need audits and production environment setup.

**Q: Can the agent go rogue and spend all the money?**
A: No—users must type "approve" for each payment. Plus we have rate limiting and max payment caps (5 USDC default).

**Q: What if IPFS goes down?**
A: Content CID is stored on-chain forever. Users can retrieve from any IPFS node or gateway. Seller can also re-pin.

**Q: How does reputation scale to thousands of sellers?**
A: It's on-chain but efficient—just a uint64 per seller. Algorand can handle millions of state updates.

**Q: What happens if Algorand TestNet goes down?**
A: Main features pause, but no data loss. Everything is on-chain and recoverable.

**Q: How would you monetize this?**
A: See [business.md](business.md) for full GTM strategy. TL;DR: API fees, escrow fees, and developer subscriptions.

---

## Next Steps

- **Dig Deeper**: Read [Algorand_Implementation.md](Algorand_Implementation.md) for technical details
- **Learn x402**: See [x402_Implementation.md](x402_Implementation.md) for payment flow architecture
- **Review Smart Contracts**: Check [contracts.md](contracts.md) for on-chain code
- **Business Strategy**: Read [business.md](business.md) for market positioning
