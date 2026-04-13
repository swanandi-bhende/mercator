# Interactive Demo Guide

This guide walks you through every page and feature of the Mercator user interface. This is the primary way to showcase and test the agentic commerce system.

## Quick Start: One-Click Demo

Run the full end-to-end demo with a single command:

```bash
./demo.sh
```

This will:
1. Run all regression tests
2. Start FastAPI backend on `http://localhost:8000`
3. Start React frontend on `http://localhost:5173`
4. Execute a live autonomous agent purchase scenario
5. Display results in real-time

Expected runtime: 60-120 seconds

### Logs Generated

During the demo, several log files are created:

- `backend.log`: FastAPI server output
- `frontend.log`: React development server output
- `agent_demo.log`: Autonomous agent execution trace
- `mercator.log`: High-level activity log

Check these logs if the demo encounters issues (see Troubleshooting section).

## Manual Demo: Step-by-Step UI Walkthrough

If you prefer to manually test features, follow this workflow:

### Prerequisites

1. Start backend and frontend separately:

```bash
# Terminal 1: Backend
source .venv/bin/activate
cd backend && python -m uvicorn main:app --reload --port 8000

# Terminal 2: Frontend
cd frontend && npm run dev

# Terminal 3: Monitor logs
tail -f backend.log
```

2. Open browser to `http://localhost:5173`

## Page-by-Page Walkthrough

### 1. Home Page

**URL**: `http://localhost:5173/`

**Purpose**: Landing page and navigation hub

**What You'll See**:
- Mercator branding and project description
- Navigation menu with links to all features
- Quick-start buttons for seller and buyer workflows

**What to Do**:
1. Review the description of agentic commerce
2. Click "List a New Insight" to go to seller page (see Section 2)
3. Click "Discover Insights" to go to buyer page (see Section 3)

**Expected Behavior**: Page loads in < 1 second, navigation links work without errors

---

### 2. List Insight Page

**URL**: `http://localhost:5173/sell`  
**Component**: `SellInsight.tsx`

**Purpose**: Seller interface to publish trading insights

**Fields**:

| Field | Type | Example Value | Rules |
|-------|------|---------------|-------|
| Trading Insight | Text Area | "Buy NIFTY above 24500 for 3-month target of 25000. Stop loss at 24100." | Required, 10+ characters |
| Price (USDC) | Number | 0.5 | Required, 0.000001 to 5.0 |
| Seller Wallet Address | Text | IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4 | Valid Algorand address |

**Step-by-Step**:

1. **Enter Trading Insight**
   - Click on the "Trading Insight" text area
   - Type a sample insight (see example above)
   - Min 10 characters to avoid validation error

2. **Set Price in USDC**
   - Click on "Price (USDC)" field
   - Enter a value between 0.000001 and 5.0
   - Example: `0.5` for 50 cents
   - Note: System enforces `MAX_MICROPAYMENT_USDC = 5.0` limit

3. **Enter Seller Wallet**
   - Click on "Seller Wallet Address" field
   - Paste your Algorand TestNet wallet address
   - Must be valid 58-character Algorand address (starts with letter)
   - You can copy this from a wallet app (Pera Wallet, Algosigner, etc.)

4. **Submit the Listing**
   - Click "List Insight on Algorand" button
   - Status will change to "Uploading to IPFS & Algorand..."
   - Spinner will animate during processing

**Expected Behavior**:

Success case (< 10 seconds):
```
✓ Insight listed successfully! View on explorer
[TX ID: 6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ]
```

Then a "Demo purchase result" section appears showing the insight text that was returned.

**What Happens Behind the Scenes**:

1. Frontend sends `POST /list` with insight data
2. Backend uploads insight text to Pinata IPFS
3. Backend stores listing metadata on InsightListing contract
4. Smart contract mint records: price, seller, IPFS CID, asset ID
5. Process returns transaction ID for on-chain proof

**Error Cases and Recovery**:

| Error | Cause | What to Do |
|-------|-------|-----------|
| "Please complete all fields" | Missing required field | Fill all three fields |
| "invalid wallet address format" | Not a valid Algorand address | Verify address is 58 chars, copy from wallet app |
| "LISTING_STORE_ERROR: CID must start with 'Qm'" | IPFS upload failed | Check Pinata JWT in `.env.testnet` |
| "Invalid wallet address" | Syntax error in address | Use fresh address from Pera/Algosigner wallet |
| Timeout after 30 seconds | Network latency or node down | Check `.env.testnet` has correct `ALGOD_URL` |

