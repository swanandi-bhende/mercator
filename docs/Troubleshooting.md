# Troubleshooting Guide

Common issues and solutions when setting up, running, and testing Mercator.

## Setup and Installation

### "ModuleNotFoundError: No module named 'backend'"

**Symptom**: Python scripts crash with import errors

**Solution**:
```bash
# Set PYTHONPATH before running
export PYTHONPATH=$(pwd)

# Or run Python with -path
cd backend && python -m uvicorn main:app --reload

# Or from project root
PYTHONPATH=. python -m pytest backend/tests/
```

### "pip install: command not found"

**Symptom**: `pip: command not found` when installing dependencies

**Solution**:
```bash
# Use python module form
python3 -m pip install -r backend/requirements.txt

# Or ensure virtualenv is activated
source .venv/bin/activate
pip install -r backend/requirements.txt
```

### "ModuleNotFoundError: No module named 'uvicorn'"

**Symptom**: FastAPI won't start, missing uvicorn

**Solution**:
```bash
# Install missing dependency
pip install uvicorn

# Or reinstall full requirements
pip install -r backend/requirements.txt

# Then run backend
python -m uvicorn backend.main:app --reload
```

### "No such file or directory: .env.testnet"

**Symptom**: application crashes saying .env.testnet missing

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

DEPLOYER_MNEMONIC="your 25 word mnemonic here"
DEPLOYER_ADDRESS="your algorand address"
BUYER_MNEMONIC="buyer mnemonic"
BUYER_ADDRESS="buyer address"

GEMINI_API_KEY="your gemini key"
PINATA_JWT="your pinata jwt"
EOF

# Verify it exists
cat .env.testnet
```

---

## Algorand Network Issues

### "ConnectionError: cannot connect to Algorand node"

**Symptom**: 
```
ConnectionError: Cannot connect to https://testnet-api.algonode.cloud
```

**Causes**:
- Network is down
- Incorrect node URL
- Firewall blocking

**Solutions**:

1. **Test node connectivity**:
```bash
curl -s https://testnet-api.algonode.cloud/health | jq .
# Should show {"round": 12345678, "statusMessage": "OK", ...}
```

2. **Try alternative node**:
```bash
# In .env.testnet, try:
ALGOD_URL=https://api.testnet.algoexplorer.io
# or
ALGOD_URL=https://testnet-api.k1.jup.ag
```

3. **Check internet connection**:
```bash
# Simple connectivity test
curl https://www.google.com
```

### "App ID not found" or "Application index not found in account state"

**Symptom**:
```
IndexError: Application index [1234567] not found
```

**Causes**:
- Contract not deployed
- Wrong app ID in .env.testnet
- App ID belongs to different network

**Solutions**:

1. **Verify contracts are deployed**:
```bash
# Check if app ID exists on-chain
curl "https://testnet-idx.algonode.cloud/v2/applications/1234567"
# Should return detailed app info, not 404
```

2. **Redeploy contracts**:
```bash
cd backend/contracts/insight_listing/smart_contracts
python -m smart_contracts
# Note the returned app ID

# Update .env.testnet with new ID
INSIGHT_LISTING_APP_ID=<new-app-id>
```

3. **Verify you're on TestNet**:
```bash
# Check network setting
grep NETWORK .env.testnet
# Should be: NETWORK=testnet
```

### "Insufficient balance for this account"

**Symptom**: Transaction fails at simulation
```
Transaction simulation failed: insufficient balance for this account
```

**Solutions**:

1. **Fund your account**:
   - Visit [TestNet Dispenser](https://dispenser.testnet.algoexplorerapi.io/)
   - Enter your wallet address
   - Request funds (typically 10 Algo each)
   - Wait 1-2 minutes for confirmation

2. **Check balance**:
```bash
curl "https://testnet-idx.algonode.cloud/v2/accounts/${YOUR_ADDRESS}"
# Look for "amount" field (in microunits)
```

3. **Opt-in to USDC**:
   - Open Pera Wallet or Algosigner
   - Search for USDC asset (10458941)
   - Click "Opt-in"
   - Confirm the transaction

---

## Frontend Issues

### "http://localhost:5173 refused to connect"

**Symptom**: Browser shows "Cannot connect to server"

**Solutions**:

1. **Check if frontend is running**:
```bash
# Terminal 2
cd frontend
npm run dev

