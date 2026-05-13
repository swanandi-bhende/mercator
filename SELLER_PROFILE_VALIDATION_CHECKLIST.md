# Seller Profile Feature - Manual Validation Checklist (Task 15.10)

## Objective
Validate that the complete seller profile feature works end-to-end on staging, including data aggregation, display accuracy, and all 6 page sections rendering correctly.

---

## Pre-Validation Setup

### Prerequisites
- [ ] Backend server running on staging with latest seller profile endpoints
- [ ] Frontend built and deployed with new SellerProfile page and routes
- [ ] Database initialized with seller profile schema (views, tables, triggers)
- [ ] Test wallet with USDC balance for purchases
- [ ] Test seller wallet ready (can be different from buyer wallet)

### Environment Checks
- [ ] Verify GET `/sellers/leaderboard` returns top sellers (2xx response, 5+ sellers)
- [ ] Verify GET `/sellers/{test_wallet}/profile` returns profile data (2xx, non-empty stats)
- [ ] Verify trust summary is not empty for active sellers
- [ ] Confirm websocket connections active for reputation_updated events

---

## Purchase Flow - Three Sales from Same Seller

### Purchase 1: Seed First Transaction
1. Navigate to `/discover` page
2. Enter search query (e.g., "NIFTY breakout setup today")
3. Note the seller wallet address that appears in top result
4. Record seller wallet: ________________
5. Click on a listing from this seller
6. Complete checkout and payment
7. Verify transaction success (check `/transaction` page shows completed)
8. **Confirm purchase 1 recorded in flow_events table:**
   - [ ] Check backend logs for `escrow.release_completed` event
   - [ ] Verify seller wallet in metadata matches target seller

### Purchase 2: Second Transaction from Same Seller
1. Return to `/discover`
2. Search for another insight from the SAME seller wallet (use `?seller=WALLET` filter or manual search)
3. Complete second purchase
4. Verify success on `/transaction`
5. **Confirm purchase 2 added:**
   - [ ] Check PostgreSQL/SQLite flow_events has 2 entries for this seller

### Purchase 3: Third Transaction from Same Seller
1. Return to `/discover`
2. Find a third insight from the same seller
3. Complete third purchase
4. Verify success
5. **Confirm all 3 purchases recorded:**
   - [ ] Query: `SELECT COUNT(*) FROM flow_events WHERE wallet_involved = 'SELLER_WALLET' AND event_name = 'escrow.release_completed'`
   - [ ] Should return 3

---

## Seller Profile Page Validation

### Navigate to Profile
1. Go to URL: `http://staging.mercator.local/sellers/{SELLER_WALLET}`
   - Replace `{SELLER_WALLET}` with the 58-character Algorand address
2. Verify page loads within 3 seconds
3. Check no error messages appear

---

## Section 1: Profile Header ✓

### Rendering Checks
- [ ] Large avatar circle displays with deterministic color (HSL based on wallet hash)
- [ ] Display name shown (or "Anonymous Seller" if not registered)
- [ ] Truncated wallet address shown (first 8 + last 4 characters with ellipsis)
- [ ] Copy-to-clipboard button visible next to wallet
- [ ] Verification badge present:
  - If registered: Green "✓ Verified Agent" badge + role badge (e.g., "Curator Agent")
  - If unregistered: Grey "Unverified Seller" badge

### Data Accuracy
- [ ] Wallet address shown matches URL parameter
- [ ] Badge color matches expected role (purple for Curator, blue for Buyer, orange for Human)
- [ ] Large reputation score circle displays with color gradient matching score tier (green ≥80, blue 70-79, orange 50-69, red <50)

### Screenshot #1 - Profile Header
- [ ] Take screenshot of header section
- [ ] Save as: `testnet-evidence/round3/seller_profiles/01-header.png`

---

## Section 2: Stats Grid ✓

### Rendering Checks
- [ ] Four stat cards displayed in grid layout:
  1. **Total Insights Sold** - should show 3 (from our 3 purchases)
  2. **Total USDC Earned** - sum of all purchase amounts
  3. **Average Price** - average per insight
  4. **Days Active** - calculated from first_listing_date

### Data Accuracy (Critical)
- [ ] **Total Insights Sold = 3** ✓ (MUST BE EXACT)
  - If not 3, check: was a 4th listing created? Did a purchase fail to record?
  - Debug: `SELECT COUNT(DISTINCT json_extract(metadata, '$.listing_id')) FROM flow_events WHERE wallet_involved = 'SELLER' AND event_name = 'listing.asa_creation_completed'`

- [ ] **Total USDC Earned = SUM of three purchase amounts** ✓
  - Should match: `SELECT SUM(CAST(json_extract(metadata, '$.amount_usdc') AS REAL)) FROM flow_events WHERE wallet_involved = 'SELLER' AND event_name = 'escrow.release_completed'`

- [ ] **Average Price ≈ Total USDC / 3** ✓
  - Should be consistent with stats shown

- [ ] **Days Active > 0** ✓
  - Should reflect time since first listing creation