To unlock a locked form after error: click on any field to edit, error clears.

---

### 3. Discover Insights Page

**URL**: `http://localhost:5173/discover`  
**Component**: `DiscoverInsights.tsx`

**Purpose**: Buyer interface to search and filter available insights

**What You'll See**:
- List of all published insights
- Filtering options (price range, seller reputation)
- Search capability

**Step-by-Step**:

1. **Browse Available Listings**
   - Page loads with all published insights
   - Each insight shows: title, price, seller reputation, seller address

2. **Filter by Price Range** (if available)
   - Look for price filter slider or input
   - Adjust to see listings within price range
   - Example: 0.1 to 1.0 USDC

3. **Sort by Reputation**
   - Insights are ranked by seller reputation
   - Higher reputation sellers appear first

4. **Click on an Insight to Purchase**
   - Click "Purchase" or "Buy Insight" button
   - You're redirected to checkout page (see Section 4)

**Expected Behavior**:
- Page loads existing listings within 2 seconds
- No listings shown? Follow Section 2 to list an insight first
- Filtering updates in real-time as you adjust sliders/inputs

---

### 4. Checkout Page

**URL**: `http://localhost:5173/checkout?listing_id=47`  
**Component**: `Checkout.tsx`

**Purpose**: Finalize insight purchase and process payment

**Fields**:

| Field | Type | Example | Notes |
|-------|------|---------|-------|
| Buyer Wallet | Address | MJ43TC6S6UKGLCR2PG4V7A76FNKRT7TWOVTP4X2ENTNBTNCCGN734RUSAQ | Your TestNet wallet |
| Quantity | Number | 1 | Usually 1 insight = 1 purchase |

**Step-by-Step**:

1. **Review Insight Details**
   - Title, price, seller info displayed
   - Confirm you want to purchase

2. **Enter Buyer Wallet Address**
   - Click "Buyer Wallet" field
   - Paste your TestNet wallet address (different from seller)
   - Suggested: use a different account for testing

3. **Verify Price and Confirm**
   - Total displayed: insight price in USDC
   - Click "Proceed to Payment" button

4. **Wait for Payment Processing**
   - Status changes to "Processing payment..."
   - Backend executes atomic payment group:
     - USDC transfer to seller wallet
     - Escrow release confirmation
     - Reputation increment (+10 to seller)

**Expected Behavior** (8-15 seconds):

Success case:
```
✓ Payment successful
✓ Escrow released
✓ Insight unlocked
✓ Reputation updated (+10)

Transaction IDs:
- Payment: 6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ
- Redeem: MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A
- Reputation: YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A
```

The full insight text is displayed below the success message.

**Error Cases and Recovery**:

| Error | Cause | Solution |
|-------|-------|----------|
| "insufficient balance for this account" | Buyer wallet has < price USDC | Fund buyer wallet from TestNet dispenser |
| "inactive participation record" | Wallet not opted-in to USDC ASA | Opt-in to USDC on wallet app |
| "PAYMENT_LIMIT_EXCEEDED" | Price > 5.0 USDC | Navigate to listing, try a cheaper insight |
| "INVALID_ADDRESS" | Buyer address invalid format | Verify address is 58-char Algorand format |
| Timeout after 30 seconds | Network issues | Check node availability, check logs |

---

### 5. Receipt Page

**URL**: `http://localhost:5173/receipt?tx_id=6RHL36...`  
**Component**: `Receipt.tsx`

**Purpose**: View transaction details and proof of purchase

**What You'll See**:
- Transaction ID and link to explorer
- Timestamp of purchase
- Buyer and seller wallet addresses
- Payment amount
- Reputation update summary

**Step-by-Step**:

1. **Review Transaction Details**
   - Verify transaction ID matches what you saw during checkout
   - Check buyer and seller addresses

2. **Click "View on Block Explorer"**
   - Opens Algorand TestNet explorer
   - Displays full transaction details on-chain
   - Confirms transaction is finalized and permanent

