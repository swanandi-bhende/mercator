# Round 3 Context

## Current Project State
Mercator is a working Algorand TestNet marketplace for trading insights. The main flow is already in place:

- Sellers list an insight through the React frontend.
- The FastAPI backend uploads content to IPFS and stores listing metadata on-chain.
- The agent searches and evaluates listings using semantic ranking plus on-chain reputation.
- x402 executes the micropayment path with atomic settlement.
- Post-payment flow delivers the insight, releases escrow, and updates reputation.

The verified proof artifacts are already documented in [Security.md](Security.md) and the root [README.md](../README.md), including the latest successful payment, escrow release, and +10 reputation update.

## Round 3 Direction
Round 3 should be treated as a hardening and submission-polish phase, not a rewrite. The priority is to preserve the existing working flow while improving reliability, clarity, and presentation.

Focus areas:

- Keep the TestNet demo path stable end to end.
- Preserve transaction semantics, transaction IDs, and existing verification evidence.
- Tighten docs, tests, and runtime behavior together when behavior changes.
- Avoid broad refactors that do not directly support Round 3 goals.

## Repo Hygiene Rules
These are the guardrails to keep the repository safe and easy to work in:

- Never commit `.env`, `.env.*`, private keys, mnemonics, or other local secrets.
- Keep edits small and targeted; avoid unrelated formatting or cleanup.
- Update tests and docs when user-visible behavior, tx flow, or fallback strings change.
- Preserve the public API and the monkeypatch-friendly module-level clients in `backend/tools/post_payment_flow.py`.
- Treat `demo.sh` and the regression suite as the main acceptance gates before merging significant changes.
- Keep commit-ready changes focused so GitHub diffs stay easy to review.

## Compatibility Anchors
Several tests depend on specific behavior and wording, so treat these as stable unless you are intentionally updating the tests too:

- `backend/tests/test_micropayment_cycle.py` expects the semantic score formula to stay `0.7 * relevance + 0.3 * reputation_norm` for the top 3 ranking path.
- `backend/tools/post_payment_flow.py` should keep module-level `listing_client` and `escrow_client` for monkeypatch-based tests.
- `complete_purchase_flow` should still raise for payment-confirmation timeout and listing-not-found paths.
- x402 insufficient-balance handling should include the phrase `insufficient balance`.
- Post-payment fallback wording should continue to include `Escrow release skipped` and `could not be retrieved`.

## Operational Notes
- Local Python lives in `.venv` and frontend dependencies live in `frontend/node_modules`.
- Deployment targets remain Render for the backend and Vercel for the frontend.
- The current implementation uses Algorand TestNet, ARC4 contracts, IPFS via Pinata, and x402 for settlement.
- If a Round 3 doc conflicts with verified code, prefer the code path and update the doc rather than drifting the implementation.
