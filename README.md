# Mercator - AI Agent Micropayment Marketplace (AlgoBharat Round 2)

End-to-end flow: Human uploads trading insight -> AI agent discovers -> x402 micropayment on Algorand -> instant content delivery.

Mercator is being built for the Agentic Commerce track with a single core feature only, delivered as a fully working product on Algorand Testnet.

## Setup Progress

- [x] Step 1: GitHub repository created (`mercator`)
- [x] Step 2: Round 2-focused README created
- [x] Step 3: AlgoKit installed and verified (`algokit 2.10.2`)
- [~] Step 4: AlgoKit init executed with current CLI syntax; legacy flags `--frontend/--backend/--network` are no longer supported in AlgoKit 2.x

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

- AlgoKit attempted generation inside the existing `mercator` folder and created workspace helper files (`.algokit.toml`, `.algokit/`, `.vscode/`).
- The full clean scaffold is best generated in a fresh empty directory, then merged into this repository.
