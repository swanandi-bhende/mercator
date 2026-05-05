"""Autonomous trading insight buyer agent using LangChain + Gemini LLM.

Purpose: Implements AI buyer logic for semantic search → evaluation → x402 micropayment.
Uses chain-of-thought reasoning (CoT) with on-chain reputation checks and value heuristics
to autonomously decide whether to purchase trading insights and execute x402 payments.

Key Components:
- SYSTEM_PROMPT: Agent instructions (search, evaluate, BUY/SKIP decision, x402 payment logic).
- semantic_search_tool: Finds top 3 insights by relevance + reputation score.
- evaluate_insights: 2-step evaluation (relevance check, reputation gate, value-for-price).
- trigger_x402_payment: Simulates and executes Algorand micropayment + escrow release + content delivery.
- run_agent: Main orchestration - chains tool calls and returns decision + payment status.
"""

from dotenv import load_dotenv
import argparse
import asyncio
import os
import logging
import re
from typing import Any
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.tools import tool
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import PydanticOutputParser
from pydantic import BaseModel, Field

try:
    from langchain.agents import create_tool_calling_agent, AgentExecutor  # type: ignore
except ImportError:
    create_tool_calling_agent = None
    AgentExecutor = None

from langchain.agents import create_agent

from contracts.insight_listing import InsightListingClient
from backend.contracts.escrow.smart_contracts.artifacts.escrow.escrow_client import EscrowClient
from backend.contracts.reputation.smart_contracts.artifacts.reputation.reputation_client import ReputationClient
from backend.tools.semantic_search import semantic_search as semantic_search_tool
from backend.tools.x402_payment import trigger_x402_payment, validate_x402_payment
from backend.utils.error_handler import low_reputation, payment_rejected
from backend.utils.flow_tracer import export_json, record_event, start_session
from backend.utils.runtime_env import configure_demo_logging, normalize_network_env


normalize_network_env()
demo_logger = configure_demo_logging()
if not os.getenv("GEMINI_API_KEY"):
    load_dotenv(".env.testnet", override=True)

AUTO_MIN_RELEVANCE = int(os.getenv("AUTO_MIN_RELEVANCE", "85"))
AUTO_MIN_REPUTATION = int(os.getenv("AUTO_MIN_REPUTATION", "70"))
AUTO_MAX_PRICE_USDC = float(os.getenv("AUTO_MAX_PRICE_USDC", "0.30"))

if not 0 <= AUTO_MIN_RELEVANCE <= 100:
    raise ValueError("AUTO_MIN_RELEVANCE must be between 0 and 100")
if not 0 <= AUTO_MIN_REPUTATION <= 100:
    raise ValueError("AUTO_MIN_REPUTATION must be between 0 and 100")
if not 0.01 <= AUTO_MAX_PRICE_USDC <= 10.0:
    raise ValueError("AUTO_MAX_PRICE_USDC must be between 0.01 and 10.0")

from backend.utils.auto_approval import check_auto_conditions

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("mercator.log", mode="a"),
    ],
    force=True,
)
logger = logging.getLogger(__name__)

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ALGOD_URL = os.getenv("ALGOD_URL")
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")
ROUND_INTERVAL = float(os.getenv("ROUND_INTERVAL", "10"))

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY not found in .env")

llm = ChatGoogleGenerativeAI(
    model=GEMINI_MODEL,
    google_api_key=GEMINI_API_KEY,
    temperature=0.3,
    max_retries=0,
)

# Purpose: Global system prompt that constrains agent behavior and tool usage safety.
# It enforces explicit approval before x402 payment and disallows synthetic/fake insight data.
SYSTEM_PROMPT = """You are Mercator, an autonomous AI trading-insight buyer on Algorand. Your job is to:
1) Search for real human trading insights using semantic search
2) Evaluate them using on-chain reputation and price
3) Reason step-by-step whether to buy
4) ONLY call trigger_x402_payment if Decision is BUY and user has typed 'approve'
5) Never generate fake data - always use real human insights from blockchain

x402 MICROPAYMENT PROTOCOL:
- When you decide BUY, user MUST explicitly type "approve" to proceed
- Never trigger payments without explicit user approval
- Payment requires: 1) BUY decision, 2) User types "approve", 3) Payment simulation passes
- After payment confirms on TestNet, buyer gets instant IPFS content access

If any tool call or backend step fails, respond naturally and helpfully with:
"Sorry, I encountered an issue: [clear message]. Would you like to try a different insight or check your wallet balance?"
"""

