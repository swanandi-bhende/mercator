from __future__ import annotations

import asyncio
import json
import logging
import time
import uuid
from typing import Any

from pydantic import ValidationError

try:
    from google import genai
except Exception:  # pragma: no cover - tests will mock genai usage
    genai = None

from backend.utils.flow_tracer import tracer
from backend.utils.evaluation_result import EvaluationResult, build_evaluation_prompt
from backend.utils.db import record_evaluation
from backend.utils.ws_manager import ws_manager
from backend.utils.error_handler import retry_with_backoff
from backend.utils.failure_simulator import is_active as failure_is_active
from backend.utils.error_handler import AgentError, ErrorCode as EH_ErrorCode, ErrorHandler

logger = logging.getLogger(__name__)


@retry_with_backoff()
async def evaluate_insight(query: str, listing: Any, reputation_score: int) -> EvaluationResult:
    """Evaluate a single SearchResult listing and return an EvaluationResult.

    Implements retry and fallback logic per spec.
    """
    event_id = tracer.start_event(
        "agent.evaluation_started",
        wallet_involved=getattr(listing, "seller_wallet", getattr(listing, "seller", None)),
        plain_english_description=f"Evaluating listing {getattr(listing, 'listing_id', '')} for query: {query}",
    )

    prompt = build_evaluation_prompt(
        query=query,
        reputation_score=int(reputation_score),
        price_usdc=float(getattr(listing, "price_usdc", getattr(listing, "price", 0.0))),
        insight_text=str(getattr(listing, "insight_preview", getattr(listing, "text", ""))),
    )

    gemini_call_count = 0
    start_ts = time.time()

    # Initialize client/model
    if genai is None:
        raise RuntimeError("genai client not available in this environment")

    # Demo scenario: simulate Gemini rate limit
    if failure_is_active("gemini_rate_limit"):
        raise ErrorHandler.handle(AgentError(EH_ErrorCode.GEMINI_RATE_LIMIT, context={"function": "evaluate_insight"}))

    client = genai.Client()
    model = client.models

    # First attempt
    try:
        resp = await asyncio.to_thread(model.generate_content, prompt)
        response_text = getattr(resp, "text", "") or str(resp)
        response_text = response_text.strip().removeprefix("```json").removesuffix("```").strip()
        result = EvaluationResult.model_validate_json(response_text)
        gemini_call_count = 1
        duration_ms = int((time.time() - start_ts) * 1000)

        # persist and broadcast
        eval_id = str(uuid.uuid4())
        record_evaluation({
            "evaluation_id": eval_id,
            "session_id": tracer.get_current_session_id() or "",
            "listing_id": str(getattr(listing, "listing_id", "")),
            "seller_wallet": getattr(listing, "seller_wallet", getattr(listing, "seller", "")),
            "query": query,
            "reputation_score_at_eval": reputation_score,
            "price_usdc_at_eval": float(getattr(listing, "price_usdc", getattr(listing, "price", 0.0))),
            "step1_relevance_score": result.step1_relevance.score,
            "step1_evidence": result.step1_relevance.evidence_cited,
            "step2_reputation_score": result.step2_reputation.score,
            "step2_evidence": result.step2_reputation.evidence_cited,
            "step3_value_score": result.step3_value_for_price.score,
            "step3_evidence": result.step3_value_for_price.evidence_cited,
            "step4_specificity_score": result.step4_specificity.score,
            "step4_evidence": result.step4_specificity.evidence_cited,
            "total_score": result.total_score,
            "buy_confidence": result.buy_confidence,
            "decision": result.decision,
            "decision_reasoning": result.decision_reasoning,
            "improvement_suggestion": result.improvement_suggestion,
            "evaluation_version": result.evaluation_version,
            "gemini_call_count": gemini_call_count,
            "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "duration_ms": duration_ms,
        })

        # Broadcast
        try:
            await ws_manager.broadcast(
                "agent_evaluation_completed",
                {
                    "listing_id": str(getattr(listing, "listing_id", "")),
                    "query": query,
                    "total_score": result.total_score,
                    "buy_confidence": result.buy_confidence,
                    "decision": result.decision,
                    "decision_reasoning": result.decision_reasoning,
                    "improvement_suggestion": result.improvement_suggestion,
                    "step_scores": [
                        result.step1_relevance.score,
                        result.step2_reputation.score,
                        result.step3_value_for_price.score,
                        result.step4_specificity.score,
                    ],
                },
            )
        except Exception:
            logger.debug("Websocket broadcast failed for evaluation completion")

        tracer.resolve_event(event_id, "success", plain_english_description="Evaluation completed successfully")
        return result

    except ValidationError as exc:  # noqa: BLE001
        logger.warning("Evaluation JSON validation failed on first attempt: %s", str(exc))
        logger.debug("First attempt raw response (truncated): %s", response_text[:500] if 'response_text' in locals() else "")
        # Retry with schema-enforced structured output
        try:
            retry_prompt = prompt + "\nYour previous response failed JSON validation. Output ONLY the raw JSON object. Do not include any text before the opening brace or after the closing brace."
            retry_resp = await asyncio.to_thread(
                model.generate_content,
                retry_prompt,
                {"response_mime_type": "application/json", "response_schema": EvaluationResult.model_json_schema()},
            )
            retry_text = getattr(retry_resp, "text", "") or str(retry_resp)
            retry_text = retry_text.strip().removeprefix("```json").removesuffix("```").strip()
            result = EvaluationResult.model_validate_json(retry_text)
            gemini_call_count = 2
            duration_ms = int((time.time() - start_ts) * 1000)

            eval_id = str(uuid.uuid4())
            record_evaluation({
                "evaluation_id": eval_id,
                "session_id": tracer.get_current_session_id() or "",
                "listing_id": str(getattr(listing, "listing_id", "")),
                "seller_wallet": getattr(listing, "seller_wallet", getattr(listing, "seller", "")),
                "query": query,
                "reputation_score_at_eval": reputation_score,
                "price_usdc_at_eval": float(getattr(listing, "price_usdc", getattr(listing, "price", 0.0))),
                "step1_relevance_score": result.step1_relevance.score,
                "step1_evidence": result.step1_relevance.evidence_cited,
                "step2_reputation_score": result.step2_reputation.score,
                "step2_evidence": result.step2_reputation.evidence_cited,
                "step3_value_score": result.step3_value_for_price.score,
                "step3_evidence": result.step3_value_for_price.evidence_cited,
                "step4_specificity_score": result.step4_specificity.score,
                "step4_evidence": result.step4_specificity.evidence_cited,
                "total_score": result.total_score,
                "buy_confidence": result.buy_confidence,
                "decision": result.decision,
                "decision_reasoning": result.decision_reasoning,
                "improvement_suggestion": result.improvement_suggestion,
                "evaluation_version": result.evaluation_version,
                "gemini_call_count": gemini_call_count,
                "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_ms": duration_ms,
            })

            try:
                await ws_manager.broadcast(
                    "agent_evaluation_completed",
                    {
                        "listing_id": str(getattr(listing, "listing_id", "")),
                        "query": query,
                        "total_score": result.total_score,
                        "buy_confidence": result.buy_confidence,
                        "decision": result.decision,
                        "decision_reasoning": result.decision_reasoning,
                        "improvement_suggestion": result.improvement_suggestion,
                        "step_scores": [
                            result.step1_relevance.score,
                            result.step2_reputation.score,
                            result.step3_value_for_price.score,
                            result.step4_specificity.score,
                        ],
                    },
                )
            except Exception:
                logger.debug("Websocket broadcast failed for evaluation completion (retry)")

            tracer.resolve_event(event_id, "success", plain_english_description="Evaluation completed on retry")
            return result

        except Exception as retry_exc:  # noqa: BLE001
            logger.error("Evaluation retry also failed: %s", retry_exc)
            # Conservative fallback
            # Build a validator-compliant fallback EvaluationResult with minimal informative text
            fallback_payload = {
                "step1_relevance": {"score": 0, "evidence_cited": "no listing data", "reasoning": "Fallback: model failed to produce valid relevance evidence."},
                "step2_reputation": {"score": 0, "evidence_cited": "no seller evidence", "reasoning": "Fallback: model failed to produce valid reputation evidence."},
                "step3_value_for_price": {"score": 0, "evidence_cited": "no price info", "reasoning": "Fallback: model failed to produce valid value-for-price evidence."},
                "step4_specificity": {"score": 0, "evidence_cited": "no listing text", "reasoning": "Fallback: model failed to produce valid specificity evidence."},
                "total_score": 0,
                "buy_confidence": 0,
                "decision": "SKIP",
                "decision_reasoning": "Evaluation failed due to model output error — defaulting to skip for safety. Retry evaluation when model quota is available.",
                "improvement_suggestion": "Provide at least one listing with concrete entry/stop/target and a seller reputation signal.",
                "evaluation_version": "v2",
            }
            fallback = EvaluationResult.model_validate_json(json.dumps(fallback_payload))
            gemini_call_count = 0
            duration_ms = int((time.time() - start_ts) * 1000)
            eval_id = str(uuid.uuid4())
            record_evaluation({
                "evaluation_id": eval_id,
                "session_id": tracer.get_current_session_id() or "",
                "listing_id": str(getattr(listing, "listing_id", "")),
                "seller_wallet": getattr(listing, "seller_wallet", getattr(listing, "seller", "")),
                "query": query,
                "reputation_score_at_eval": reputation_score,
                "price_usdc_at_eval": float(getattr(listing, "price_usdc", getattr(listing, "price", 0.0))),
                "step1_relevance_score": 0,
                "step1_evidence": "",
                "step2_reputation_score": 0,
                "step2_evidence": "",
                "step3_value_score": 0,
                "step3_evidence": "",
                "step4_specificity_score": 0,
                "step4_evidence": "",
                "total_score": 0,
                "buy_confidence": 0,
                "decision": "SKIP",
                "decision_reasoning": "Evaluation failed due to model output error — defaulting to skip for safety",
                "improvement_suggestion": "",
                "evaluation_version": "v2",
                "gemini_call_count": gemini_call_count,
                "evaluated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "duration_ms": duration_ms,
            })

            try:
                await ws_manager.broadcast(
                    "agent_evaluation_completed",
                    {
                        "listing_id": str(getattr(listing, "listing_id", "")),
                        "query": query,
                        "total_score": 0,
                        "buy_confidence": 0,
                        "decision": "SKIP",
                        "decision_reasoning": "Evaluation failed due to model output error — defaulting to skip for safety",
                        "improvement_suggestion": "",
                        "step_scores": [0, 0, 0, 0],
                    },
                )
            except Exception:
                logger.debug("Websocket broadcast failed for evaluation fallback")

            tracer.resolve_event(event_id, "skipped", plain_english_description="Evaluation failed; fallback applied")
            return fallback
