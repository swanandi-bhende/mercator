# Deployment Guide

Deploy Mercator to production on Vercel (frontend) and Render (backend). This guide covers environment setup, build configuration, and mainnet deployment planning.

## Live Deployments

- **Frontend**: [mercator-algorand.vercel.app](https://mercator-algorand.vercel.app/)
- **Backend API**: [mercator-reka.onrender.com](https://mercator-reka.onrender.com/)

---

## Frontend Deployment (Vercel)

Vercel is the easiest way to deploy React + Vite frontends with automatic CI/CD.

### Prerequisites

- Vercel account (free tier sufficient)
- GitHub repository with frontend code
- Environment variables ready

### Step 1: Connect GitHub to Vercel

1. Go to [vercel.com](https://vercel.com)
2. Click "New Project"
3. Select "Import GitHub Repository"
4. Choose your Mercator repo
5. Click "Import"

### Step 2: Configure Build Settings

Vercel auto-detects Vite projects, but verify:

**Framework**: `Vite`
**Build Command**: `npm run build`
**Output Directory**: `dist`
**Root Directory**: `frontend`

**Environment Variables** (set in Vercel dashboard):

```
VITE_API_BASE=https://mercator-reka.onrender.com
VITE_WS_BASE=wss://mercator-reka.onrender.com
VITE_NETWORK=testnet
```

### Step 3: Deploy

Click "Deploy" — Vercel builds and deploys automatically.

**Your frontend is now live at**:
```
https://mercator-algorand.vercel.app
```

### Automatic Deployments

- Every push to `main` triggers a new deploy
- Preview deployments for pull requests
- Rollback to previous versions anytime

### Custom Domain (Optional)

1. Add your domain in Vercel dashboard
2. Update DNS records to point to Vercel
3. Vercel auto-issues SSL certificate

---

## Backend Deployment (Render)

Render is a modern deployment platform for backend servers. Free tier includes PostgreSQL and Docker deployments.

### Prerequisites

- Render account (free tier sufficient)
- Docker image built locally (or Render builds from Dockerfile)
- Environment variables ready

### Step 1: Prepare Backend for Deployment

**Create Dockerfile** at project root:

```dockerfile
FROM python:3.12-slim

WORKDIR /app

# Copy requirements
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend code
COPY backend/ ./backend/
COPY contracts/ ./contracts/

# Expose port
EXPOSE 8000

# Environment
ENV PYTHONPATH=/app
ENV PORT=8000

# Run server
CMD ["python", "-m", "uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**Create render.yaml** (Render config):

```yaml
services:
  - type: web
    name: mercator-api
    runtime: python
    startCommand: "PYTHONPATH=/app python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000"
    healthCheckPath: /health
    envVars:
      - key: PYTHONPATH
        value: /app
      - key: LOG_LEVEL
        value: info
```

**Commit to GitHub**:

```bash
git add Dockerfile render.yaml
git commit -m "Add Render deployment configuration"
git push
```

### Step 2: Connect GitHub to Render

1. Go to [render.com](https://render.com)
2. Click "New +" → "Web Service"
3. Click "Connect Repository"
4. Authorize GitHub and select your Mercator repo
5. Click "Connect"

### Step 3: Configure Backend Service

**Name**: `mercator-api`

**Environment**: `Docker`

**Branch**: `main`

**Build Command**: (Leave empty, Render detects Dockerfile)

**Start Command**:
```
PYTHONPATH=/app python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

### Step 4: Set Environment Variables

In Render dashboard, add all required environment variables:

```
ALGOD_URL=https://mainnet-api.algonode.cloud
INDEXER_URL=https://mainnet-idx.algonode.cloud
NETWORK=mainnet

INSIGHT_LISTING_APP_ID=<mainnet-app-id>
ESCROW_APP_ID=<mainnet-app-id>
REPUTATION_APP_ID=<mainnet-app-id>

USDC_ASA_ID=31566704
USDC_DECIMALS=6

SELLER_MNEMONIC=<your-seller-key>
SELLER_ADDRESS=<your-seller-address>

GEMINI_API_KEY=<your-gemini-key>
PINATA_JWT=<your-pinata-key>

OPERATOR_API_KEY=<your-api-key>

LOG_LEVEL=info
```

**Never commit these to Git.**

### Step 5: Deploy

Click "Create Web Service" — Render builds Docker image and deploys automatically.

**Your API is now live at**:
```
https://mercator-reka.onrender.com
```

### Monitoring Deployments

- **Logs**: View real-time logs in Render dashboard
- **Metrics**: CPU, memory, network usage
- **Alerts**: Email on deployment failure
- **Rollback**: Redeploy previous version if needed

---

## Production Environment Setup

### Algorand Mainnet Configuration

Update environment variables for mainnet:

```
# Mainnet endpoints (read-only, free)
ALGOD_URL=https://mainnet-api.algonode.cloud
INDEXER_URL=https://mainnet-idx.algonode.cloud
NETWORK=mainnet

# Mainnet USDC (different app ID)
USDC_ASA_ID=31566704  # MainNet, different from TestNet!

# Mainnet app IDs (after deploying contracts)
INSIGHT_LISTING_APP_ID=<your-app-id>
ESCROW_APP_ID=<your-app-id>
REPUTATION_APP_ID=<your-app-id>
```

### Secrets Management

**Never commit `.env` files to Git.**

Use Render's secure environment variables instead:

1. In Render dashboard → Environment
2. Add each secret as a separate variable
3. Render never exposes values in logs/deployments
4. Use `EnvironmentFile` to load locally

---

## Smart Contract Deployment (MainNet)

### Prerequisites

- Production ALGO and USDC funding
- MainNet-ready wallets
- Security audit completed
- Test suite passing

### Step 1: Deploy Contracts

```bash
# Set environment for MainNet
export NETWORK=mainnet
export ALGOD_URL=https://mainnet-api.algonode.cloud
export DEPLOYER_MNEMONIC="<your-mainnet-mnemonic>"

# Deploy each contract
PYTHONPATH=. python backend/contracts/insight_listing.py
PYTHONPATH=. python backend/contracts/escrow.py
PYTHONPATH=. python backend/contracts/reputation.py

# Save returned app IDs
# Update environment variables with new app IDs
```

### Step 2: Verify Contracts

```bash
# Verify contract creation
PYTHONPATH=. python -c "
from backend.utils.algorand_async import get_app_state
import asyncio

app_id = <your-app-id>
state = asyncio.run(get_app_state(app_id))
print('Contract deployed successfully:', state)
"
```

### Step 3: Fund Initial Escrow

Escrow contract needs minimum funds for first transactions:

```bash
# Send 1 ALGO to escrow app address
PYTHONPATH=. python -c "
from backend.contracts.escrow import get_escrow_address
escrow = get_escrow_address()
print(f'Send 1 ALGO to: {escrow}')
"
```

---

## CI/CD Pipeline

### Automated Testing

Both Vercel and Render can run tests before deploying:

**Pre-deployment test script** (.github/workflows/test.yml):

```yaml
name: Run Tests

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
      - uses: actions/setup-python@v4
        with:
          python-version: 3.12
      - run: pip install -r backend/requirements.txt
      - run: PYTHONPATH=. pytest backend/tests/ -v
```

### Deployment Checklist

Before deploying to production:

- [ ] All tests passing (`pytest backend/tests/`)
- [ ] Frontend build succeeds (`npm run build`)
- [ ] Environment variables set in Vercel + Render
- [ ] Smart contracts deployed to mainnet
- [ ] Contracts app IDs match environment
- [ ] Security audit completed
- [ ] Rate limiting configured
- [ ] Monitoring/alerting set up
- [ ] Backup/recovery plan documented

---

## Monitoring & Logging

### Frontend Monitoring (Vercel)

- **Performance**: Vercel Web Analytics (free)
- **Errors**: Sentry integration (optional)
- **Deployment status**: Real-time in Vercel dashboard

### Backend Monitoring (Render)

- **Logs**: View in Render dashboard
- **Metrics**: CPU, memory, network
- **Uptime**: Status page available
- **Alerts**: Email on failure

### Set Up Sentry (Optional)

For production error tracking:

```bash
pip install sentry-sdk

# Add to backend/main.py
import sentry_sdk
sentry_sdk.init("https://your-key@sentry.io/project-id")
```

---

## Scaling Considerations

### Horizontal Scaling

**Frontend (Vercel)**:
- Automatic (CDN + serverless functions)
- No configuration needed
- Scales to millions of requests/day

**Backend (Render)**:
- Upgrade plan to enable multiple instances
- Load balancer automatically distributes traffic
- Can scale from $7/month to $200+/month

### Database (If Added)

Render can provision PostgreSQL:

1. In Render dashboard → "New +" → "PostgreSQL"
2. Connect to backend service
3. Render handles backups automatically

### Caching

Add Redis caching for frequent queries:

```python
import redis

cache = redis.Redis(host='localhost', port=6379)

# Cache search results
cache.setex(f"insights:{query}", 3600, json.dumps(results))
```

---

## Maintenance & Updates

### Update Dependencies

```bash
# Check for outdated packages
pip list --outdated

# Update requirements.txt
pip install --upgrade -r backend/requirements.txt
pip freeze > backend/requirements_updated.txt

# Test locally before pushing
pytest backend/tests/
```

### Rollback Procedure

If deployment breaks production:

**Vercel**:
1. Go to "Deployments" tab
2. Click the previous working version
3. Click "Redeploy" — instant rollback

**Render**:
1. Go to "Deploys" tab
2. Select previous successful deploy
3. Click "Redeploy" — instant rollback

### Database Migrations

If adding PostgreSQL, use Alembic:

```bash
pip install alembic
alembic revision --autogenerate -m "Add users table"
alembic upgrade head
```

---

## Security Checklist Before Production

- [ ] All secrets in environment variables (not hardcoded)
- [ ] HTTPS enforced (auto with Vercel + Render)
- [ ] CORS configured for your domain only
- [ ] Rate limiting enabled
- [ ] Input validation on all endpoints
- [ ] SQL injection prevention (if using DB)
- [ ] XSS protection (React does this by default)
- [ ] CSRF tokens if needed
- [ ] Log sensitive data redacted
- [ ] Security audit completed

---

## Troubleshooting Deployments

### Vercel Build Fails

```bash
# Check build logs in Vercel dashboard
# Common issues:
# - npm install fails: Clear cache → redeploy
# - Build command error: Check vite.config.ts
# - Missing env vars: Add to Vercel dashboard
```

### Render Container Won't Start

```bash
# Check logs in Render dashboard
# Common issues:
# - Python version mismatch: Use 3.12 in Dockerfile
# - Module not found: Reinstall requirements
# - Port binding: Use PORT env var, not hardcoded
```

### Environment Variable Issues

```bash
# Verify in backend
print(os.getenv('ALGOD_URL'))  # Should print URL

# Check Render dashboard
# Variables not interpolated in start command
# Use in Python: os.getenv('VAR_NAME')
```

---

## Cost Estimation

### Vercel (Frontend)

- **Free tier**: $0/month (includes 100 GB bandwidth)
- **Pro**: $20/month (1 TB bandwidth, priority support)
- **Most projects**: Free tier is sufficient

### Render (Backend)

- **Free tier**: $0/month (sleeps after 15 min inactivity)
- **Starter**: $7/month (never sleeps)
- **Standard**: $25+/month (more CPU/memory)
- **For production**: Recommend Standard plan minimum

### Total Monthly Cost

- Small (<1000 MAU): $0-30/month
- Medium (1000-10k MAU): $30-100/month
- Large (>10k MAU): $200+/month

---

## Next Steps

- **Monitor**: Set up dashboards in Vercel + Render
- **Security**: Run security audit before production
- **Mainnet**: Deploy smart contracts to Algorand MainNet
- **Performance**: Monitor response times and optimize
- **Scaling**: Plan for 10x traffic growth

## Get Help

- **Vercel Docs**: [vercel.com/docs](https://vercel.com/docs)
- **Render Docs**: [render.com/docs](https://render.com/docs)
- **Algorand**: [developer.algorand.org](https://developer.algorand.org/)
