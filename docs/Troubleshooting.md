# Troubleshooting Guide

Quick solutions for common issues when developing, testing, and deploying Mercator.

---

## Setup & Environment

### `ModuleNotFoundError: No module named 'backend'`

**Problem**: Python can't find the backend module

**Solution**:
```bash
# Set PYTHONPATH before running
export PYTHONPATH=$(pwd)

# Then run your command
pytest backend/tests/
```

Or use the virtual environment Python:
```bash
.venv/bin/python -m pytest backend/tests/
```

### `pip install: command not found`

**Problem**: pip not available or not in PATH

**Solution**:
```bash
# Use Python module form
python3 -m pip install -r backend/requirements.txt

# Or ensure virtual env is activated
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### `ModuleNotFoundError: No module named 'uvicorn'`

**Problem**: FastAPI server won't start

**Solution**:
```bash
# Install specific dependency
pip install uvicorn

# Or reinstall all requirements
pip install -r backend/requirements.txt

# Start backend with correct path
PYTHONPATH=. python -m uvicorn backend.main:app --reload
```

### `.env.testnet file not found`

**Problem**: Application crashes with missing environment file

**Solution**:
```bash
# Create .env.testnet in project root
cat > .env.testnet << 'EOF'
ALGOD_URL=https://testnet-api.algonode.cloud
INDEXER_URL=https://testnet-idx.algonode.cloud
NETWORK=testnet

INSIGHT_LISTING_APP_ID=1234567
ESCROW_APP_ID=1234568
REPUTATION_APP_ID=1234569

USDC_ASA_ID=10458941
USDC_DECIMALS=6

SELLER_ADDRESS="your-testnet-address"
SELLER_MNEMONIC="your-25-word-seed"

GEMINI_API_KEY="your-api-key"
PINATA_JWT="your-jwt-token"
EOF
```

### `error: No such file or directory: 'npm'`

**Problem**: Node.js/npm not installed

**Solution**:
```bash
# Verify Node.js is installed
node --version  # Should be v18+

# If not installed:
# macOS: brew install node
# Linux: apt install nodejs npm
# Windows: Download from nodejs.org
```

---

## Algorand & Wallet Issues

### `ConnectionError: Cannot connect to ALGOD_URL`

**Problem**: Backend can't reach Algorand node

**Solution**:
```bash
# Verify endpoint is accessible
curl https://testnet-api.algonode.cloud/health

# Check .env.testnet has correct URL
# Should be: ALGOD_URL=https://testnet-api.algonode.cloud

# Not localhost unless you're running a local node
# Not http:// (must be https://)
```

### `Error: USDC balance = 0`

**Problem**: TestNet USDC not available

**Solution**:
```bash
# 1. Get TestNet ALGO first
Visit: https://bank.testnet.algorand.org
Enter: Your wallet address
Get: 10+ ALGO

# 2. Opt-in to USDC ASA (10458941)
# Use Pera Wallet:
# - Open Pera Wallet
# - Search ASA #10458941
# - Click "Add asset"

# 3. Ask for USDC on Discord
Discord: https://discord.gg/algorand
Channel: #testnet
Message: "Need TestNet USDC, here's my address: ..."

# 4. Create second test account
# Transfer ALGO to second account
# Opt-in to USDC on second account
```

### `Error: Invalid Algorand address`

**Problem**: Address format is wrong

**Solution**:
```bash
# Valid TestNet address format:
# 58 characters
# Starts with letter (not 0)
# Alphanumeric only
# Includes checksum

# Example valid address:
IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4

# Common mistakes:
# - 0x prefix (Ethereum format): [Invalid]
# - Too short (< 58 chars): [Invalid]
# - Special characters: [Invalid]
# - Invalid checksum: [Invalid]
```

### `Error: App ID not found`

**Problem**: Smart contract not deployed or wrong app ID

**Solution**:
```bash
# Verify app exists on-chain
curl "https://testnet-idx.algonode.cloud/v2/applications/{APP_ID}"

# If 404: Contract not deployed
# Deploy contract and get app ID:
PYTHONPATH=. python backend/contracts/insight_listing.py

# Save returned app ID
# Update .env.testnet with correct ID

# Verify network matches:
# TestNet contracts have IDs < 1,000,000
# MainNet contracts have IDs > 1,000,000
```

### `Transaction group size exceeded (16 max)`

**Problem**: Too many transactions in atomic group

**Solution**:
```bash
# Mercator uses 3 transactions per payment:
# 1. ASA Transfer (USDC)
# 2. Escrow Release
# 3. Reputation Update

