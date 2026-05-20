# Setup Guide

Get Mercator running locally in under 15 minutes. This guide covers environment setup, smart contract deployment, and local development.

## What You'll Set Up

- **Backend**: FastAPI server (port 8000) with agent, x402 payments, and Algorand contracts
- **Frontend**: React + Vite app (port 5173) with wallet integration
- **Contracts**: Three ARC4 smart contracts on Algorand TestNet
- **Payment Flow**: End-to-end x402 micropayment pipeline

## Prerequisites

You'll need these tools installed on macOS or Linux:

- **Python 3.12+** (`python3 --version`)
- **Node.js 18+** and npm (`node --version`)
- **Git** (`git --version`)

For Algorand TestNet testing:
- An Algorand wallet (use [Pera Wallet](https://www.perawallet.app/))
- TestNet ALGO: Get from the [faucet](https://bank.testnet.algorand.org/)
- TestNet USDC (ASA 10458941): Request testnet USDC or ask on the [Algorand Discord](https://discord.gg/algorand)

---

## Quick Start (15 minutes)

### 1. Clone and Install

```bash
git clone https://github.com/yourusername/mercator.git
cd mercator

# Create Python virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install backend + contracts
pip install -r backend/requirements.txt

# Install frontend
cd frontend && npm install && cd ..
```

### 2. Configure Environment

Create `.env.testnet` in the project root:

```bash
# Algorand TestNet (algonode is free and reliable)
ALGOD_URL=https://testnet-api.algonode.cloud
INDEXER_URL=https://testnet-idx.algonode.cloud
NETWORK=testnet

# Smart Contract App IDs
# Get these AFTER deploying contracts (see "Deploy Contracts" section)
INSIGHT_LISTING_APP_ID=<deployment-app-id>
ESCROW_APP_ID=<deployment-app-id>
REPUTATION_APP_ID=<deployment-app-id>
FEE_CONFIG_APP_ID=<deployment-app-id>

# USDC on TestNet
USDC_ASA_ID=10458941
USDC_DECIMALS=6

# Seller wallet (can be same as deployer for testing)
SELLER_ADDRESS=<your-testnet-algorand-address>
SELLER_MNEMONIC="<25-word-recovery-phrase>"

# Buyer wallet (must be different for testing)
BUYER_MNEMONIC="<25-word-recovery-phrase>"
BUYER_WALLET=<buyer-algorand-address>
BUYER_ADDRESS=<buyer-algorand-address>

# AI & Storage APIs (optional - demo mode works without)
GEMINI_API_KEY=<get-from-https://aistudio.google.com>
PINATA_JWT=<get-from-https://pinata.cloud>

# Operator API (optional)
OPERATOR_API_KEY=optional-key
```

### 3. Start Services

**Terminal 1 - Backend (port 8000):**
```bash
source .venv/bin/activate
PYTHONPATH=. python -m uvicorn backend.main:app --reload --port 8000
```

**Terminal 2 - Frontend (port 5173):**
```bash
cd frontend
npm run dev
```

**Terminal 3 - Tests:**
```bash
source .venv/bin/activate
# Run all tests
pytest backend/tests/ -v

# Or run specific test
PYTHONPATH=. pytest backend/tests/test_payment_flow.py -v -s
```

Visit [http://localhost:5173](http://localhost:5173) to see the app.

---

## How the System Works (Architecture Overview)

```
┌──────────────────────────────────────────────────────────┐
│ React Frontend (Port 5173)                               │
│ - Sell Insight: Seller lists trading ideas              │
│ - Discover: Buyer searches insights                      │
│ - Checkout: x402 micropayment                            │
│ - Receipt: View transaction on explorer                  │
└────────────────┬─────────────────────────────────────────┘
                 │ HTTP/JSON
┌────────────────▼─────────────────────────────────────────┐
│ FastAPI Backend (Port 8000)                              │
│ - Agent: AI evaluates insights                           │
│ - x402: Micropayment execution                           │
│ - Smart Contracts: Escrow & Reputation                   │
└────────────────┬────────────────┬───────────────────────┘
                 │                │
    ┌────────────▼────────┐    ┌──▼───────────────┐
    │ Algorand TestNet    │    │ IPFS (Pinata)    │
    │ 3 Contracts         │    │ Content Storage  │
    │ USDC Transfers      │    │                  │
    └─────────────────────┘    └──────────────────┘
```

### The Payment Flow

1. **Seller** lists an insight with price and content
2. **Backend** stores content on IPFS, listing on Algorand
3. **Agent** searches insights and evaluates relevance + reputation
4. **Buyer** sees recommendations and clicks "Buy"
5. **Buyer** types "approve" to trigger x402 payment
6. **Backend** simulates, then atomically transfers USDC + releases content
7. **Reputation** increases +10 for verified seller

---

## Full Setup with Smart Contracts

### Deploy Smart Contracts (First Time Only)

If you want to deploy your own contracts to TestNet:

```bash
# Set up deployer wallet in .env.testnet first

# Deploy all three contracts
PYTHONPATH=. python -c "
from backend.contracts.insight_listing import deploy_insight_listing
from backend.contracts.escrow import deploy_escrow  
from backend.contracts.reputation import deploy_reputation

insight_app_id = deploy_insight_listing()
escrow_app_id = deploy_escrow()
reputation_app_id = deploy_reputation()

print(f'Update .env.testnet with:')
print(f'INSIGHT_LISTING_APP_ID={insight_app_id}')
print(f'ESCROW_APP_ID={escrow_app_id}')
print(f'REPUTATION_APP_ID={reputation_app_id}')
"
```

### Use Pre-Deployed Contracts (Easier)

We provide pre-deployed app IDs for testing. Contact the team or check the [README](../README.md) for current TestNet contract IDs.

---

## Folder Structure

```
mercator/
├── backend/
│   ├── main.py              # FastAPI entry point
│   ├── agent.py             # AI agent (Gemini evaluator)
│   ├── contracts/           # Smart contract source + deployment
│   │   ├── insight_listing.py
│   │   ├── escrow.py
│   │   └── reputation.py
│   ├── tools/
│   │   ├── x402_payment.py  # Micropayment execution
│   │   └── semantic_search.py
│   ├── utils/               # Helper modules
│   └── tests/               # Pytest suite (~15 test files)
├── frontend/
│   ├── src/
│   │   ├── App.tsx
│   │   ├── SellInsight.tsx  # Listing form
│   │   ├── DiscoverInsights.tsx  # Search
│   │   ├── Checkout.tsx     # Payment UI
│   │   └── Receipt.tsx      # Confirmation
│   └── package.json
└── docs/                    # Documentation
```

---

## Development Workflow

1. **Make changes** to Python backend or React frontend
2. **Reload** automatically (both have hot reload)
3. **Test** with `pytest backend/tests/`
4. **Check Explorer** at [testnet.algoexplorer.io](https://testnet.algoexplorer.io)

### Run Full Demo (One Command)

```bash
# Requires .env.testnet configured
./demo.sh
```

This runs tests, starts both services, and executes a complete purchase scenario.

---

## Common Setup Issues

### `ModuleNotFoundError: No module named 'backend'`
```bash
export PYTHONPATH=$(pwd)  # Must set PYTHONPATH before running
pytest backend/tests/
```

### `pip install: command not found`
```bash
# Use Python module form
python3 -m pip install -r backend/requirements.txt
```

### TestNet Faucet Error
Visit [bank.testnet.algorand.org](https://bank.testnet.algorand.org/) directly instead of using code automation.

### `Error: Cannot connect to ALGOD_URL`
Verify your .env.testnet has correct endpoints:
- `ALGOD_URL=https://testnet-api.algonode.cloud` (Correct)
- NOT localhost unless you're running a local node

### `USDC Balance = 0`
TestNet USDC is limited. Ask in the [Algorand Discord](https://discord.gg/algorand) or create a secondary account with faucet ALGO and do ASA opt-in.

---

## Next Steps

- **First run**: Follow [Demo.md](Demo.md) for a guided walkthrough
- **Integration**: See [x402_Implementation.md](x402_Implementation.md) for payment architecture
- **Smart contracts**: Read [contracts.md](contracts.md) for on-chain details
- **Troubleshooting**: Check [Troubleshooting.md](Troubleshooting.md) for common errors

## Get Help

- **GitHub Issues**: Post setup questions with `.env.testnet` (no secrets)
- **Discord**: Algorand community [here](https://discord.gg/algorand)
- **Docs**: Check [Troubleshooting.md](Troubleshooting.md) first