### Screenshot #2 - Stats Grid
- [ ] Take screenshot of four stat cards
- [ ] Save as: `testnet-evidence/round3/seller_profiles/02-stats-grid.png`

---

## Section 3: Reputation Panel ✓

### Rendering Checks
- [ ] Large circular score display (e.g., "42/100" in colored circle)
- [ ] Progress bar with fill showing percentage (0-100)
- [ ] Two threshold markers on progress bar:
  - "50" threshold (trust minimum)
  - "70" threshold (high tier)
- [ ] Decay info displayed (if applicable):
  - "Decay Applied: -X points"
- [ ] **AreaChart sparkline visible** (CRITICAL - uses Recharts)
  - X-axis: timestamps of reputation changes
  - Y-axis: 0-100 scale
  - Area fill with gradient color (matches avatar color)
  - Should show last 20 reputation score updates

### Data Accuracy
- [ ] **Reputation score is between 0-100** ✓
- [ ] **Score displays consistently** (same value across page sections) ✓
- [ ] **Sparkline shows at least 1 point** (should increase with purchases if reputation updates)
  - If sparkline empty: Check if reputation_updated websocket event fires after escrow release

### Sparkline Data Points (FROM REPUTATION HISTORY)
- [ ] Hover over sparkline points, verify:
  - Score increases monotonically (or flat) across timeline
  - Dates show recent to older
  - Last point matches current effective score
- [ ] **Count sparkline points: should be ≤ 20** (max 20 entries per seller, older pruned)

### Screenshot #3 - Reputation Panel with Sparkline
- [ ] Take screenshot including the full AreaChart
- [ ] **Ensure sparkline is visible with at least 3 data points**
- [ ] Save as: `testnet-evidence/round3/seller_profiles/03-reputation-sparkline.png`

---

## Section 4: Listing History (Paginated) ✓

### Rendering Checks
- [ ] Table header: Price | Purchases | Date | Action
- [ ] **3 rows visible** (one for each listing created during purchases)
  - If < 3 rows: Check if all purchases triggered listing.asa_creation_completed events

### Data Accuracy
- [ ] **Exactly 3 listings shown on page 1** ✓
  - Each row should have:
    - Price in USDC (e.g., "2.50 USDC")
    - Purchase count (should be ≥1 for each, since we just purchased)
    - Date (should be recent, within last hour or so)
    - View button

- [ ] **Purchase count aggregation correct:**
  - Each listing should show the count of times it was purchased
  - Our 3 separate listings should show 1 purchase each (or more if same listing purchased multiple times)

### Pagination Checks
- [ ] If ≤10 listings total: No pagination controls shown
- [ ] If >10 listings: "Previous" and "Next" buttons visible
  - Pagination info shows: "Page 1 of X"
  - "Previous" button disabled on page 1
  - "Next" button enabled if more pages exist

### Screenshot #4 - Listing History Table
- [ ] Take screenshot showing all 3 listings
- [ ] Verify row count clearly shows 3
- [ ] Save as: `testnet-evidence/round3/seller_profiles/04-listing-history.png`

---

## Section 5: Agent Evaluations History ✓

### Rendering Checks
- [ ] Table header: Quality | Relevance | Total Score | Decision | Date
- [ ] Rows displayed for each evaluation from Buyer Agent
  - Should show evaluation records for our 3 purchases

### Data Accuracy
- [ ] **Evaluations from Buyer Agent visible** ✓
  - Each row shows: quality_score, relevance_score, total_score, decision, created_at
  - Decision badges: "BUY", "SKIP", or other Buyer Agent decision
  - Scores are numeric (0-100 or similar scale)

- [ ] **At least 3 evaluation records displayed** (one per purchase, assuming Buyer Agent evaluated each)
  - If fewer: Check if evaluations table has records for this seller

- [ ] **Decision badges colored appropriately:**
  - BUY = green badge
  - SKIP = purple/red badge

### Screenshot #5 - Evaluation History
- [ ] Take screenshot of evaluations table
- [ ] Ensure at least 3 rows visible
- [ ] Save as: `testnet-evidence/round3/seller_profiles/05-evaluations.png`

---

## Section 6: Trust Summary ✓

### Rendering Checks
- [ ] Text box displays 2-3 sentences of auto-generated summary
- [ ] Text is readable and grammatically correct
- [ ] Summary mentions seller's metrics (sales count, reputation, evaluation feedback)

### Content Accuracy
- [ ] Summary should include:
  - Seller's sales count: "has sold 3 insight(s)" or similar
  - Reputation tier language: "trusted", "developing", or similar category based on score
  - Evaluation feedback: "Buyer Agent rates their insights as..." or similar

- [ ] Special case - Curator Agent:
  - If seller is a Curator Agent: Summary should start with "This is Mercator's automated Curator Agent..."

### Sample Expected Summary (non-curator):
```
"[Seller Name] has sold 3 insight(s) with a reputation score of 42/100, 
placing them in the developing seller category. The Buyer Agent has rated their 
insights as moderate quality on average with mixed evaluations."
```