# Purpose: Structured evaluation prompt for deterministic BUY/SKIP reasoning output.
# The agent must score relevance, enforce reputation >= 50, compute value/price, then decide.
EVALUATION_PROMPT_TEMPLATE = """You must evaluate semantic search results step-by-step before any payment decision.

User Query: {query}
Semantic Search Results:
{semantic_results}

Follow this exact sequence:
1) First, rate relevance 0-100 to the user query and NSE context.
2) Second, check on-chain reputation. Reputation must be 50 or higher - otherwise SKIP.
3) Third, calculate value-for-price using: value_for_price = relevance_score / price_in_usdc.
4) Fourth, only BUY if value_for_price > 8.0. Otherwise SKIP.

IMPORTANT: If Decision is BUY, the user will be prompted to type "approve" to trigger x402 micropayment.
The actual payment will only execute after explicit user approval and simulation validation.
If any tool call fails, respond naturally with:
"Sorry, I encountered an issue: [clear message]. Would you like to try a different insight or check your wallet balance?"

You MUST output a visible markdown reasoning block followed by a final decision line:
```markdown
Reasoning:
1. Relevance: ...
2. Reputation check: ...
3. Value-for-price: ...
4. Final rationale: ...
```
Decision: BUY or SKIP
"""

prompt = ChatPromptTemplate.from_messages(
    [
        SystemMessage(content=SYSTEM_PROMPT),
        ("system", EVALUATION_PROMPT_TEMPLATE),
        ("system", "Semantic search results:\n{semantic_results}"),
        ("human", "{input}"),
    ]
)


@tool
def on_chain_query(listing_id: int) -> str:
    """Placeholder tool for reading on-chain listing details."""
    return f"on_chain_query placeholder: listing_id={listing_id}."


# Purpose: Ordered tool registry for agent runtime.
# 1) on_chain_query placeholder (future detail fetch),
# 2) semantic_search for candidate insights,
# 3) trigger_x402_payment for purchase execution,
# 4) validate_x402_payment for on-chain confirmation checks.
tools = [on_chain_query, semantic_search_tool, trigger_x402_payment, validate_x402_payment]


class EvaluationDecision(BaseModel):
    decision: str = Field(description="Final decision, either BUY or SKIP")


decision_parser = PydanticOutputParser(pydantic_object=EvaluationDecision)


def _parse_decision(eval_text: str) -> str:
    """Extract BUY or SKIP decision from LLM evaluation output.
    
    Tries pydantic parser first, then regex fallback (\"Decision: BUY\" or \"Decision: SKIP\").
    Defaults to SKIP if decision cannot be parsed (safety default).
    
    Purpose: Ensure agent decision is always machine-readable regardless of LLM response format.
    """
    try:
        parsed = decision_parser.parse(eval_text)
        decision = parsed.decision.upper().strip()
        if decision in {"BUY", "SKIP"}:
            return decision
    except Exception:
        pass

    match = re.search(r"Decision\s*:\s*(BUY|SKIP)", eval_text, re.IGNORECASE)
    if match:
        return match.group(1).upper()
    return "SKIP"


