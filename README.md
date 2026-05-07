# Mercator

Mercator is an agentic commerce platform on Algorand where sellers list trading insights, an autonomous agent discovers and evaluates them, and buyers complete micropayments atomically with instant content delivery.

## Quick Start

### Run the Demo (2 minutes)

```bash
./demo.sh
```

This one-click command starts the backend (port 8000), frontend (port 5173), runs tests, and executes a full purchase scenario end-to-end.

### Setup (First Time)

Follow [Setup.md](docs/Setup.md) for detailed environment configuration.

```bash
# Quick setup overview
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd frontend && npm install
# Configure .env.testnet with Algorand and API keys
./demo.sh
```

---

## Documentation

The project is documented across the following primary guides:

- **[Setup.md](docs/Setup.md)**: Environment setup, dependency installation, wallet configuration, smart contract deployment
- **[Demo.md](docs/Demo.md)**: Interactive UI walkthrough, page-by-page feature guide, demo scenarios
- **[Features.md](docs/Features.md)**: Core features and system capabilities
- **[x402_Implementation.md](docs/x402_Implementation.md)**: Architecture, API endpoints, core implementations
- **[Algorand_Implementation.md](docs/Algorand_Implementation.md)**: ARC4 smart contracts, atomic grouping, reputation system, transaction verification
- **[Security.md](docs/Security.md)**: Security audit, compliance checklist, successful transaction IDs, edge case test results
- **[Tests.md](docs/Tests.md)**: Regression test suite, test scenarios, performance benchmarks
- **[Troubleshooting.md](docs/Troubleshooting.md)**: Common issues and solutions
- **[Deploy.md](docs/Deploy.md)**: Production deployment to public URLs (Render + Vercel)

---

## What It Does

1. **Seller Creates Listing**: Submits insight text with USDC price via React UI
2. **Backend Processes**: Uploads content to IPFS (Pinata), registers on InsightListing contract
3. **Agent Discovers**: LangChain + Gemini ranks insights by relevance and seller reputation
4. **Atomic Payment**: x402 executes USDC transfer + escrow release in single transaction group (all-or-nothing)
5. **Reputation Updates**: Seller reputation increases by +10 on confirmation
6. **Instant Delivery**: Buyer receives insight content immediately (no manual reconciliation)

---

## Core Features

### Atomic Micropayments
- Payment + escrow release grouped in single Algorand transaction
- 4-5 second finality (TestNet)
- ~$0.0003 cost per transaction
- Instant settlement without middleman

### On-Chain Reputation
- Seller trust scores stored immutably on blockchain
- +10 per successful sale, never decreases
- Agent uses reputation for buy/skip decisions
- Queries by wallet address

### Content Verification
- IPFS CID stored with each listing (permanent, content-addressable)
- Hash verification ensures buyer receives promised content
- No centralized content server

### Agent-Driven Commerce
- Natural language queries ("latest NIFTY insight")
- LLM evaluation with semantic search ranking
- Automatic buy/skip decisions based on relevance + trust + price
- User confirmation required before payment

---

## Architecture

```
React Frontend    ←→    FastAPI Backend    ←→    Algorand Contracts
                                ├─ IPFS (Pinata)
                                ├─ LangChain + Gemini
                                └─ x402 Payment Engine
```

**Key Components**:
- `frontend/src/`: React + Vite UI (SellInsight, DiscoverInsights, Checkout, Receipt, Ledger, Trust pages)
- `backend/main.py`: FastAPI routing and orchestration
- `backend/tools/x402_payment.py`: Atomic payment execution
- `backend/tools/post_payment_flow.py`: Content delivery and reputation update
- `backend/contracts/`: Three ARC4 smart contracts (InsightListing, Escrow, Reputation)

---

## API Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/list` | Seller creates insight listing |
| GET | `/discover` | Buyer discovers insights by query |
| POST | `/demo_purchase` | Execute autonomous purchase flow |
| GET | `/ledger` | View activity audit trail |
| GET | `/reputation/{address}` | Query seller reputation score |

See [x402_Implementation.md](docs/x402_Implementation.md) for detailed request/response schemas.

---

## Deployed Contracts