# Wait for: "Local: http://localhost:5173"
```

2. **Check if port 5173 is in use**:
```bash
# See what's using port 5173
lsof -i :5173

# Kill if needed
kill -9 <PID>
```

3. **Install dependencies**:
```bash
cd frontend
npm install
npm run dev
```

### "npm: command not found"

**Symptom**: `npm` not installed or not in PATH

**Solutions**:

1. **Install Node.js**:
   - macOS: `brew install node`
   - Linux: See https://nodejs.org/

2. **Verify installation**:
```bash
node --version   # Should show v18+
npm --version    # Should show 9.0.0+
```

### React component errors (console shows red errors)

**Symptom**: Browser console shows React errors like:
```
TypeError: Cannot read property 'map' of undefined
```

**Solutions**:

1. **Check backend is running**:
```bash
curl http://localhost:8000/health
# Should return {"status": "healthy"}

# If not, in Terminal 1:
python -m uvicorn backend.main:app --reload
```

2. **Check smart contract IDs**:
```bash
grep APP_ID .env.testnet
# All three should have values, not blanks
```

3. **Restart frontend**:
```bash
# Ctrl+C in frontend terminal
npm run dev
```

4. **Check browser console**:
   - Open DevTools (F12)
   - Click "Console" tab
   - Look for specific error message
   - Share the error in logs (next section)

---

## Backend API Issues

### "Connection refused" on http://localhost:8000

**Symptom**: Cannot reach backend API

**Solutions**:

1. **Start backend**:
```bash
# Terminal 1
source .venv/bin/activate
cd backend
python -m uvicorn main:app --reload --port 8000

# Wait for: "Uvicorn running on http://0.0.0.0:8000"
```

2. **Check port availability**:
```bash
lsof -i :8000
# If in use, kill or use different port
python -m uvicorn main:app --port 8001
```

3. **Verify backend health**:
```bash
curl http://localhost:8000/health
# Should return {"status": "ok"}
```

### "CORS error" in browser console

**Symptom**:
```
Access to XMLHttpRequest from origin 'http://localhost:5173' has been blocked by CORS policy
```

**Solution**:
The backend should have CORS enabled. Check `backend/main.py` has:

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
```

If missing, add it above the route definitions.

### "No such file or directory: backend/contracts/..."

**Symptom**: Backend crashes with import error for contracts

**Solution**:
```bash
# Ensure you're in project root
pwd
# Should show: /path/to/mercator

# Check contract files exist
ls backend/contracts/insight_listing/smart_contracts/insight_listing/contract.py
ls backend/contracts/escrow/smart_contracts/escrow/contract.py
ls backend/contracts/reputation/smart_contracts/reputation/contract.py

# If missing, they weren't deployed. See "Deploy Smart Contracts" in SETUP.md
```

---

## Payment and Transaction Issues

### "PAYMENT_LIMIT_EXCEEDED"

**Symptom**: Payment rejected with message "exceeds maximum micropayment limit"

**Cause**: Attempting to pay more than 5.0 USDC

**Solution**:
```bash
# Check MAX_MICROPAYMENT_USDC in x402_payment.py
grep MAX_MICROPAYMENT_USDC backend/tools/x402_payment.py

# If you need to change limit:
# Edit backend/tools/x402_payment.py
# Change: MAX_MICROPAYMENT_USDC = 5.0
# To: MAX_MICROPAYMENT_USDC = 10.0
```