3. **Save or Share**
   - Take screenshot for records
   - Copy transaction ID if needed

**Expected Behavior**:
- Explorer loads within 5 seconds
- You can see all transaction details (amounts, fees, etc.)
- Transaction status shows "Confirmed"

---

### 6. Activity Ledger Page

**URL**: `http://localhost:5173/ledger`  
**Component**: `ActivityLedger.tsx`

**Purpose**: View full audit trail of all activities

**What You'll See**:
- Chronological list of all listings created
- All purchase transactions
- All reputation updates
- Timestamps and transaction IDs

**Step-by-Step**:

1. **View All Activities**
   - Page loads full activity history
   - Most recent activities appear first

2. **Filter by Activity Type** (if available)
   - "Listings" - show only new insight listings
   - "Purchases" - show only payment transactions
   - "Reputation" - show only reputation updates

3. **Click Activity to View Details**
   - Transaction ID becomes clickable
   - Opens receipt page or explorer

**Expected Behavior**:
- Page load time < 2 seconds
- Activities update as you create listings/purchases
- Transaction IDs are exact and link to block explorer

---

### 7. Trust/Reputation Page

**URL**: `http://localhost:5173/trust`  
**Component**: `Trust.tsx`

**Purpose**: Display seller reputation system

**What You'll See**:
- Seller address and current reputation score
- Reputation history (purchases and updates)
- Trust ranking (low/medium/high)

**Information Displayed**:

| Field | Meaning | Example |
|-------|---------|---------|
| Seller Address | Wallet address | IXPLWQSP... (first 20 chars) |
| Current Reputation | Score from 0-100+ | 87 |
| Status | Trust level | HIGH (> 80), MEDIUM (40-80), LOW (< 40) |
| Total Purchases | Insights sold | 5 |
| Average Rating | Buyer satisfaction | 4.2/5 |

**Step-by-Step**:

1. **Type or Paste Seller Wallet**
   - Click address input field
   - Enter a seller wallet address (or use default)

2. **View Reputation Details**
   - System fetches reputation from Reputation contract
   - Shows current score and transaction history

3. **Review Trust Indicators**
   - Green = HIGH trust (> 80)
   - Yellow = MEDIUM trust (40-80)
   - Red = LOW trust (< 40)

**How Reputation Works**:
- Each successful purchase: seller reputation +10
- Reputation never decreases
- Agent uses reputation for buy/skip decisions
- Reputation tied to wallet address permanently

**Expected Behavior**:
- Reputation loads within 5 seconds
- Score updates after each purchase
- History shows all reputation-affecting transactions

---

### 8. About Page

**URL**: `http://localhost:5173/about`  
**Component**: `About.tsx`

**Purpose**: Project information and technical overview

**What You'll See**:
- Project description (agentic commerce on Algorand)
- Key features
- Technology stack
- Links to documentation

---

## Complete Demo Scenario

Follow this workflow to demonstrate all core features in sequence:

### Scenario: Seller Lists Insight → Agent Evaluates → Buyer Purchases → Reputation Updates

**Step 1: Seller Lists (2-3 minutes)**
1. Navigate to Home → "List a New Insight"
2. Enter sample insight: "Buy NIFTY above 24500..."
3. Set price: 0.5 USDC
4. Enter seller wallet address
5. Click "List Insight on Algorand"
6. Wait for success message with TX ID
7. Copy the TX ID and note listing ID (if displayed)

**Step 2: Discover Available Listings (1 minute)**
1. Navigate to Home → "Discover Insights"
2. Verify your newly created insight appears in the list
3. Review insight details (price, seller reputation)
4. Click "Purchase" button

**Step 3: Complete Purchase (2-3 minutes)**
1. Enter buyer wallet address (different from seller)
2. Click "Proceed to Payment"
3. Wait for payment processing (spinner shows progress)
4. Wait for success message with 3 TX IDs:
   - Payment TX
   - Redeem TX
   - Reputation TX

**Step 4: View Receipts and Ledger (1 minute)**
1. Click "View Receipt" link
2. Verify transaction details
3. Click "View on Block Explorer"
4. Return to home, navigate to "Activity Ledger"
5. Verify new listing and purchase appear in history

