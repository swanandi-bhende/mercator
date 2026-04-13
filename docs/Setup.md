# Project Setup Guide

This guide covers all steps required to set up Mercator for development, testing, and deployment.

## Supported Environments

- **OS**: macOS, Linux
- **Python**: 3.12 or higher
- **Node.js**: 18 or higher
- **Network**: Algorand TestNet (recommended for development)

## Prerequisites

Ensure the following tools are installed on your system:

```bash
# Verify Python installation
python3 --version  # Should be 3.12+

# Verify Node.js installation
node --version     # Should be 18+
npm --version

# Verify Git
git --version
```

## Quick Start (5-10 minutes)

### 1. Clone the Repository

```bash
git clone https://github.com/yourusername/mercator.git
cd mercator
```

### 2. Create and Activate Python Virtual Environment

```bash
# Create virtual environment
python3 -m venv .venv

# Activate it
source .venv/bin/activate

# Upgrade pip
pip install --upgrade pip
```

### 3. Install Python Dependencies

```bash
# Install backend dependencies
pip install -r backend/requirements.txt

# Install contract development dependencies (optional)
pip install -r backend/contracts/escrow/requirements.txt
```

### 4. Install Frontend Dependencies

```bash
cd frontend
npm install
cd ..
```

### 5. Configure Environment Variables

Create a `.env.testnet` file in the project root with the following variables:

```bash
# Algorand Configuration
ALGOD_URL=https://testnet-api.algonode.cloud
INDEXER_URL=https://testnet-idx.algonode.cloud
NETWORK=testnet

# Smart Contract App IDs (obtain after deployment)
INSIGHT_LISTING_APP_ID=<your-app-id>
ESCROW_APP_ID=<your-app-id>
REPUTATION_APP_ID=<your-app-id>

# USDC Configuration
USDC_ASA_ID=10458941
USDC_DECIMALS=6

# Wallets and Mnemonics (TestNet accounts only)
DEPLOYER_MNEMONIC="<25-word-mnemonic>"
DEPLOYER_ADDRESS=<algorand-address>
BUYER_MNEMONIC="<25-word-mnemonic>"
BUYER_WALLET=<algorand-address>
BUYER_ADDRESS=<algorand-address>

# API Keys (optional for full agent features)
GEMINI_API_KEY=<your-google-gemini-key>
PINATA_JWT=<your-pinata-jwt-token>

# Operator Access Control (optional)
OPERATOR_API_KEY=<optional-operator-key>

# x402 Payment Configuration
X402_PRIVATE_KEY=<optional-private-key-for-payment>
```

**Important**: Never commit `.env.*` files. They are already listed in `.gitignore`.

### 6. Fund Your TestNet Accounts

Before running any transactions, fund your accounts with TestNet Algo:

1. Visit [Algorand TestNet Dispenser](https://dispenser.testnet.algoexplorerapi.io/)
2. Enter your deployer and buyer wallet addresses
3. Request funds (typically 10 Algo each for development)

### 7. Deploy Smart Contracts

Deploy the three ARC4 contracts required by the system:

```bash
# Navigate to each contract directory and deploy

cd backend/contracts/insight_listing/smart_contracts
python -m smart_contracts

cd ../../escrow/smart_contracts
python -m smart_contracts

cd ../../reputation/smart_contracts
python -m smart_contracts
```

After deployment, update your `.env.testnet` with the returned app IDs:

```bash
INSIGHT_LISTING_APP_ID=<returned-app-id>
ESCROW_APP_ID=<returned-app-id>
REPUTATION_APP_ID=<returned-app-id>
```

### 8. Verify Setup

Run the setup verification script:

```bash
source .venv/bin/activate
cd backend
python -c "from utils.runtime_env import load_env_file; load_env_file(); print('Environment loaded successfully')"
```

Expected output: `Environment loaded successfully`

## Environment Variables Reference

### Algorand Network

| Variable | Description | Example |
|----------|-------------|---------|
| `ALGOD_URL` | Node RPC endpoint | `https://testnet-api.algonode.cloud` |
| `INDEXER_URL` | Indexer API endpoint | `https://testnet-idx.algonode.cloud` |
| `NETWORK` | Network name | `testnet` or `mainnet` |

### Smart Contracts

| Variable | Description | 
|----------|-------------|
| `INSIGHT_LISTING_APP_ID` | InsightListing contract app ID (obtained after deployment) |
| `ESCROW_APP_ID` | Escrow contract app ID (obtained after deployment) |
| `REPUTATION_APP_ID` | Reputation contract app ID (obtained after deployment) |

### USDC Configuration

| Variable | Description | Value |
|----------|-------------|-------|
| `USDC_ASA_ID` | Algorand USDC token ID | `10458941` (TestNet) |
| `USDC_DECIMALS` | USDC decimal places | `6` |

### Wallet Credentials (TestNet Only)

| Variable | Description |
|----------|-------------|
| `DEPLOYER_MNEMONIC` | 25-word recovery phrase for deployer account |
| `DEPLOYER_ADDRESS` | Algorand address of deployer account |
| `BUYER_MNEMONIC` | 25-word recovery phrase for buyer account |
| `BUYER_WALLET` | Algorand address of buyer account |
| `BUYER_ADDRESS` | Alternative name for buyer wallet |

### External APIs

| Variable | Description | Required |
|----------|-------------|----------|
| `GEMINI_API_KEY` | Google Gemini API key for LangChain agent | Yes (for agent features) |
| `PINATA_JWT` | Pinata authentication token for IPFS uploads | Yes (for content storage) |

### Optional Configuration

| Variable | Description | Default |
|----------|-------------|---------|
| `OPERATOR_API_KEY` | API key for operator-only endpoints | None |
| `X402_PRIVATE_KEY` | Private key for x402 payment signer | None |
| `MAX_MICROPAYMENT_USDC` | Maximum single micropayment in USDC | `5.0` |

## Troubleshooting Setup Issues

### "ModuleNotFoundError: No module named 'backend'"

Ensure you have `PYTHONPATH` set correctly:

```bash
export PYTHONPATH=$(pwd)
python backend/main.py
```

Or use the virtual environment Python directly:

```bash
.venv/bin/python backend/main.py
```

### "ConnectionError: cannot connect to Algorand node"

Verify `ALGOD_URL` is correct and accessible:

```bash
curl https://testnet-api.algonode.cloud/health
```

### "App ID not found" Error

Ensure:
1. Contracts have been deployed
2. App IDs are correctly set in `.env.testnet`
3. You are on the correct network (TestNet vs MainNet)

### Package Installation Failures

If pip install fails, try:

```bash
# Clear pip cache
pip install --no-cache-dir -r backend/requirements.txt

# Or install with verbose output for debugging
pip install -v -r backend/requirements.txt
```

## Development Workflow

### Running the Backend

```bash
source .venv/bin/activate
cd backend
python -m uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

Backend will be available at `http://localhost:8000`

### Running the Frontend

```bash
cd frontend
npm run dev
```

Frontend will be available at `http://localhost:5173`

### Running Tests

```bash
source .venv/bin/activate
pytest backend/tests/ -v
```

## Next Steps

- See [DEMO.md](DEMO.md) for walkthrough of the user interface and features
- See [TESTS.md](TESTS.md) for comprehensive testing guidance
- See [ALGORAND.md](ALGORAND.md) for technical details on the Algorand integration
- See [COMPONENTS.md](COMPONENTS.md) for architectural details and proof artifacts
