# Deploy Mercator to a Public URL

This guide deploys:
- Backend (FastAPI) on Render
- Frontend (Vite React) on Vercel

## 1. Push Code

Push your latest branch to GitHub so both platforms can build from it.

## 2. Deploy Backend on Render

### Create Service

- Platform: Render -> New Web Service
- Repo: this Mercator repo
- Build Command:

```bash
pip install -r backend/requirements.txt
```

- Start Command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### Set Environment Variables (Render)

Copy these from your local `.env.testnet`:

- `NETWORK=testnet`
- `ALGOD_URL`
- `INDEXER_URL`
- `ALGOD_TOKEN` (if used)
- `INDEXER_TOKEN` (if used)
- `GEMINI_API_KEY`
- `PINATA_JWT`
- `DEPLOYER_MNEMONIC`
- `DEPLOYER_ADDRESS`
- `BUYER_MNEMONIC`
- `BUYER_WALLET`
- `BUYER_ADDRESS`
- `INSIGHT_LISTING_APP_ID`
- `ESCROW_APP_ID`
- `REPUTATION_APP_ID`
- `USDC_ASA_ID=10458941`
- `USDC_DECIMALS=6`
- `EXPLORER_TX_BASE=https://lora.algokit.io/testnet/tx`

After first deploy, test:

```text
https://<your-render-backend>/health
```

## 3. Deploy Frontend on Vercel

### Create Project

- Platform: Vercel -> Add New Project
- Root directory: `frontend`
- Framework preset: Vite
- Build command: `npm run build`
- Output directory: `dist`

### Set Frontend Env Var

- `VITE_API_BASE_URL=https://<your-render-backend>`

Deploy and open your Vercel URL.

## 4. Configure Backend CORS for Frontend URL

Now set this on Render backend env vars:

- `FRONTEND_ORIGIN=https://<your-vercel-frontend>`

If multiple domains:

```text
FRONTEND_ORIGIN=https://<vercel-url>,https://<custom-domain>
```

Redeploy backend.

## 5. Verify End-to-End

1. Open frontend URL.
2. List one insight from Sell page.
3. Confirm receipt has tx id and explorer link.
4. Open Find/Discover page and search relevant query.
5. Confirm new listing appears.
6. Open Activity page and verify ledger entries.

## 6. Local Behavior Clarification

`python demo.py` is intentionally one-shot and shuts down servers after the scripted flow.

To keep it running:

```bash
DEMO_KEEP_ALIVE=1 python demo.py
```

For normal development, run services separately.