async def evaluate_insights(state: dict) -> dict:
    """Chain-of-thought evaluation of semantic search results.
    
    Purpose: Use LLM to reason step-by-step:
    1. Rate relevance of top result to user query (0-100 scale).
    2. Check seller on-chain reputation (must be >= 50 or SKIP).
    3. Calculate value_for_price = relevance / price_usdc (must be > 8.0 to BUY).
    4. Return BUY or SKIP decision with full reasoning.
    
    Returns: Updated state dict with evaluation (reasoning text) + decision (BUY|SKIP).
    """
    query = state.get("query", "")
    semantic_results = state.get("semantic_results", "")
    eval_prompt = EVALUATION_PROMPT_TEMPLATE.format(
        query=query,
        semantic_results=semantic_results,
    )

    try:
        eval_response = await asyncio.to_thread(llm.invoke, eval_prompt)
        eval_text = getattr(eval_response, "content", str(eval_response))
    except Exception as exc:  # noqa: BLE001
        error_text = str(exc)
        is_rate_limit = "429" in error_text or "TooManyRequests" in error_text
        is_quota_error = "RESOURCE_EXHAUSTED" in error_text
        if is_rate_limit or is_quota_error:
            logger.warning("Evaluation step hit Gemini limit; falling back to SKIP")
            eval_text = (
                "Reasoning: Gemini limit reached during evaluation; cannot verify safely.\n"
                "Decision: SKIP"
            )
        else:
            raise

    decision = _parse_decision(eval_text)
    updated_state = dict(state)
    updated_state["evaluation"] = eval_text
    updated_state["decision"] = decision
    return updated_state


@dataclass
class AutonomousSessionResult:
    session_id: str
    rounds_completed: int
    purchases_made: int
    skips: int
    errors: int
    total_usdc_spent: float

if create_tool_calling_agent and AgentExecutor:
    # Preferred path: explicit tool-calling agent with intermediate steps and parsing safeguards.
    agent = create_tool_calling_agent(llm, tools, prompt)
    agent_executor = AgentExecutor(
        agent=agent,
        tools=tools,
        verbose=True,
        handle_parsing_errors=True,
        return_intermediate_steps=True,
    )
else:
    # Compatibility fallback for environments lacking create_tool_calling_agent APIs.
    logger.info(
        "LangChain create_tool_calling_agent/AgentExecutor not available; "
        "using create_agent compatibility mode"
    )
    agent = create_agent(
        model=llm,
        tools=tools,
        system_prompt=SYSTEM_PROMPT,
    )
    agent_executor = agent