**Step 5: Check Reputation System (1 minute)**
1. Navigate to "Trust" page
2. Enter seller wallet address
3. Verify reputation increased by +10
4. Note that score is now visible in all future searches

**Total Demo Time**: 8-12 minutes

---

## Testing All Features Checklist

Use this checklist to verify all features work correctly:

- [ ] **Listing Creation**
  - [ ] Can enter insight text
  - [ ] Can set price 0.000001 to 5.0 USDC
  - [ ] Can enter seller wallet
  - [ ] Form validates empty fields
  - [ ] TX ID shown on success
  - [ ] Demo purchase executes automatically
  - [ ] Error handling for invalid wallet

- [ ] **Discovery**
  - [ ] Listings load on page
  - [ ] Can see newly created listings
  - [ ] Can filter/sort (if implemented)
  - [ ] Click purchase redirects to checkout

- [ ] **Payment Processing**
  - [ ] Can enter buyer wallet
  - [ ] Can see price confirmation
  - [ ] Payment processes without error
  - [ ] All 3 TX IDs displayed
  - [ ] Escrow release confirmed
  - [ ] Insight text displayed

- [ ] **Receipt and Proof**
  - [ ] TX IDs clickable to explorer
  - [ ] Buyer/seller addresses correct
  - [ ] Timestamp displays correctly
  - [ ] Block explorer shows confirmed transaction

- [ ] **Activity Ledger**
  - [ ] New listings appear
  - [ ] Purchase transactions appear
  - [ ] Reputation updates appear
  - [ ] Chronological ordering correct
  - [ ] Activity links work

- [ ] **Reputation System**
  - [ ] Can look up seller by address
  - [ ] Score shows +10 after purchase
  - [ ] Reputation history shows all updates
  - [ ] Trust color indicator works

- [ ] **Error Handling**
  - [ ] Invalid addresses rejected
  - [ ] Missing fields show validation
  - [ ] Payment limit enforced (6.0 USDC rejected)
  - [ ] Low balance shows clear error
  - [ ] Network errors show helpful message

---

## Troubleshooting Demo Issues

### Frontend Won't Load

**Symptom**: `http://localhost:5173` shows blank page or "cannot connect"

**Solution**:
```bash
cd frontend
npm run dev
# Wait for "Local: http://localhost:5173"
```

### Backend Not Responding

**Symptom**: Form submission hangs, no error after 30 seconds

**Solution**:
```bash
# Check backend is running
curl http://localhost:8000/health

# If not running:
cd backend
python -m uvicorn main:app --reload --port 8000
```

### "Cannot read property of undefined"

**Symptom**: React component error in console

**Solution**:
1. Check `ALGOD_URL` and `INDEXER_URL` in `.env.testnet`
2. Check smart contract app IDs are set
3. Restart frontend: `cd frontend && npm run dev`

### Transaction Simulation Failed

**Symptom**: "Transaction simulation failed" error during payment

**Solutions**:
1. Fund buyer wallet: Use [TestNet Dispenser](https://dispenser.testnet.algoexplorerapi.io/)
2. Opt-in to USDC: Use Pera Wallet or Algosigner to opt-in to ASA 10458941
3. Check USDC balance: Buyer needs at least price + 0.25 Algo for fees

### "Application index not found"

**Symptom**: Smart contract app ID errors

**Solution**:
1. Verify contracts deployed (see [SETUP.md](SETUP.md))
2. Update `.env.testnet` with correct app IDs
3. Restart backend: `Ctrl+C` then re-run

### All Features Work Except Automatic Demo Purchase

**Symptom**: Listing created successfully, but "Demo purchase result" section empty

**Possible Causes**:
- `GEMINI_API_KEY` not set (agent can't evaluate)
- `PINATA_JWT` not set (can't fetch insight)
- Agent timeout (semantic search too slow)

**Solution**:
1. Manually complete a purchase (see Step 3-4 of demo scenario)
2. Or check `agent_demo.log` for detailed error
3. See [SETUP.md](SETUP.md) to configure missing API keys

---

## Next Steps

- See [TESTS.md](TESTS.md) to run automated regression tests
- See [COMPONENTS.md](COMPONENTS.md) for proof artifacts and code examples
- See [ALGORAND.md](ALGORAND.md) for technical contract details
- See [SECURITY.md](SECURITY.md) for security audit and compliance