### Screenshot #6 - Trust Summary
- [ ] Take screenshot of the trust summary box
- [ ] Save as: `testnet-evidence/round3/seller_profiles/06-trust-summary.png`

---

## Integration Tests

### SellerCard Component in DiscoverInsights
- [ ] Navigate to `/discover`
- [ ] Execute search
- [ ] In results grid, verify:
  - [ ] Each listing shows `<SellerCard wallet={seller_wallet} />` instead of plain text
  - [ ] SellerCard displays: avatar + name/role + reputation badge + "→" arrow
  - [ ] Click SellerCard navigates to `/sellers/{wallet}` ✓

### SellerCard in InsightDetail (About this Seller)
- [ ] Navigate to `/discover` and select a listing
- [ ] On evaluation page (`/evaluate`), scroll to find "About this Seller" section
- [ ] Click to expand "About this Seller"
- [ ] Verify expanded SellerCard shows:
  - [ ] Full profile header with avatar
  - [ ] Stats grid
  - [ ] Reputation badge
  - [ ] Trust summary
  - [ ] "View Full Profile →" button navigates to seller profile ✓

### Top Sellers Leaderboard (Sidebar)
- [ ] Navigate to `/discover`
- [ ] In right sidebar, look for "Top Sellers" panel
- [ ] Verify 5 SellerCards displayed in ranked order
- [ ] Click on any seller card in leaderboard → navigates to `/sellers/{wallet}` ✓

---

## Performance Checks

### Page Load Time
- [ ] Profile page loads in < 2 seconds (Tier 1+2 data)
- [ ] Listing history loads within 3 seconds
- [ ] No console errors or warnings

### Cache Efficiency
- [ ] Reload `/sellers/{wallet}` page
- [ ] Verify data loads quickly (should hit cache)
- [ ] API request count should be lower on second load (browser dev tools)

### Reputation Sparkline
- [ ] Chart renders smoothly with no visual glitches
- [ ] Hover tooltips appear on data points
- [ ] Chart is responsive on mobile (if testing mobile)

---

## Final Validation Document Assembly

### Create testnet-evidence Directory
```bash
mkdir -p testnet-evidence/round3/seller_profiles
```

### Collect All Screenshots
- [ ] 01-header.png
- [ ] 02-stats-grid.png
- [ ] 03-reputation-sparkline.png (CRITICAL - must show sparkline with ≥3 points)
- [ ] 04-listing-history.png (CRITICAL - must show 3 listings)
- [ ] 05-evaluations.png
- [ ] 06-trust-summary.png

### Create Validation Report
Create `testnet-evidence/round3/seller_profiles/VALIDATION_REPORT.md`:

```markdown
# Seller Profile Feature - Manual Validation Report

**Date:** [TODAY]
**Tested By:** [YOUR NAME]
**Seller Wallet Tested:** [SELLER_WALLET_ADDRESS]
**Test Environment:** Staging

## Summary
✓ All 6 sections of seller profile page render correctly
✓ 3 purchases from same seller aggregated accurately
✓ Reputation sparkline shows score changes
✓ Listing history shows correct 3 listings
✓ Agent evaluations displayed
✓ Trust summary auto-generated
✓ SellerCard integrated into DiscoverInsights
✓ SellerCard integrated into InsightDetail
✓ Top Sellers leaderboard functional

## Key Metrics Verified
- Total Purchases: 3 ✓
- Total USDC Earned: [AMOUNT] ✓
- Average Price: [AMOUNT] ✓
- Reputation Score: [SCORE]/100 ✓
- Days Active: [DAYS] ✓

## Screenshots
See attached PNG files in this directory.
```

### Save Complete Screenshot
- [ ] Take one full-page screenshot: `testnet-evidence/round3/seller_profiles/complete_profile_after_3_purchases.png`

---

## Troubleshooting Guide

| Issue | Debug Steps |
|-------|-----------|
| **Total Purchases ≠ 3** | Check flow_events table for `escrow.release_completed` with seller wallet |
| **Sparkline empty** | Check reputation_score_history table; verify WebSocket reputation_updated events firing |
| **Listing history empty** | Verify `listing.asa_creation_completed` events in flow_events |
| **Evaluations empty** | Check evaluations table for seller_wallet matches |
| **Trust summary missing** | Verify seller_trust_summary_cache table; check build_trust_summary logic |
| **SellerCard not showing** | Check browser console for import errors; verify SellerCard.tsx exists |
| **404 on /sellers/{wallet}** | Verify route added to App.tsx; check wallet format (58 chars) |

---

## Sign-Off

- [ ] All 6 sections render correctly
- [ ] Data aggregation accurate for 3 purchases
- [ ] Reputation sparkline shows historical data
- [ ] SellerCard integrated and functional
- [ ] No console errors or warnings
- [ ] Page performance acceptable (<2s load)
- [ ] All screenshots captured and saved
- [ ] Validation report completed

**Validation Status:** ✓ COMPLETE / ✗ NEEDS FIXES

---

## Notes
```
[Add any observations, issues encountered, or additional context here]


```