### "PAYMENT_EXECUTION_FAILED - insufficient balance"

**Symptom**: Payment fails, "insufficient balance for this account"

**Solution**:
1. Fund buyer wallet from [TestNet Dispenser](https://dispenser.testnet.algoexplorerapi.io/)
2. Ensure buyer has opted-in to USDC ASA (10458941)
3. For testing, ensure at least 1 Algo + price in USDC

```bash
# Check buyer balance
curl "https://testnet-idx.algonode.cloud/v2/accounts/${BUYER_ADDRESS}"
```

### "INVALID_ADDRESS"

**Symptom**: "Payment failed: invalid buyer address format"

**Cause**: Wallet address not valid Algorand format

**Solution**:
```bash
# Valid Algorand address is:
# - 58 characters long
# - Starts with a letter (not a number)
# - Uses base32 encoding (A-Z, 2-7)

# Example: 
# IXPLWQSP5D7K2F4BLXNWY3PR6KKXVG44DAESMMZ2H27VYZQNXGVQZNWVM4

# Get valid address from wallet app:
# - Pera Wallet: Click "Copy Address"
# - Algosigner: Select account, copy address
```

### "CID must start with 'Qm'"

**Symptom**: Listing creation fails, "LISTING_STORE_ERROR: CID must start with 'Qm'"

**Cause**: IPFS upload failed, returned invalid CID

**Solutions**:

1. **Check Pinata JWT**:
```bash
grep PINATA_JWT .env.testnet
# Should have value, not blank
```

2. **Verify Pinata JWT is valid**:
```bash
# Get your JWT from https://pinata.cloud/keys
# Update .env.testnet with correct JWT
```

3. **Check internet connection** to Pinata:
```bash
curl -X POST "https://api.pinata.cloud/data/testAuthentication" \
  -H "Authorization: Bearer YOUR_JWT"
```

---

## Test Failures

### pytest: command not found

**Symptom**: `pytest: command not found`

**Solution**:
```bash
# Install pytest
pip install pytest

# Or use Python module form
python -m pytest backend/tests/ -v
```

### "test_micropayment_cycle.py: No such file or directory"

**Symptom**: Cannot find test file

**Solution**:
```bash
# Ensure you're in project root
pwd
# Check test file exists
ls backend/tests/test_micropayment_cycle.py

# Run from project root
python -m pytest backend/tests/test_micropayment_cycle.py -v
```

### Tests hang or timeout

**Symptom**: Test runs but never completes, hangs for > 30 seconds

**Causes**:
- Slow network to TestNet node
- Agent semantic search taking too long
- IPFS upload stalled

**Solutions**:

1. **Run with timeout**:
```bash
pytest backend/tests/test_micropayment_cycle.py -v --timeout=60
```

2. **Check network latency**:
```bash
# Test node speed
time curl https://testnet-api.algonode.cloud/health

# If > 2 seconds, network is slow
# Try alternative node (see "ConnectionError" section above)
```

3. **Run specific fast test**:
```bash
# Run just the payment limit test (very fast)
pytest backend/tests/test_critical_path_coverage.py::test_payment_decline_exceeding_limit -v
```

### "GEMINI_API_KEY not configured"

**Symptom**: Test or agent fails with "GEMINI_API_KEY not found"

**Cause**: Missing Gemini API key for LangChain agent

**Solution**:
1. Get key from [Google AI Studio](https://makersuite.google.com/app/apikey)
2. Add to `.env.testnet`:
```bash
GEMINI_API_KEY=your_key_here
```
3. Restart backend/tests

---

## Debugging Deep Dives

### Enable Verbose Logging

```bash
# Run backend with debug logging
PYTHONPATH=. python -m uvicorn backend.main:app --reload --log-level debug

# Run tests with verbose output
pytest backend/tests/ -vv -s --log-cli-level=DEBUG

# Check logs
tail -f backend.log
tail -f agent_demo.log
```

### Use Python Debugger

```python
# Add to any Python file where you want to pause
import pdb; pdb.set_trace()

# Run and it will pause at breakpoint
# Type 'c' to continue, 'n' for next line, 'p variable' to print
```

### Check Transaction Status

```bash
# Get full transaction details from explorer
TX_ID="6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ"
curl "https://testnet-idx.algonode.cloud/v2/transactions/${TX_ID}"

# Check if confirmed
curl "https://testnet-idx.algonode.cloud/v2/transactions/${TX_ID}" | grep -o '"confirmed-round":[0-9]*'
```

### Inspect Smart Contract State

```bash
# Get app state for listing contract
APP_ID=1234567
curl "https://testnet-idx.algonode.cloud/v2/applications/${APP_ID}"

# Check specific listing
curl "https://testnet-idx.algonode.cloud/v2/applications/${APP_ID}/box?name=listing_47"
```

---

## Performance Issues

### Slow API responses (> 5 seconds)

**Causes**:
- Slow Algorand node
- Slow IPFS upload
- Slow semantic search (Gemini API)

**Solutions**:

1. **Profile the slow operation**:
```bash
# Add timing to backend/main.py
import time
start = time.time()
# ... operation ...
elapsed = time.time() - start
print(f"Operation took {elapsed:.2f}s")
```

2. **Use faster node**:
```bash
# Try AlgoNode (usually fastest)
ALGOD_URL=https://testnet-api.algonode.cloud

# Or try K1 Finance:
ALGOD_URL=https://testnet-api.k1.jup.ag
```

3. **Cache IPFS CIDs locally** (if building):
```python
# Instead of uploading same file twice, cache CID
cid_cache = {}
if content_hash not in cid_cache:
    cid_cache[content_hash] = upload_to_ipfs(content)
```

---

## Environment Variable Issues

### "Unrecognized env var: SOMETHING"

**Symptom**: Backend starts but complains about unknown variable

**Solution**:
```bash
# Check which vars are required
grep "getenv\|environ" backend/utils/runtime_env.py

# Make sure .env.testnet has all required vars
# See SETUP.md for complete list
```

### ".env.testnet not loaded"

**Symptom**: Variables are empty, env not loaded

**Solutions**:

1. **Verify file exists**:
```bash
ls -la .env.testnet
```

2. **Check format** (should have no spaces around =):
```bash
# Correct:
ALGOD_URL=https://testnet-api.algonode.cloud

# Incorrect:
ALGOD_URL = https://testnet-api.algonode.cloud
```

3. **Manually load in Python**:
```bash
# In Python shell or script:
import os
from dotenv import load_dotenv
load_dotenv('.env.testnet')
print(os.getenv('ALGOD_URL'))
```

---

## Getting Help

### Collect Debug Information

Before asking for help, gather:

```bash
# System info
python3 --version
node --version
npm --version

# Environment
cat .env.testnet | grep -v MNEMONIC  # Hide secrets

# Check if services running
lsof -i :8000  # Backend
lsof -i :5173  # Frontend

# Recent errors
tail -50 backend.log
tail -50 frontend.log

# Contract state
curl "https://testnet-idx.algonode.cloud/v2/applications/${INSIGHT_LISTING_APP_ID}"
```

### Resources

- **Algorand Docs**: https://developer.algorand.org/
- **Algorand Discord**: https://discord.gg/algorand
- **TestNet Dispenser**: https://dispenser.testnet.algoexplorerapi.io/
- **TestNet Explorer**: https://explorer.perawallet.app/
- **AlgoKit Docs**: https://github.com/algorandfoundation/algokit-cli

---

## Next Steps

- Return to [DEMO.md](DEMO.md) for UI walkthrough
- See [SETUP.md](SETUP.md) if not yet set up
- Check [TESTS.md](TESTS.md) for test examples
