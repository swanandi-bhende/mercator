# Mercator

Agentic commerce platform on Algorand: sellers list trading insights, an autonomous agent discovers and evaluates them, and buyers complete micropayments atomically with instant content delivery.

**Live**: [mercator-algorand.vercel.app](https://mercator-algorand.vercel.app/)  
**Backend**: [mercator-reka.onrender.com](https://mercator-reka.onrender.com/)

---

## Quick Start

### Run Demo (2 minutes)
```bash
./demo.sh
```
Starts backend (8000) + frontend (5173), runs tests, executes full purchase flow.

### Setup (First Time)
See [Setup.md](docs/Setup.md) for detailed configuration.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install
# Configure .env.testnet with Algorand + API keys
./demo.sh
```

---

## How It Works

1. Seller lists trading insight with USDC price
2. Backend uploads content to IPFS, registers on InsightListing contract
3. Agent discovers insights via semantic search + Algorand reputation ranking
4. Buyer approves payment (requires typing "approve")
5. Atomic transaction: USDC transfer + escrow release + reputation update in single group
6. Buyer receives content instantly

**Key**: All-or-nothing execution—no partial failures, instant settlement.

---

## Documentation

| Document | Purpose |
|----------|---------|
| [Setup.md](docs/Setup.md) | Environment setup, wallets, smart contract deployment |
| [Demo.md](docs/Demo.md) | Interactive UI walkthrough, demo scenarios |
| [Features.md](docs/Features.md) | Product features, feature matrix vs competitors |
| [x402_Implementation.md](docs/x402_Implementation.md) | Payment architecture, API endpoints, approval gates |
| [Algorand_Implementation.md](docs/Algorand_Implementation.md) | Smart contracts, atomic groups, reputation system |
| [contracts.md](docs/contracts.md) | Deployed contract addresses, app IDs, transaction hashes |
| [Security.md](docs/Security.md) | Security audit, threat model, compliance checklist |
| [Tests.md](docs/Tests.md) | Test suite, coverage, performance benchmarks |
| [Troubleshooting.md](docs/Troubleshooting.md) | Common issues and solutions |
| [Deploy.md](docs/Deploy.md) | Production deployment (Vercel + Render) |
| [business.md](docs/business.md) | Business model, GTM strategy, roadmap |

---

## Deployed Contracts (TestNet)

| Contract | App ID | Address | Status |
|----------|--------|---------|--------|
| InsightListing | 758025190 | AVJELGX3NJ2C3ZXT6KWAHLJZRWRTN7CEOLYUBVKRTR5EWN2QE5L24Q37Q4 | Active |
| Escrow | 761839258 | I6YCXMEWRAXGDQ2NAYNPEUWUA77WBHCHQ5O7AYASMJPQEDGPEK44N74ALE | Active |
| Reputation | 758022459 | YDIVEMIG7AYBQ7U7ISU5ILNG5RPAIVCU2UUMUF2YTYH2SL6APF3KWQQL2Y | Active |
| FeeConfig | 761839101 | BW4DVLKC2VKEH47TPWPCJG6GJEVXTG77VQWZONIV57F255UCV4TU3UKMQU | Active |
| SubscriptionManager | 761863755 | N7SSOFF3NXB5E5XNR3AJHH54HR56XPBQ4GJ3Z3IBUHECTCJCZP5GKQAE3U | Active |

Treasury: `M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM`

See [contracts.md](docs/contracts.md) for complete contract reference and deployment details.

---

## Latest Proof (2026-04-13)

Successful atomic purchase cycle on TestNet:
- Payment TX: `6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ`
- Escrow Release TX: `MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A`
- Reputation Update TX: `YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A`
- Seller Rep: 87 → 97 (+10)

Verify on [AlgoExplorer TestNet](https://testnet.algoexplorer.io/tx/6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ)

---

## Requirements

- **Python**: 3.12+
- **Node.js**: 18+
- **Algorand TestNet**: Get ALGO from [dispenser](https://dispenser.testnet.algoexplorerapi.io/)
- **API Keys**: Gemini (LangChain), Pinata JWT (IPFS)

Full environment setup: [Setup.md](docs/Setup.md)

---

## Quick Commands

```bash
# Frontend dev server (Vite on 5173)
cd frontend && npm run dev

# Backend dev server (FastAPI on 8000)
python backend/main.py

# Run tests
pytest backend/tests/ -v

# Full integration test
./demo.sh
```

---

## API Endpoints

See [x402_Implementation.md](docs/x402_Implementation.md) for schemas.

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/list` | Create insight listing |
| GET | `/discover` | Search insights by query |
| POST | `/demo_purchase` | Autonomous purchase flow |
| GET | `/reputation/{address}` | Query seller score |
| GET | `/ledger` | View activity trail |

---

## Stack

- **Frontend**: React + Vite + TypeScript
- **Backend**: FastAPI + Python 3.12
- **Blockchain**: Algorand TestNet (PyTeal smart contracts)
- **Storage**: IPFS (Pinata)
- **AI**: LangChain + Google Gemini
- **Wallet**: Pera Wallet + algosdk

Full security audit in [Security.md](docs/Security.md).

Checklist:
- ✓ Atomic payment + escrow release (verified in testnet)
- ✓ USDC limits enforced (max 5.0 per transaction)
- ✓ Reputation immutable and monotonically increasing
- ✓ No hardcoded credentials (.env properly configured)
- ✓ Keypair scan shows no exposed secrets

---

## Support

- **General Issues**: See [Troubleshooting.md](docs/Troubleshooting.md)
- **Setup Issues**: See [Setup.md](docs/Setup.md)
- **Demo Issues**: See [Demo.md](docs/Demo.md)
- **Test Failures**: See [Tests.md](docs/Tests.md) debugging section
- **Algorand Questions**: See [Algorand_Implementation.md](docs/Algorand_Implementation.md) resources

---

## License

GPL-3.0. See [LICENSE](LICENSE).
