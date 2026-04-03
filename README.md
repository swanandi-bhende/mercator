# Mercator

Mercator is an Algorand TestNet demo for seller-listed trading insights and an AI buyer that can search, buy, and unlock the insight in one flow.

## Core Files

- [backend/main.py](backend/main.py): FastAPI API with `/list` and `/demo_purchase`
- [backend/agent.py](backend/agent.py): LangChain buyer agent
- [backend/tools/x402_payment.py](backend/tools/x402_payment.py): USDC payment and post-payment flow
- [frontend/src/SellInsight.tsx](frontend/src/SellInsight.tsx): seller UI
- [demo.py](demo.py): one-command local demo runner

## Run

```bash
python demo.py
```

## API

- `POST /list` publishes an insight to IPFS and Algorand
- `POST /demo_purchase` runs the buyer agent and returns the final insight text

## Environment

Required keys include `ALGOD_URL` or `ALGOD_SERVER`, `INDEXER_URL` or `INDEXER_SERVER`, `GEMINI_API_KEY`, `PINATA_JWT`, `INSIGHT_LISTING_APP_ID`, `ESCROW_APP_ID`, `REPUTATION_APP_ID`, `DEPLOYER_MNEMONIC`, `DEPLOYER_ADDRESS`, `BUYER_WALLET`, `BUYER_MNEMONIC`, and `USDC_ASA_ID`.
