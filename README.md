# Mercator

Mercator is an Agentic Commerce marketplace on Algorand TestNet where human sellers list trading insights and AI agents discover, evaluate, and purchase them.

## Round 2 Status

- [x] InsightListing contract implemented in ARC4
- [x] Escrow contract implemented in ARC4
- [x] Reputation contract implemented in ARC4
- [x] Contracts compiled and TEAL generated
- [x] ARC specs and typed clients generated
- [x] Contracts deployed to TestNet
- [x] Phase 6 `/list` backend endpoint (validation -> IPFS pin -> on-chain ASA mint -> confirmation polling)
- [x] Phase 7 agent scaffolding (`backend/agent.py` with Gemini init + tool placeholders)
- [x] Semantic search tools scaffolding (`backend/tools/semantic_search.py` + IPFS fetch helper)
- [x] Core semantic search tool implemented (live listing fetch + IPFS content retrieval + ranked top-3 results with relevance/reputation weighting + cache/retry)
- [x] Agent evaluation chain added (CoT evaluation prompt template + async evaluate_insights runnable before payment decision)
- [x] Agent chain sequencing hardened (semantic_search -> evaluate_insights -> BUY/SKIP parsing -> payment gate)
- [x] Agent executor configured for auditable runs (`verbose=True`, `return_intermediate_steps=True` where supported)
- [x] Phase 8 agent evaluation chain (CoT evaluation prompt template + async evaluate_insights runnable + BUY/SKIP decision parsing)
- [x] Phase 9 step-by-step CoT reasoning (EVALUATION_PROMPT_TEMPLATE with 4-step reasoning: relevance scoring, reputation threshold ≥50 enforcement, value-for-price calculation >8.0, auditable BUY/SKIP decision)
- [x] Phase 9 evaluation runnable integrated into agent chain (semantic_search -> evaluate_insights -> decision_parser -> payment gate)
- [x] Phase 9 visibility & auditability (verbose=True, return_intermediate_steps=True, markdown reasoning blocks, regex/Pydantic decision extraction)
- [~] Phase 7 agent uses graceful fallback on Gemini free-tier limits/model availability (returns non-crashing offline response when API is unavailable)
- [~] Local end-to-end tests (no automated test suite yet)

## TestNet Identifiers

- `INSIGHT_LISTING_APP_ID=758022443`
- `ESCROW_APP_ID=758022447`
- `REPUTATION_APP_ID=758022459`
- `ESCROW_ADDRESS=262TFFBGXEAOOLQECJ4SNEVNQ2QFCCCVZ5K6ZT42ETIWBYDI63JLKSGHDI`
- `SAMPLE_ASA_ID=758023286`

## Phase 9: CoT Reasoning & Evaluation Logic

**Completed Steps:**

1. ✅ **EVALUATION_PROMPT_TEMPLATE Created** ([agent.py](backend/agent.py#L48))
   - Enforces 4-step reasoning: relevance scoring (0-100), reputation check (≥50), value-for-price calc (rel/price > 8.0), final BUY/SKIP decision
   - Visible markdown reasoning blocks for auditability

2. ✅ **Hard-Coded Quality Rules**
   - Reputation threshold: `≥50` (immediate SKIP if <50)
   - Value-for-price threshold: `>8.0` (relevance_score / price_in_usdc)
   - Enforced inside EVALUATION_PROMPT_TEMPLATE and agent flow

3. ✅ **Async evaluate_insights() Runnable** ([agent.py](backend/agent.py#L105))
   - Takes semantic search results + user query
   - Invokes Gemini to run full 4-step CoT reasoning
   - Graceful fallback when Gemini unavailable (free-tier quota)
   - Returns structured state with `evaluation` text + `decision` enum

4. ✅ **Decision Parsing** ([agent.py](backend/agent.py#L89))
   - PydanticOutputParser for EvaluationDecision model
   - Regex fallback: `Decision\s*:\s*(BUY|SKIP)` pattern
   - Reliable extraction even under API constraints

5. ✅ **Integration into Agent Chain** ([agent.py](backend/agent.py#L145))
   - Flow: `semantic_search(query)` → `evaluate_insights(results, query)` → `_parse_decision(eval_text)` → payment gate (approval-gated)
   - Agent blocks BUY decisions if `user_approval=False`

6. ✅ **Auditable Execution** ([agent.py](backend/agent.py#L155))
   - `verbose=True` + `return_intermediate_steps=True` in AgentExecutor
   - Console logs visible reasoning + decision trace
   - File logs to stderr for production audit trail

**Test Validation:**
```bash
python -m backend.agent
# Output: Agent evaluates "Show me the best NIFTY 24500 call insight"
# Returns: Visible reasoning steps + clear Decision: BUY or SKIP
```

## Environment Files

- `.env`: local working configuration
- `.env.testnet`: TestNet deployment configuration

## Manual TestNet Validation

- create_listing succeeded on InsightListing (`LISTING_ID` advanced from `1` to `2`)
- escrow release flow succeeded with grouped payment (`release_after_payment` returned `true`)
- reputation initialized and updated (`get_score` before `0`, after `update_score` -> `77`)
- IPFS helper test succeeded (`CID=QmSqR9oHZWbHDj1jgoyeKw7nuzYB6bDiLgySC7SxXjzwWF`) and CID-linked listing call confirmed on explorer
- Phase 6 live `/list` API call succeeded (`listing_id=3`, `asa_id=758048084`) with explorer tx: https://testnet.explorer.algorand.org/tx/WOZDMPMPHAVBAZ4RMCY4Y3MVC5V2HNTIROPMLUOVKRP5GEETAPKA
- Semantic search tool standalone run succeeded against live TestNet listings (`python -m backend.tools.semantic_search`) and returned top-3 ranked matches
- Agent local run verified with new evaluation chain (`python -m backend.agent`) and returned explicit `Decision: SKIP` fallback under Gemini free-tier 429 limits
- explorer links:
	- https://testnet.algoexplorer.io/tx/3TSEMSSU4GHZJ4SQAR6D64BGRPZZOUXCAUHRTOCAZGV5GUX2B7KQ
	- https://testnet.algoexplorer.io/tx/VZDJCINLUM72I6TTGNMVO7XXOK4ZI3HSS2XH3EICQVUJME6A5EMQ
	- https://testnet.algoexplorer.io/tx/33M5NFCM376EVMHD4LBBL2L3HWNQ5Y7Y6BS3W6GWKTMRRKDEXTSQ
	- https://testnet.algoexplorer.io/tx/T3CZ7OQU63NWW3ZXWH5C5DZDH6BS4JFL5FLBYQWEUAHE2R5XPZZQ
	- https://testnet.algoexplorer.io/tx/VU4ANW2TFIDVKQXDYSJK7MNWANHEDFY5ZDLSWGGVPBMRURBFULTA
	- https://testnet.algoexplorer.io/tx/224C63VBDIBVPE5XMWR4ULJORGHQMIWN6FK6M2RW2H3ZC76LUESQ
	- https://testnet.algoexplorer.io/tx/EDJZHOLXVNCOCMFE3VBFJWRI6244E2GC775FWDZ5ZW7FSWHEJWLQ