# If error, check that:
# - Not adding extra transactions
# - Not reusing same group multiple times
# - Atomic group properly closed

# Max 16 transactions per group, so Mercator is well under
```

---

## Payment & Transaction Issues

### `Payment rejected: insufficient balance`

**Problem**: Buyer doesn't have enough USDC

**Solution**:
```bash
# Check current USDC balance
# In Pera Wallet: See Assets tab

# Get more USDC:
# 1. Get TestNet ALGO (see above)
# 2. Trade ALGO for USDC on testnet exchange (if available)
# 3. Ask Discord for USDC transfer

# For testing with unlimited balance:
# Set in .env.testnet during development
# (Don't use in production)
```

### `Error: User approval required. Type 'approve'`

**Problem**: User didn't confirm payment

**Cause**: This is expected behavior, not an error!

**Solution**:
```bash
# When prompted for payment, type exactly:
approve

# Not:
# - "Approve" (capital A)
# - "yes" or "ok"
# - Empty input

# Only exact match "approve" proceeds to payment
```

### `Transaction timeout (did not confirm in 4 blocks)`

**Problem**: Transaction was submitted but didn't finalize

**Solution**:
```bash
# This is rare on TestNet
# Try again - the transaction may be in mempool

# If repeats:
# 1. Check Algorand TestNet status
#    https://status.algorand.org

# 2. Wait a few minutes and retry

# 3. If using local node, check node health
#    curl http://localhost:4001/health

# 4. Check transaction on explorer
#    https://testnet.algoexplorer.io/
```

### `Escrow release failed`

**Problem**: Escrow contract call failed

**Solution**:
```bash
# Check error message for details:
# Common causes:
# 1. App not opted into USDC asset
#    → Smart contract needs: "asset 10458941" in foreign assets

# 2. Seller address not passed to app
#    → Ensure seller address in Accounts field

# 3. Amount validation failed
#    → Check amount > 0 and < MAX_PAYMENT (5.0 USDC)

# Debug: View transaction on explorer
https://testnet.algoexplorer.io/tx/{TX_ID}
```

---

## Frontend & Browser Issues

### `Error: VITE_API_BASE not set`

**Problem**: Frontend can't connect to backend

**Solution**:
```bash
# Create .env.local in frontend/ directory:
VITE_API_BASE=http://localhost:8000
VITE_WS_BASE=ws://localhost:8000

# Or use production API for testing:
VITE_API_BASE=https://mercator-reka.onrender.com
VITE_WS_BASE=wss://mercator-reka.onrender.com

# Restart frontend dev server
npm run dev
```

### `Blank page or "Cannot GET /"`

**Problem**: Frontend not running or wrong port

**Solution**:
```bash
# Verify frontend is running
npm run dev
# Should show: "VITE v5.x.x ready in 123ms"

# Check port 5173 is accessible
# http://localhost:5173 in browser

# If not working:
# 1. Kill any process on port 5173
#    lsof -i :5173
#    kill -9 <PID>

# 2. Clear vite cache
#    rm -rf frontend/node_modules/.vite

# 3. Restart dev server
#    npm run dev
```

### `Wallet connection failed`

**Problem**: Cannot connect to Pera Wallet

**Solution**:
```bash
# 1. Install Pera Wallet browser extension
#    https://www.perawallet.app/

# 2. Create TestNet account in wallet
#    (Select "TestNet" in wallet settings)

# 3. Reload browser page
#    wallet connection should work

# 4. If still failing:
#    - Check browser console (F12)
#    - Look for specific error message
#    - Try incognito window
```

### `Transaction appears to hang after "approve"`

**Problem**: UI doesn't update after typing "approve"

**Solution**:
```bash
# Check backend logs for errors
# Terminal where you ran: python -m uvicorn backend.main:app

# If no error logs:
# 1. Verify backend is running on port 8000
#    curl http://localhost:8000/health

# 2. Check browser console (F12 → Console tab)
#    Look for network errors

# 3. Clear browser cache
#    Ctrl+Shift+Delete (Windows)
#    Cmd+Shift+Delete (Mac)
#    Select "All time" → Clear data
```

---

## Test Failures

### `pytest: command not found`

**Problem**: pytest not installed or not in PATH

**Solution**:
```bash
# Install pytest
pip install pytest pytest-asyncio

# Then run tests
PYTHONPATH=. pytest backend/tests/ -v

