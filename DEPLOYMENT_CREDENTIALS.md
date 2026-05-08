# Mercator Reputation System: Deployment Credentials

This document lists all credentials and configuration required to deploy the on-chain reputation system to Algorand TestNet.

## Prerequisites

- **Algokit**: CLI tool for Algorand contract deployment. Install: `brew install algorand-foundation/tap/algokit`
- **Node.js & npm**: For frontend build and contract TypeScript compilation
- **Python 3.10+**: For backend and AlgoKit Python scripts

## Required Environment Variables

### 1. Algorand Node Connectivity

```bash
ALGOD_SERVER=https://testnet-api.algonode.cloud
ALGOD_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
INDEXER_URL=https://testnet-idx.algonode.cloud
INDEXER_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
```

**Details**:
- **ALGOD_SERVER**: Public TestNet algod endpoint (AlgoNode free tier recommended)
- **ALGOD_TOKEN**: Authentication token (AlgoNode uses dummy token for public endpoints)
- **INDEXER_URL**: Public TestNet indexer endpoint (for historical queries)
- **INDEXER_TOKEN**: Authentication token

**Alternatives**:
- PureStake API (if AlgoNode unavailable)
- Local Algorand sandbox (for testing; requires Docker)

---

### 2. Deployer Account

```bash
DEPLOYER_MNEMONIC="word1 word2 word3 ... word25"
DEPLOYER_ADDRESS=ACCOUNTASDFASDFASDFASDFASDFASDFASDFASDFASDFASDFASDFASDFA3Q
```

**Details**:
- **DEPLOYER_MNEMONIC**: 25-word recovery phrase for account with TestNet ALGO funding
- **DEPLOYER_ADDRESS**: Derived public address (for reference/logging)