async def run_agent(
    user_query: str = "",
    user_approval: bool = False,
    buyer_address: str = "",
    user_approval_input: str = "",
    force_buy_for_test: bool = False,
    target_listing_id: int | None = None,
    autonomous_mode: bool = False,
    rounds: int = 1,
    query: str | None = None,
    dry_run: bool = False,
):
    """Run the Mercator buyer agent with full x402 micropayment flow.
    
    Purpose: Autonomous agent orchestration that chains:
    1. semantic_search_tool: Find top 3 insights by relevance + reputation.
    2. evaluate_insights: LLM chain-of-thought (CoT) reasoning with reputation + value heuristics.
    3. user approval gate: If BUY decision, require user to type \"approve\" to proceed.
    4. trigger_x402_payment: Simulate x402 micropayment \u2192 execute on TestNet \u2192 release escrow.
    5. validate_x402_payment: Confirm on-chain settlement and content delivery.
    
    Returns:
        dict: {success (bool), decision (BUY|SKIP|ERROR), evaluation (reasoning text),
               payment_status (tx_id/confirmation if BUY), message (user-facing text)}
    
    Args:
        user_query (str): The search query for trading insights.
        user_approval_input (str): User's explicit approval (must be \"approve\" to trigger payment).
        buyer_address (str): Buyer's Algorand wallet address.
        force_buy_for_test (bool): Force BUY decision for operational tests (skip reputation gate).
    
    Key Behaviors:
    - SKIP decision: returned when reputation < 50, value-for-price <= 8.0, or no results found.
    - BUY decision: requires explicit user_approval_input = \"approve\" to execute payment.
    - Error recovery: gracefully falls back to SKIP on network/Gemini issues.
    """
    effective_query = query if query is not None else user_query
    logger.info(
        "Starting agent run with user_approval=%s, user_approval_input=%s, autonomous_mode=%s, rounds=%s, dry_run=%s",
        user_approval,
        user_approval_input,
        autonomous_mode,
        rounds,
        dry_run,
    )

    def _agent_error_result(clear_message: str, evaluation: str | None = None) -> dict[str, Any]:
        natural = (
            f"Sorry, I encountered an issue: {clear_message}. "
            "Would you like to try a different insight or check your wallet balance?"
        )
        return {
            "success": False,
            "decision": "ERROR",
            "evaluation": evaluation or "",
            "message": natural,
            "error": clear_message,
        }

    def _extract_top_reputation(results: Any) -> float | None:
        try:
            parsed = results
            if isinstance(parsed, str):
                import json
                parsed = json.loads(parsed)
            if isinstance(parsed, list) and parsed:
                first = parsed[0]
                if isinstance(first, dict) and "reputation" in first:
                    return float(first.get("reputation", 0.0))
            if isinstance(parsed, dict):
                matches = parsed.get("matches", [])
                if isinstance(matches, list) and matches:
                    top = matches[0]
                    if isinstance(top, dict) and "reputation" in top:
                        return float(top.get("reputation", 0.0))
        except Exception:
            return None
        return None

    def _extract_top_listing_details(results: Any) -> dict[str, Any] | None:
        try:
            parsed = results
            if isinstance(parsed, str):
                import json
                parsed = json.loads(parsed)

            top_listing: dict[str, Any] | None = None
            if isinstance(parsed, list) and parsed:
                first = parsed[0]
                if isinstance(first, dict):
                    top_listing = first
            elif isinstance(parsed, dict):
                matches = parsed.get("matches", [])
                if isinstance(matches, list) and matches:
                    first = matches[0]
                    if isinstance(first, dict):
                        top_listing = first

            if not top_listing:
                return None

            listing_id = top_listing.get("listing_id")
            if listing_id is not None:
                listing_id = int(listing_id)

            if "price_usdc" in top_listing:
                price_usdc = float(top_listing.get("price_usdc", 1.0))
            elif "price_micro_usdc" in top_listing:
                price_usdc = float(top_listing.get("price_micro_usdc", 1_000_000)) / 1_000_000
            elif "price" in top_listing:
                raw_price = float(top_listing.get("price", 1.0))
                price_usdc = raw_price / 1_000_000 if raw_price > 1000 else raw_price
            else:
                price_usdc = 1.0

            if "relevance_score" in top_listing:
                relevance_score = int(round(float(top_listing.get("relevance_score", 0))))
            elif "relevance" in top_listing:
                raw_relevance = float(top_listing.get("relevance", 0.0))
                relevance_score = int(round(raw_relevance * 100 if raw_relevance <= 1 else raw_relevance))
            else:
                relevance_score = 0

            reputation_score = int(round(float(top_listing.get("reputation", 0))))

            return {
                "listing_id": listing_id,
                "price_usdc": price_usdc,
                "relevance_score": relevance_score,
                "reputation_score": reputation_score,
                "raw": top_listing,
            }
        except Exception:
            return None

    def _record_autonomous_approval(
        *,
        listing_id: int | None,
        relevance_score: int,
        reputation_score: int,
        price_usdc: float,
        result: object,
    ) -> None:
        if not autonomous_mode:
            return
        record_event(
            "autonomous_approval_check",
            "Autonomous approval threshold check completed",
            {
                "mode": "autonomous",
                "listing_id": listing_id,
                "relevance_score": relevance_score,
                "reputation_score": reputation_score,
                "price_usdc": price_usdc,
                "auto_min_relevance": AUTO_MIN_RELEVANCE,
                "auto_min_reputation": AUTO_MIN_REPUTATION,
                "auto_max_price": AUTO_MAX_PRICE_USDC,
                "approved": bool(getattr(result, "approved", False)),
                "rejection_reason": getattr(result, "rejection_reason", ""),
            },
            autonomous=bool(getattr(result, "approved", False)),
        )

    if target_listing_id is not None:
        semantic_results = {"matches": [{"listing_id": int(target_listing_id)}]}
        eval_state = {
            "decision": "BUY",
            "evaluation": (
                "Reasoning: explicit target listing provided by checkout context.\n"
                "Decision: BUY"
            ),
        }
        logger.info(
            "target listing provided; bypassing search/evaluation and selecting listing %s",
            target_listing_id,
        )
    else:
        try:
            semantic_results = await semantic_search_tool.ainvoke({"query": effective_query})
            eval_state = await evaluate_insights(
                {"query": effective_query, "semantic_results": semantic_results}
            )
        except Exception as exc:  # noqa: BLE001
            logger.error("Agent pre-evaluation failed | error=%s", exc, exc_info=True)
            return _agent_error_result(str(exc))

    top_reputation = _extract_top_reputation(semantic_results)
    if top_reputation is not None and top_reputation < 50 and not force_buy_for_test:
        rep_message = low_reputation(logger, f"top_reputation={top_reputation}")
        return {
            "success": True,
            "decision": "SKIP",
            "evaluation": eval_state.get("evaluation", ""),
            "message": rep_message,
        }

    if force_buy_for_test:
        logger.info("force_buy_for_test enabled; overriding decision to BUY")
        eval_state["decision"] = "BUY"

    if eval_state.get("decision") == "SKIP":
        evaluation_text = str(eval_state.get("evaluation", ""))
        skip_message = "Skipped based on evaluation rules (reputation/value-for-price)."
        if "reputation" in evaluation_text.lower():
            skip_message = low_reputation(logger, evaluation_text)
        return {
            "success": True,
            "decision": "SKIP",
            "evaluation": eval_state.get("evaluation"),
            "message": skip_message,
            "skip_reason": skip_message,
        }

    listing_details = _extract_top_listing_details(semantic_results)
    autonomous_payment_ready = False
    auto_approval_result = None
    if autonomous_mode and eval_state.get("decision") == "BUY" and listing_details is not None:
        auto_approval_result = check_auto_conditions(
            relevance_score=int(listing_details["relevance_score"]),
            reputation_score=int(listing_details["reputation_score"]),
            price_usdc=float(listing_details["price_usdc"]),
        )
        autonomous_payment_ready = bool(auto_approval_result.approved)
        _record_autonomous_approval(
            listing_id=int(listing_details["listing_id"]) if listing_details.get("listing_id") is not None else None,
            relevance_score=int(listing_details["relevance_score"]),
            reputation_score=int(listing_details["reputation_score"]),
            price_usdc=float(listing_details["price_usdc"]),
            result=auto_approval_result,
        )
        logger.info(
            "Autonomous approval check | approved=%s | reason=%s | thresholds=%s",
            auto_approval_result.approved,
            auto_approval_result.rejection_reason or "passed",
            auto_approval_result.thresholds_used,
        )
        if not auto_approval_result.approved:
            return {
                "success": True,
                "decision": "SKIP",
                "evaluation": eval_state.get("evaluation", ""),
                "message": auto_approval_result.rejection_reason,
                "skip_reason": auto_approval_result.rejection_reason,
                "thresholds_used": auto_approval_result.thresholds_used,
            }

    # If decision is BUY, check for user approval
    if eval_state.get("decision") == "BUY":
        # Check if user has provided explicit approval
        if not autonomous_payment_ready and (not user_approval_input or user_approval_input.lower().strip() != "approve"):
            logger.info("Decision is BUY but user approval is missing; awaiting 'approve'")
            pending_message = "✓ AI has approved the insight! Type 'approve' to trigger x402 micropayment and purchase."
            if autonomous_mode and auto_approval_result is not None and not auto_approval_result.approved:
                pending_message = (
                    f"Autonomous thresholds not met: {auto_approval_result.rejection_reason}. "
                    "Type 'approve' to trigger x402 micropayment and purchase."
                )
            return {
                "success": True,
                "decision": "BUY_PENDING_APPROVAL",
                "evaluation": eval_state.get("evaluation"),
                "message": pending_message,
                "next_step": "User must type 'approve' to confirm and proceed with payment",
            }

        if dry_run:
            return {
                "success": True,
                "decision": "BUY",
                "evaluation": eval_state.get("evaluation"),
                "payment_status": {
                    "dry_run": True,
                    "autonomous_mode": autonomous_payment_ready,
                    "thresholds_used": getattr(auto_approval_result, "thresholds_used", {}),
                },
                "message": "Dry run complete: evaluation passed; payment broadcast skipped.",
            }
        
        # User has approved - trigger x402 payment
        logger.info("Decision is BUY and user approval confirmed ('approve'); triggering x402 payment")
        
        # Parse listing details from semantic results
        try:
            import json
            listing_id: int | None = int(target_listing_id) if target_listing_id is not None else None
            price = 1.0
            if listing_details is not None:
                if listing_details.get("listing_id") is not None:
                    listing_id = int(listing_details["listing_id"])
                price = float(listing_details["price_usdc"])

            if listing_id is None or listing_id < 0:
                return _agent_error_result(
                    "No valid on-chain listing_id found for the selected insight",
                    str(eval_state.get("evaluation", "")),
                )

            if not buyer_address:
                buyer_address = (
                    os.getenv("BUYER_WALLET", "").strip()
                    or os.getenv("BUYER_ADDRESS", "").strip()
                    or os.getenv("DEPLOYER_ADDRESS", "").strip()
                )

            if buyer_address:
                logger.info(f"Triggering x402 payment: listing {listing_id}, price {price}, buyer {buyer_address}")

                # Call trigger_x402_payment with user approval input
                payment_response = await trigger_x402_payment.ainvoke({
                    "listing_id": listing_id,
                    "buyer_address": buyer_address,
                    "amount_usdc": price,
                    "user_approval_input": user_approval_input,
                    "autonomous_mode": autonomous_payment_ready,
                    "relevance_score": int(listing_details["relevance_score"]) if listing_details else None,
                    "reputation_score": int(listing_details["reputation_score"]) if listing_details else None,
                    "price_usdc": float(listing_details["price_usdc"]) if listing_details else price,
                })

                payment_payload = payment_response
                payment_success = True
                try:
                    import json
                    payment_payload = json.loads(payment_response) if isinstance(payment_response, str) else payment_response
                    if isinstance(payment_payload, dict):
                        payment_success = bool(payment_payload.get("success", False))
                except Exception:
                    payment_success = False

                result = {
                    "success": payment_success,
                    "decision": "BUY",
                    "evaluation": eval_state.get("evaluation"),
                    "payment_status": payment_payload,
                    "message": (
                        "✓ x402 micropayment executed successfully"
                        if payment_success
                        else _agent_error_result(
                            payment_rejected(logger, str(payment_payload)),
                            str(eval_state.get("evaluation", "")),
                        )["message"]
                    ),
                }
                demo_logger.info("Payment approved")
                logger.info(f"Payment triggered: {result}")
                return result
        except Exception as e:
            logger.error(f"Error triggering x402 payment: {str(e)}", exc_info=True)
            return _agent_error_result(str(e), str(eval_state.get("evaluation", "")))

    payload: dict[str, Any]
    if create_tool_calling_agent and AgentExecutor:
        payload = {
            "input": effective_query,
            "semantic_results": semantic_results,
        }
    else:
        payload = {"messages": [{"role": "user", "content": effective_query}]}

    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        try:
            result = await asyncio.to_thread(agent_executor.invoke, payload)
            if isinstance(result, dict):
                result["evaluation"] = eval_state.get("evaluation")
                result["decision"] = eval_state.get("decision")
            if user_approval is False and eval_state.get("decision") == "BUY":
                logger.info("Decision is BUY but user approval is missing; payment blocked")
            return result
        except Exception as exc:  # noqa: BLE001
            error_text = str(exc)
            is_quota_error = (
                "429" in error_text
                or "RESOURCE_EXHAUSTED" in error_text
                or "TooManyRequests" in error_text
            )
            is_model_error = (
                "404" in error_text
                or "NOT_FOUND" in error_text
                or "is not found" in error_text
                or "not supported for generateContent" in error_text
            )
            if is_quota_error and attempt < max_attempts:
                delay_seconds = 2 ** attempt
                logger.warning(
                    "Gemini quota/rate limit hit; retrying in %ss (attempt %s/%s)",
                    delay_seconds,
                    attempt,
                    max_attempts,
                )
                await asyncio.sleep(delay_seconds)
                continue

            if is_quota_error:
                logger.warning(
                    "Gemini quota exhausted on free tier; returning fallback response"
                )
                return _agent_error_result(
                    "Gemini free-tier quota reached. Skipping live AI reasoning for now",
                    str(eval_state.get("evaluation", "")),
                )

            if is_model_error:
                logger.warning(
                    "Configured Gemini model is unavailable for this key; returning fallback response"
                )
                return _agent_error_result(
                    (
                        f"Configured model '{GEMINI_MODEL}' is unavailable for this API key. "
                        "Set GEMINI_MODEL in .env to an available model and retry"
                    ),
                    str(eval_state.get("evaluation", "")),
                )

            raise