# If still not found:
# Use Python module form
python -m pytest backend/tests/ -v
```

### `Test passes locally but fails in CI/CD`

**Problem**: Environment difference between local and CI

**Common causes**:
- Different Python version
- Missing environment variables
- OS-specific file path issues

**Solution**:
```bash
# 1. Match Python version to CI
#    CI uses Python 3.12
#    Check: python --version

# 2. Set all env vars CI uses
#    Check: .github/workflows/test.yml

# 3. Run full CI simulation locally
#    docker run -v $(pwd):/app -w /app python:3.12 bash
#    Then: pip install -r backend/requirements.txt && pytest backend/tests/
```

### `Test hangs indefinitely`

**Problem**: Test process doesn't finish

**Solution**:
```bash
# Kill hanging test with timeout
timeout 30 pytest backend/tests/test_file.py

# If hangs: Probably waiting for async operation
# Check for:
# - Missing await keyword
# - Infinite loops
# - Unclosed connections

# Run with verbose output to see where it hangs
pytest backend/tests/ -v -s
```

---

## Deployment Issues (Vercel/Render)

### `Build failed on Vercel: npm install error`

**Problem**: Frontend dependencies won't install

**Solution**:
```bash
# 1. Check package.json for typos
#    Verify all dependencies are valid npm packages

# 2. Clear Vercel cache
#    Vercel dashboard → Settings → Caching
#    Click "Clear All"

# 3. Redeploy
#    Vercel dashboard → Redeploy

# 4. If still fails, test locally
#    rm -rf node_modules package-lock.json
#    npm install
#    npm run build
```

### `Backend deployment fails: Cannot import backend`

**Problem**: Render can't find Python modules

**Solution**:
```bash
# Check Dockerfile has correct PYTHONPATH
FROM python:3.12

WORKDIR /app
COPY . .

ENV PYTHONPATH=/app  # Must be set

# Test Dockerfile locally
docker build -t mercator .
docker run -e PYTHONPATH=/app mercator python -m uvicorn backend.main:app
```

### `Environment variables not working in production`

**Problem**: API returns 500 errors with missing env var

**Solution**:
```bash
# 1. Verify env vars set in Render dashboard
#    Render dashboard → Environment

# 2. Restart service after adding env vars
#    Render dashboard → Manual deploy

# 3. Check if env var names match code
#    Code: os.getenv('ALGOD_URL')
#    Render: Must be exactly: ALGOD_URL

# 4. Never include in start command
#    Don't do: CMD python -c "os.environ['VAR']='value'"
#    Do: Set in Render dashboard
```

---

## FAQ

### Q: How do I get TestNet USDC?

A: See [Algorand & Wallet Issues](#algorand--wallet-issues) section above.

### Q: Can I run tests without spending USDC?

A: Yes! Most tests use mock transactions. Only enable real transactions with:
```bash
TEST_REAL_TRANSACTIONS=true pytest backend/tests/
```

### Q: How do I check if a transaction succeeded?

A: View on explorer:
```
https://testnet.algoexplorer.io/tx/{TRANSACTION_ID}
```

### Q: My balance isn't updating after a purchase

A: Wait 5-10 seconds for block confirmation. Then:
```bash
# Refresh on explorer
curl https://testnet-idx.algonode.cloud/v2/accounts/{ADDRESS}
```

### Q: Can I reset TestNet accounts?

A: TestNet can reset monthly. Check Algorand status page:
```
https://status.algorand.org
```

### Q: How do I report a bug?

A: Create a GitHub issue with:
- Error message (full stack trace)
- Steps to reproduce
- Your `.env.testnet` (without secrets)
- Python/Node version

---

## Getting Help

**Documentation**:
- [Setup.md](Setup.md) - Initial setup
- [Demo.md](Demo.md) - How to run the app
- [Algorand_Implementation.md](Algorand_Implementation.md) - Blockchain details
- [Deploy.md](Deploy.md) - Production deployment

**Community**:
- **Algorand Discord**: https://discord.gg/algorand
- **GitHub Issues**: Post bugs with full context
- **Email**: Contact development team

**Advanced Debugging**:
```bash
# Enable verbose logging
export LOG_LEVEL=DEBUG
python -m uvicorn backend.main:app --reload

# Print all environment variables
python -c "import os; print({k: v for k, v in os.environ.items() if 'ALGO' in k or 'USDC' in k})"

# Check if contract state accessible
PYTHONPATH=. python -c "from backend.utils.algorand_async import get_app_state; import asyncio; print(asyncio.run(get_app_state(APP_ID)))"
```