**Requirements**:
- Must have ≥ 10 ALGO balance (covers contract creation fees + transactions)
- Fund via [AlgoFaucet](https://testnet.algoexplorer.io/dispenser) if needed

**Creation** (if new):
```bash
algokit account new
# Saves mnemonic; fund with faucet
```

---

### 3. Treasury Account

```bash
TREASURY_ADDRESS=TREASURYADDRESSASDFASDFASDFASDFASDFASDFASDFASDFASDFA3Q
```

**Details**:
- **TREASURY_ADDRESS**: Account receiving fee income from x402 micropayments and subscriptions
- Can be same as DEPLOYER_ADDRESS or different account
- Must exist on TestNet (no fund requirement; fees are transferred TO it)

---

### 4. USDC Token ID (TestNet)

```bash
USDC_ASSET_ID=10458941
```

**Details**:
- **Fixed for TestNet**: The USDCe (USDC Ecosystem) asset on Algorand TestNet
- Do NOT change unless using different stablecoin
- Automatically opt-in by FeeConfig and Escrow contracts

---

### 5. Contract App IDs (Post-Deployment)

After initial deployment, capture these new IDs from deployment logs:

```bash
REPUTATION_APP_ID=1234567890
ESCROW_APP_ID=1234567891
FEECONFIG_APP_ID=1234567892
LISTING_APP_ID=1234567893
SUBSCRIPTION_MANAGER_APP_ID=1234567894
INSIGHT_LISTING_APP_ID=1234567895
```

**Details**:
- Generated automatically on first deployment
- Reputation app **must** be passed to Escrow constructor in subsequent redeploys
- Update `.env` after first deploy; commit to repo for reproducibility

---

## Deployment Workflow

### Step 1: Create `.env` File

```bash
cat > .env << 'EOF'
# Algorand Connectivity
ALGOD_SERVER=https://testnet-api.algonode.cloud
ALGOD_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
INDEXER_URL=https://testnet-idx.algonode.cloud
INDEXER_TOKEN=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa

# Deployer Account (fund via faucet if new)
DEPLOYER_MNEMONIC="your 25-word mnemonic here"
DEPLOYER_ADDRESS="YOURADDRESSHEREQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ3Q"

# Treasury Account (receives fees)
TREASURY_ADDRESS="TREASURYADDRESSQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQQ3Q"

# USDC Token (fixed for TestNet)
USDC_ASSET_ID=10458941

# Contract IDs (fill after first deployment)
REPUTATION_APP_ID=
ESCROW_APP_ID=
FEECONFIG_APP_ID=
LISTING_APP_ID=
SUBSCRIPTION_MANAGER_APP_ID=
INSIGHT_LISTING_APP_ID=
EOF
```

### Step 2: Verify Connectivity

```bash
# Test algod connection
curl -H "X-Algo-API-Token: $ALGOD_TOKEN" "$ALGOD_SERVER/health" | jq

# Test indexer connection
curl -H "X-Algo-API-Token: $INDEXER_TOKEN" "$INDEXER_URL/health" | jq
```

### Step 3: Deploy Reputation Contract

```bash
cd backend/contracts/reputation

# Build contract (generates TEAL)
algokit compile python smart_contracts/reputation/contract.py

# Deploy to TestNet
algokit deploy --environment testnet

# Capture REPUTATION_APP_ID from output
# Update .env with the new ID
```

### Step 4: Deploy Escrow Contract (with Reputation Integration)

```bash
cd backend/contracts/escrow

# Update contract to include reputation_app_id parameter from Step 3
# Escrow.__init__ must receive REPUTATION_APP_ID

algokit compile python smart_contracts/escrow/contract.py
algokit deploy --environment testnet --app-client-arguments reputation_app_id=$REPUTATION_APP_ID
```

### Step 5: Deploy Remaining Contracts

```bash
# FeeConfig
cd backend/contracts/fee_config
algokit deploy --environment testnet

# InsightListing
cd backend/contracts/insight_listing
algokit deploy --environment testnet

# SubscriptionManager
cd backend/contracts/subscription_manager
algokit deploy --environment testnet
```

### Step 6: Update Backend Configuration

```bash
# Update backend/main.py and FastAPI endpoints with new app IDs
# Example: Set REPUTATION_APP_ID in AlgorandClient initialization
export REPUTATION_APP_ID=<from-step-3>
export ESCROW_APP_ID=<from-step-4>
```

### Step 7: Start FastAPI Backend

```bash
cd backend

# Install dependencies
pip install -r requirements.txt

# Run with deployed app IDs
export ALGOD_SERVER ALGOD_TOKEN INDEXER_URL INDEXER_TOKEN REPUTATION_APP_ID ESCROW_APP_ID
python main.py
```

### Step 8: Build and Deploy Frontend

```bash
cd frontend

# Install dependencies
npm install

# Build (vite)
npm run build

# Deploy built artifacts to hosting (Render, Vercel, etc.)
# Point VITE_API_URL to backend from Step 7
export VITE_API_URL=https://your-backend-url
npm run build
npm run preview
```

---

## Credential Security Best Practices

1. **Never commit `.env` to version control**
   ```bash
   # In .gitignore
   .env
   .env.local
   .env.*.local
   ```

2. **Use GitHub Secrets for CI/CD**
   ```yaml
   # .github/workflows/deploy.yml
   env:
     DEPLOYER_MNEMONIC: ${{ secrets.DEPLOYER_MNEMONIC }}
     ALGOD_TOKEN: ${{ secrets.ALGOD_TOKEN }}
   ```

3. **Rotate credentials if exposed**
   - Create new DEPLOYER_ADDRESS account
   - Update Treasury address if compromised
   - Redeploy all contracts with new credentials

4. **Separate credentials by environment**
   - **TestNet** (.env.testnet): Test accounts, public endpoints
   - **MainNet** (.env.mainnet): Production account, AlgoNode premium, multi-sig if possible

---

## Troubleshooting Deployment

### Issue: "Account not found"
- **Cause**: Deployer account doesn't exist on TestNet
- **Solution**: Fund the address using [AlgoFaucet](https://testnet.algoexplorer.io/dispenser)

### Issue: "Insufficient balance for transaction"
- **Cause**: Not enough ALGO in deployer account
- **Solution**: Each contract costs ~0.25 ALGO to create + transaction fees; ensure ≥10 ALGO

### Issue: "Contract creation rejected"
- **Cause**: TEAL compilation errors or invalid global/local state
- **Solution**: Run `algokit compile` to check syntax; verify Box storage bounds

### Issue: "Inner transaction failed"
- **Cause**: Escrow → Reputation inner call fails due to missing app ID
- **Solution**: Ensure `reputation_app_id` parameter passed to Escrow.__init__

### Issue: "Reputation endpoints return 500"
- **Cause**: Contract artifact not regenerated after deployment
- **Solution**: Re-run `algokit compile` in contract directories to generate client stubs

---

## Verification Steps

After deployment, verify the system is working:

```bash
# 1. Check contract state
curl http://localhost:8000/sellers/<testnet-wallet>/reputation

# 2. Verify response includes:
# - effective_score
# - raw_score
# - decay_points_applied
# - rounds_since_last_purchase
# - rounds_until_decay_starts
# - total_purchases
# - last_purchase_approx_date

# 3. Test WebSocket reputation_updated events
wscat -c ws://localhost:8000/ws

# 4. Monitor logs for inner transaction failures
tail -f logs/app.log | grep -i reputation
```

---

## Post-Deployment Checklist

- [ ] DEPLOYER_MNEMONIC stored securely (not in code)
- [ ] All contract IDs captured and updated in `.env`
- [ ] Backend endpoints return valid reputation data
- [ ] Frontend loads seller profiles with decay timers
- [ ] WebSocket broadcasts reputation_updated events
- [ ] Test x402 payment triggers reputation update
- [ ] Test subscription purchase triggers reputation update
- [ ] Verify decay formula with sample sellers (wait 30k+ rounds or mock in tests)
- [ ] Monitor transaction costs (should be ~6000 microALGO per purchase with reputation)
- [ ] Document any custom parameter changes (points_per_purchase, decay thresholds, etc.)

---

## Contract Parameters (Customizable)

If deploying with non-default values, update these in Reputation.__init__:

```python
# backend/contracts/reputation/smart_contracts/reputation/contract.py
self.points_per_purchase.value = 5        # Points per purchase (1-50)
self.decay_threshold_rounds.value = 30000 # Rounds before decay starts (~48 hours)
self.decay_rate_rounds.value = 10000      # 1 point per N rounds decay
self.min_score.value = 0                  # Floor for effective score
```

---

## Support

- **Algokit docs**: https://github.com/algorand/algokit-cli
- **Algorand JS SDK**: https://github.com/algorand/js-algorand-sdk
- **Algorand Python SDK**: https://github.com/algorand/py-algorand-sdk
- **TestNet Faucet**: https://testnet.algoexplorer.io/dispenser
- **TestNet Explorer**: https://testnet.algoexplorer.io/

