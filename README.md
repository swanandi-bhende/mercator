# Mercator

Mercator is an Algorand TestNet demo for seller-listed trading insights and an AI buyer that can search, buy, and unlock the insight in one flow.

## Latest Verified TestNet Runs

- Full Round 2 run ledger: [testnet-demo-runs.md](testnet-demo-runs.md)
- Raw API capture: [testnet-demo-runs.raw.json](testnet-demo-runs.raw.json)
- Runtime trace: [demo_flow.log](demo_flow.log)
- Latest seller upload tx id: ZRD7Q7WXUAWTDEP77ERRRJ2GGE2NC35MATL3TTNH4HHLDDVRRGHA
- Latest payment tx id: QUOO4WN6LPAUZVKYWVE362YDCAQ67MK7QS3T77MNO5IC33VXIIGA
- Explorer (if reachable): https://explorer.perawallet.app/tx/ZRD7Q7WXUAWTDEP77ERRRJ2GGE2NC35MATL3TTNH4HHLDDVRRGHA/ and https://explorer.perawallet.app/tx/QUOO4WN6LPAUZVKYWVE362YDCAQ67MK7QS3T77MNO5IC33VXIIGA/
- Verification note: these tx ids were validated directly via TestNet indexer (confirmed rounds 62118380 and 62118398)

Observed during these live runs:
- Seller uploads and x402 USDC payment transactions are confirmed on TestNet.
- Gemini quota limits can force fallback reasoning text (`Decision: SKIP`) while force-buy mode proceeds with payment.
- Escrow release tx emission passed in all latest 5 runs.
- Delivered insight text exactly matched uploaded seller text in all latest 5 runs.
- Instant access after payment confirm (<=8s) passed in all latest 5 runs.

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

For batched live TestNet runs used in Round 2 verification:

```bash
python scripts/run_testnet_demo_batch.py
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
