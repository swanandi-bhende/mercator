# Deployment Guide (Live URL)

This guide deploys Mercator to public URLs using:
- Backend: Render (FastAPI)
- Frontend: Vercel (Vite React)

You can complete this in 20-30 minutes.

## 1. Pre-deploy Checklist

Before deploying, verify:

1. Code is pushed to GitHub.
2. You have these values ready from local `.env.testnet`:
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
- `INSIGHT_LISTING_APP_ID`
- `ESCROW_APP_ID`
- `REPUTATION_APP_ID`
- `USDC_ASA_ID` (TestNet: `10458941`)
- `USDC_DECIMALS` (usually `6`)

3. Wallets are funded on Algorand TestNet.

## 2. Deploy Backend (Render)

### 2.1 Create Web Service

1. Go to Render Dashboard.
2. Click New + -> Web Service.
3. Connect your GitHub repo.
4. Set:
- Name: `mercator-backend`
- Environment: `Python 3`
- Root Directory: repo root (leave blank)
- Build Command:

```bash
pip install -r backend/requirements.txt
```

- Start Command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

### 2.2 Add Backend Environment Variables

In Render service settings, add all required variables:

- `NETWORK=testnet`
- `ALGOD_URL=...`
- `INDEXER_URL=...`
- `ALGOD_TOKEN=...` (if applicable)
- `INDEXER_TOKEN=...` (if applicable)
- `GEMINI_API_KEY=...`
- `PINATA_JWT=...`
- `DEPLOYER_MNEMONIC=...`
- `DEPLOYER_ADDRESS=...`
- `BUYER_MNEMONIC=...`
- `BUYER_WALLET=...`
- `BUYER_ADDRESS=...`
- `INSIGHT_LISTING_APP_ID=...`
- `ESCROW_APP_ID=...`
- `REPUTATION_APP_ID=...`
- `USDC_ASA_ID=10458941`
- `USDC_DECIMALS=6`
- `EXPLORER_TX_BASE=https://lora.algokit.io/testnet/tx`

Do not set `FRONTEND_ORIGIN` yet. You will set it after frontend URL exists.

### 2.3 First Deploy and Health Check

After deploy succeeds, open:

```text
https://<your-render-backend>/health
```

Expected: JSON with `status` and service checks.

If this fails, check Render logs for missing env vars.

## 3. Deploy Frontend (Vercel)

### 3.1 Import Project

1. Go to Vercel Dashboard.
2. Click Add New -> Project.
3. Import same GitHub repo.
4. Set:
- Framework Preset: `Vite`
- Root Directory: `frontend`
- Build Command: `npm run build`
- Output Directory: `dist`

### 3.2 Set Frontend Environment Variable

Add:

- `VITE_API_BASE_URL=https://<your-render-backend>`

Deploy the frontend.

### 3.3 Verify Frontend

Open your Vercel URL and test:
- Home page loads.
- Sell page opens.
- Discover page can call backend.

## 4. Complete CORS (Critical)

Now set backend CORS origin on Render:

- `FRONTEND_ORIGIN=https://<your-vercel-frontend>`

If you have multiple domains:

```text
FRONTEND_ORIGIN=https://<vercel-url>,https://<custom-domain>
```

Redeploy backend.

## 5. Post-deploy Validation

Run this order:

1. `GET /health` on backend URL.
2. Open frontend URL.
3. On Sell page: publish one insight.
4. Confirm receipt shows:
- tx id
- listing id
- cid
- explorer link opens
5. On Discover page: search a relevant query and confirm live listings show.
6. On Activity page: verify listing record appears.

## 6. Why app was closing locally

`python demo.py` is a one-shot script that starts servers, runs flow, then exits and shuts servers down.

If you want demo.py to keep servers running:

```bash
DEMO_KEEP_ALIVE=1 python demo.py
```

For normal local dev, run backend and frontend separately:

```bash
# terminal 1
source .venv/bin/activate
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000

# terminal 2
cd frontend
npm run dev -- --host 127.0.0.1 --port 3000
```

## 7. Common Deployment Issues

### 7.1 Discover returns poor results or empty

Cause: Gemini embedding endpoint/rate limit fallback.

Action:
- Verify `GEMINI_API_KEY` is valid.
- Expect lexical fallback when embeddings fail; this is normal degradation behavior.

### 7.2 Payment fails with insufficient balance

Cause: Buyer wallet lacks USDC/Algo.

Action:
- Fund buyer wallet on TestNet.
- Ensure buyer is opted-in to USDC ASA `10458941`.

### 7.3 Explorer links fail

Ensure backend env var is:

```text
EXPLORER_TX_BASE=https://lora.algokit.io/testnet/tx
```

### 7.4 CORS blocked in browser

Ensure backend has:

```text
FRONTEND_ORIGIN=https://<your-vercel-frontend>
```

and redeploy backend.

## 8. Optional Custom Domain

- Add custom domain in Vercel for frontend.
- Add custom domain in Render for backend.
- Update:
  - `VITE_API_BASE_URL`
  - `FRONTEND_ORIGIN`

Then redeploy both.
