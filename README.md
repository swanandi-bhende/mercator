# Mercator

Mercator is an Agentic Commerce demo on Algorand TestNet where a seller lists a trading insight, and an autonomous LangChain buyer agent discovers, evaluates, pays via x402 micropayment, and unlocks instant content delivery.

## Architecture

Architecture path: React UI -> FastAPI Backend -> Algorand Smart Contracts (ASA + Escrow + Reputation) -> IPFS (Pinata) -> LangChain Agent (Gemini) -> x402 Micropayment -> Instant Content Delivery.

Flow caption: This architecture expresses Mercator's single core feature from listing to monetization. The React UI captures seller and buyer actions, the FastAPI backend orchestrates storage and chain calls, IPFS stores the insight body, Algorand contracts anchor listing/escrow/reputation state, the LangChain agent performs reasoning with Gemini to decide BUY or SKIP, x402 executes settlement, and confirmed buyers receive immediate insight text.

In plain English: a seller submits text in the UI, the backend uploads it to Pinata and writes listing metadata on Algorand (price, CID, ASA linkage). A buyer query is evaluated by the agent using semantic relevance and on-chain reputation. If value and trust thresholds pass, the buyer approves payment, x402 transfers USDC atomically, escrow records unlock state, and the backend returns the full insight content to the buyer without waiting for manual reconciliation.

## Project Structure

- [frontend/src](frontend/src): React application (seller listing UI, buyer discovery/evaluation pages).
- [backend/main.py](backend/main.py): FastAPI entrypoint and API orchestration.
- [backend/agent.py](backend/agent.py): LangChain agent logic (search, evaluate, decide, pay).
- [backend/tools](backend/tools): Tool modules for semantic search, x402 payment, and post-payment fulfillment.
- [backend/utils](backend/utils): Shared helpers (IPFS, env normalization, error messages).
- [backend/contracts](backend/contracts): Smart contract sources, deploy configs, and generated ABI clients.
- [backend/tests](backend/tests): End-to-end and critical path tests.
- [demo.sh](demo.sh): One-click demo runner for local showcase.
- [demo.py](demo.py): Python demo runner for scripted API flow.

## How the Micropayment Flow Works (Step-by-Step)

1. Seller lists insight in the React UI.
2. `POST /list` uploads the insight text to Pinata and receives a CID.
3. Backend stores listing metadata on InsightListing contract (price, seller, CID, ASA id).
4. Buyer triggers `POST /demo_purchase` with a natural-language query.
5. Agent calls semantic search tool, ranks listings by relevance + seller reputation.
6. Agent evaluates value-for-price and trust thresholds to produce BUY or SKIP.
7. If BUY and user explicitly types `approve`, agent calls x402 payment tool.
8. x402 simulates then executes USDC transfer on Algorand TestNet.
9. Post-payment flow confirms transaction, calls escrow release, and fetches CID content from IPFS.
10. Backend returns instant insight text and transaction metadata to the buyer.

## How to Run the One-Click Demo

Run the full flow (tests + backend + frontend + agent execution):

```bash
./demo.sh
```

What `demo.sh` does:

1. Runs the micropayment regression test file.
2. Starts FastAPI backend on port `8000`.
3. Starts React frontend on port `5173`.
4. Executes a live agent run that performs search, evaluation, and x402 purchase.
5. Writes runtime logs to `backend.log`, `frontend.log`, `agent_demo.log`, and `mercator.log`.

## Latest Verified TestNet Runs

- Full Round 2 run ledger: [testnet-demo-runs.md](testnet-demo-runs.md)
- Raw API capture: [testnet-demo-runs.raw.json](testnet-demo-runs.raw.json)
- Runtime trace: [demo_flow.log](demo_flow.log)
- Security audit report: [SECURITY.md](SECURITY.md)
- Latest seller upload tx id: ZRD7Q7WXUAWTDEP77ERRRJ2GGE2NC35MATL3TTNH4HHLDDVRRGHA
- Latest payment tx id: QUOO4WN6LPAUZVKYWVE362YDCAQ67MK7QS3T77MNO5IC33VXIIGA

## API

- `POST /list`: publish insight to IPFS and Algorand listing contract.
- `POST /discover`: semantic discovery endpoint (relevance + reputation ranking).
- `POST /demo_purchase`: run autonomous buyer flow and return final insight text.
- `GET /ledger`: normalized activity feed of listing/payment/escrow events.

## Environment

Required keys include `ALGOD_URL` or `ALGOD_SERVER`, `INDEXER_URL` or `INDEXER_SERVER`, `GEMINI_API_KEY`, `PINATA_JWT`, `INSIGHT_LISTING_APP_ID`, `ESCROW_APP_ID`, `REPUTATION_APP_ID`, `DEPLOYER_MNEMONIC`, `DEPLOYER_ADDRESS`, `BUYER_WALLET`, `BUYER_MNEMONIC`, and `USDC_ASA_ID`.

## Testing

```bash
pytest backend/tests/test_micropayment_cycle.py -q --tb=no
```
