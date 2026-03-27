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