| Contract | App ID | Network | Notes |
|--------|----------|---------|---------|
| InsightListing | 758025190 | TestNet | Existing listing registry |
| Escrow | 761839258 | TestNet | Fee-aware settlement contract |
| Reputation | 758022459 | TestNet | Existing reputation contract |
| FeeConfig | 761839101 | TestNet | Fee configuration and revenue tracking |
| SubscriptionManager | 761863755 | TestNet | Subscription entitlements and recurring revenue |

Treasury wallet address: M7R55YRO2M7GL5FCEHXQN2Y63HTUTCFZQRLK6QF2SPRS6ZJ4CAMJV4DBTM

---

## Latest Proof Artifacts

**Latest Successful Purchase** (2026-04-13):
- Payment TX: `6RHL36IPWJDCZOYQ73VSCGRFGG5WPVT5XFWFZSGNXL63ZWHD6LKQ`
- Escrow Release TX: `MNZCPDINK5LZF3SZSIIINUEFPTVGUCVY37BC6UBCAPQYH6RIXK6A`
- Reputation Update TX: `YFHVORAUDXFB33JBWGIJWHJ7XSI54FYKVOALSR657DTW3EAPRX4A`
- Seller Reputation: 87 → 97 (+10)

Full audit details in [Security.md](docs/Security.md).

---

## Project Structure

```
mercator/
├─ frontend/                    # React Vite app
│  └─ src/
│     ├─ SellInsight.tsx       # Seller listing interface
│     ├─ pages/
│     │  ├─ DiscoverInsights.tsx
│     │  ├─ Checkout.tsx
│     │  ├─ Receipt.tsx
│     │  ├─ ActivityLedger.tsx
│     │  └─ Trust.tsx
│     └─ components/
│
├─ backend/                     # FastAPI server
│  ├─ main.py                  # API endpoints
│  ├─ agent.py                 # LangChain agent
│  ├─ tools/
│  │  ├─ x402_payment.py       # Atomic payment
│  │  ├─ post_payment_flow.py  # Content + reputation
│  │  └─ semantic_search.py    # Vector search
│  ├─ contracts/               # Smart contracts
│  │  ├─ insight_listing/
│  │  ├─ escrow/
│  │  └─ reputation/
│  └─ tests/
│     ├─ test_micropayment_cycle.py
│     └─ test_critical_path_coverage.py
│
├─ scripts/                     # Utility scripts
│  ├─ final_purchase_check.py
│  └─ security_edge_cases.py
│
├─ docs/                        # Documentation
│  ├─ Setup.md                 # Environment setup guide
│  ├─ Demo.md                  # UI walkthrough guide
│  ├─ Features.md              # Core features overview
│  ├─ x402_Implementation.md   # Implementation details
│  ├─ Algorand_Implementation.md # Blockchain details
│  ├─ Security.md              # Audit report
│  ├─ Tests.md                 # Testing guide
│  └─ Troubleshooting.md       # Troubleshooting guide
│
├─ LICENSE
├─ README.md
└─ demo.sh                     # One-click demo
```

---

## Environment Requirements

- **Python**: 3.12+
- **Node.js**: 18+
- **Algorand TestNet**: Account with funding from [dispenser](https://dispenser.testnet.algoexplorerapi.io/)
- **API Keys**: Gemini (LangChain), Pinata JWT (IPFS)

See [Setup.md](docs/Setup.md) for complete configuration.

---

## Deploy to Public URL

Use [Deploy.md](docs/Deploy.md) for full instructions.

Quick summary:
1. Deploy backend to Render using `backend/requirements.txt` and start command `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`.
2. Deploy frontend to Vercel from `frontend` with `VITE_API_BASE_URL` set to your backend URL.
3. Set backend `FRONTEND_ORIGIN` to your frontend URL and redeploy backend.

---

## Testing

```bash
# Run all regression tests
pytest backend/tests/ -v

# Run specific test suite
pytest backend/tests/test_micropayment_cycle.py -v

# See docs/Tests.md for detailed testing guide
```

Test suites cover:
- Full purchase flow (listing, payment, delivery, reputation)
- Edge cases (low reputation, insufficient balance, invalid addresses)
- Error handling (payment limit enforcement, atomic group failure)
- Performance (< 2 sec per test)

---

## Security

All smart contracts follow ARC4 standards with:
- Type-safe contract code
- Atomic transaction grouping (no race conditions)
- Access control per contract
- Read-only methods for queries

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
