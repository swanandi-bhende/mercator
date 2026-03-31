# Mercator - AI Agent Micropayment Marketplace (AlgoBharat Round 2)

End-to-end flow: Human uploads trading insight -> AI agent discovers -> x402 micropayment on Algorand -> instant content delivery.

Mercator is being built for the Agentic Commerce track with a single core feature only, delivered as a fully working product on Algorand Testnet.

## Setup Progress

- [x] Step 1: GitHub repository created (`mercator`)
- [x] Step 2: Round 2-focused README created
- [x] Step 3: AlgoKit installed and verified (`algokit 2.10.2`)
- [~] Step 4: AlgoKit init executed with current CLI syntax; legacy flags `--frontend/--backend/--network` are no longer supported in AlgoKit 2.x
- [~] Step 5: Structure verified; required legacy targets (`backend`, `algokit.toml`, `.env.example`, `requirements.txt`) are still missing because AlgoKit 2.x fullstack now generates a different layout
- [x] Step 6: Virtual environment `venv` created and activation verified (Python 3.14.3)
- [x] Step 7: Required dependencies installed in `venv` (using `x402` package, since `x402-sdk` is not available on PyPI)
- [x] Step 8: Environment files created with blank placeholders (`.env.example` and `.env`)

## How to Run Demo

Demo setup and run instructions will be added in upcoming phases.

## Tech Stack

- Algorand Testnet
- x402 micropayment flow
- Python backend services (FastAPI planned)
- React frontend
- IPFS for content storage
- LangChain + Google Gemini for AI agent reasoning

## Notes

- AlgoKit fullstack 2.x generates a monorepo layout that differs from the older Phase 1 file expectations.
- Non-essential temporary init artifacts were removed to keep this repository clean.
- No API keys are needed yet for Steps 5 and 6. Keys are required starting from `.env` setup and service integrations in later phases.

## Phase 2 Contract Progress

- [x] Step 4 complete: `InsightListing` ARC4 contract added with BoxMap-backed listing storage and `create_listing(price, seller, ipfs_hash)`.
- [x] Step 5 complete: `Escrow` ARC4 contract now includes `release_after_payment(buyer, listing_id)` with atomic group payment checks and unlock state updates.
- [x] Step 6 complete: `Reputation` ARC4 contract now includes `update_score(seller, new_score)` and `get_score(seller)` using BoxMap-backed seller scores.
- [x] Step 8 complete: all three contracts compiled successfully and generated `approval.teal`, `clear.teal`, and `.arc56.json` specs.
- [~] Step 9 partial: test commands were executed, but there is currently no test task and no contract tests in the repository yet (`algokit project run test` missing, `pytest backend/contracts` found 0 tests).
- [x] Step 10 complete (spec/client generation): ARC app specifications and typed clients were generated for InsightListing, Escrow, and Reputation.

### Latest Run Status (31 Mar 2026)

- Re-ran Step 10 successfully: all three contracts rebuilt and regenerated TEAL, ARC specs, and typed clients.
- Step 9 remains blocked for end-to-end local simulation: Docker/Podman is not installed, so `algokit localnet` cannot start; `pytest backend/contracts` currently reports no tests.
- Created a dedicated TestNet environment file by copying `.env` to `.env.testnet` at the project root.
- Added official AlgoNode TestNet endpoints to `.env.testnet` (`ALGOD_SERVER`, `INDEXER_SERVER`, `ALGOD_PORT`, `ALGOD_TOKEN`).
- Added deployer account wiring in `.env.testnet` (`DEPLOYER_MNEMONIC`, `DEPLOYER_ADDRESS`) for signed TestNet deployment commands.
- Implemented real deploy hooks in all three `deploy_config.py` files and deployed contracts to TestNet.
- Captured and stored real TestNet App IDs in `.env.testnet`.

### TestNet Deployment Output

- `INSIGHT_LISTING_APP_ID=758022443`
- `ESCROW_APP_ID=758022447`
- `REPUTATION_APP_ID=758022459`

### Build Artifacts Generated

- `backend/contracts/insight_listing/smart_contracts/artifacts/insight_listing/InsightListing.approval.teal`
- `backend/contracts/insight_listing/smart_contracts/artifacts/insight_listing/InsightListing.clear.teal`
- `backend/contracts/insight_listing/smart_contracts/artifacts/insight_listing/InsightListing.arc56.json`
- `backend/contracts/escrow/smart_contracts/artifacts/escrow/Escrow.approval.teal`
- `backend/contracts/escrow/smart_contracts/artifacts/escrow/Escrow.clear.teal`
- `backend/contracts/escrow/smart_contracts/artifacts/escrow/Escrow.arc56.json`
- `backend/contracts/reputation/smart_contracts/artifacts/reputation/Reputation.approval.teal`
- `backend/contracts/reputation/smart_contracts/artifacts/reputation/Reputation.clear.teal`
- `backend/contracts/reputation/smart_contracts/artifacts/reputation/Reputation.arc56.json`

### Inputs Needed From You

- No API keys or secrets are needed for Steps 5 and 6.
- Keys will be required when we wire external services: Algorand Testnet deployer mnemonic, Pinata JWT, Google Gemini API key, and any x402 provider credentials.
- For Testnet deployment and real App IDs: `DEPLOYER_MNEMONIC` is required.
- For full Step 9 flow simulation on LocalNet: Docker must be available and we need to add integration tests for listing -> payment -> escrow unlock -> reputation update.

### Docker Requirement (MVP)

- Docker is compulsory only for LocalNet-based testing and local end-to-end blockchain simulation.
- Docker is not compulsory to compile contracts, generate app specs/clients, or deploy directly to Testnet.
