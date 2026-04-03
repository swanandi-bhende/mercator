# Mercator

Mercator is an Algorand TestNet demo for seller-listed trading insights and an AI buyer that can search, buy, and unlock the insight in one flow.

## Latest Verified Run

- Command: `python demo.py`
- Listing tx: `WI3DBJAEXOMVP6XKHLF3SVMUVOFHSVI25ZBCSWEB7BD4Z6JSSA3Q`
- Payment tx: `FFFJ2PN57NGT765W2OI6TK4RSL4H6SVCTDFIMTT6L3PIPGJVUL5A`
- Escrow tx: `BHGEHFI4ZMGZV5625ME33CSQJEWSBNQKRKRGCU5V6WHFHATLBRWA`
- Final delivered insight text: `Sample trading insight: Buy NIFTY above 24500 with SL 24380`
- Full trace: [demo_flow.log](demo_flow.log)

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

## Testing

The mocked end-to-end suite lives in [backend/tests/test_micropayment_cycle.py](backend/tests/test_micropayment_cycle.py).

```bash
pytest backend/tests/test_micropayment_cycle.py
```