async def run_autonomous_loop(query: str, rounds: int, dry_run: bool) -> AutonomousSessionResult:
    session_id = start_session()
    purchases_made = 0
    skips = 0
    errors = 0
    total_usdc_spent = 0.0

    logger.info(
        "[AUTONOMOUS] Starting session | session_id=%s | query=%s | rounds=%s | round_interval=%s | thresholds=(relevance=%s, reputation=%s, price=%s)",
        session_id,
        query,
        rounds,
        ROUND_INTERVAL,
        AUTO_MIN_RELEVANCE,
        AUTO_MIN_REPUTATION,
        AUTO_MAX_PRICE_USDC,
    )

    for round_num in range(rounds):
        logger.info("[AUTONOMOUS] Starting round %s of %s", round_num + 1, rounds)
        try:
            result = await run_agent(
                user_query=query,
                autonomous_mode=True,
                dry_run=dry_run,
            )
            decision = str(result.get("decision", "")) if isinstance(result, dict) else "ERROR"
            if decision == "BUY" and bool(result.get("success", False)):
                purchases_made += 1
                payment_status = result.get("payment_status", {}) if isinstance(result, dict) else {}
                if isinstance(payment_status, dict):
                    total_usdc_spent += float(payment_status.get("payment_details", {}).get("amount_usdc", 0.0) or 0.0)
                logger.info("[AUTONOMOUS] Round %s purchase complete | result=%s", round_num + 1, result)
            elif decision == "SKIP":
                skips += 1
                logger.info("[AUTONOMOUS] Round %s skipped | reason=%s", round_num + 1, result.get("skip_reason") if isinstance(result, dict) else "unknown")
            else:
                errors += 1
                logger.info("[AUTONOMOUS] Round %s error | result=%s", round_num + 1, result)
        except Exception as exc:  # noqa: BLE001
            errors += 1
            logger.error("[AUTONOMOUS] Round %s raised error: %s", round_num + 1, exc, exc_info=True)

        if round_num < rounds - 1:
            await asyncio.sleep(ROUND_INTERVAL)

    logger.info(
        "[AUTONOMOUS] Completed %s rounds. Total purchased: %s. Total skipped: %s. Total errors: %s.",
        rounds,
        purchases_made,
        skips,
        errors,
    )
    export_json(session_id)
    return AutonomousSessionResult(
        session_id=session_id,
        rounds_completed=rounds,
        purchases_made=purchases_made,
        skips=skips,
        errors=errors,
        total_usdc_spent=total_usdc_spent,
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Mercator AI Buyer Agent")
    parser.add_argument(
        "--autonomous",
        action="store_true",
        help="Run without human approval gates when trust thresholds are met",
    )
    parser.add_argument(
        "--rounds",
        type=int,
        default=1,
        help="Number of purchase cycles to run in autonomous mode before exiting",
    )
    parser.add_argument(
        "--query",
        type=str,
        default=None,
        help="Search query to use for insight discovery (uses a default NSE query if not provided)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run the full evaluation and decision logic but skip actual x402 payment broadcast",
    )
    args = parser.parse_args()

    print("\n" + "=" * 80)
    print("MERCATOR AGENT FULL PURCHASE FLOW TEST")
    print("=" * 80 + "\n")

    default_query = "Show me the best NSE insight"

    async def _run_cli() -> None:
        if args.autonomous:
            result = await run_autonomous_loop(
                query=args.query or default_query,
                rounds=args.rounds,
                dry_run=args.dry_run,
            )
            print(result)
        else:
            result = await run_agent(
                user_query=default_query,
                buyer_address=os.getenv("DEPLOYER_ADDRESS", ""),
                user_approval_input="approve",
                force_buy_for_test=True,
                autonomous_mode=False,
                rounds=args.rounds,
                query=args.query,
                dry_run=args.dry_run,
            )

            print("Decision:", result.get("decision"))
            print("Message:", result.get("message"))
            payment_status = result.get("payment_status", "")
            if payment_status:
                print("\nPayment status payload:\n", payment_status)

    asyncio.run(_run_cli())


