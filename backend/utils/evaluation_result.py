from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CriterionScore(BaseModel):
    model_config = ConfigDict(extra="forbid")

    score: int = Field(ge=0, le=40, description="Points awarded for this criterion")
    evidence_cited: str = Field(
        min_length=10,
        description="Specific text from the listing that justifies this score",
    )
    reasoning: str = Field(
        min_length=20,
        description="One to three sentences explaining the scoring decision",
    )


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="forbid")

    step1_relevance: CriterionScore
    step2_reputation: CriterionScore
    step3_value_for_price: CriterionScore
    step4_specificity: CriterionScore
    total_score: int = Field(ge=0, le=100)
    buy_confidence: int = Field(
        ge=0,
        le=100,
        description="Overall confidence 0-100 derived from the four criterion scores",
    )
    decision: str = Field(pattern="^(BUY|SKIP)$")
    decision_reasoning: str = Field(
        min_length=30,
        description="One sentence explaining the final BUY or SKIP decision",
    )
    improvement_suggestion: str = Field(
        description="What would need to change for a SKIP to become a BUY. Empty string if decision is BUY.",
    )
    evaluation_version: str = Field(default="v2")

    @field_validator("total_score")
    @classmethod
    def _validate_total_score(cls, value: int, info: Any) -> int:
        expected = sum(
            getattr(info.data.get(field_name), "score", 0)
            for field_name in (
                "step1_relevance",
                "step2_reputation",
                "step3_value_for_price",
                "step4_specificity",
            )
        )
        if value != expected:
            raise ValueError(f"total_score must equal the sum of criterion scores ({expected})")
        return value

    @field_validator("buy_confidence")
    @classmethod
    def _validate_buy_confidence(cls, value: int, info: Any) -> int:
        total_score = info.data.get("total_score")
        if total_score is not None and value != total_score:
            raise ValueError("buy_confidence must equal total_score")
        return value

    @field_validator("improvement_suggestion")
    @classmethod
    def _validate_improvement_suggestion(cls, value: str, info: Any) -> str:
        decision = info.data.get("decision")
        if decision == "SKIP" and not value.strip():
            raise ValueError("improvement_suggestion must be non-empty when decision is SKIP")
        return value


_FEW_SHOT_HIGH_LISTING = (
    "RELIANCE.NS is showing a clear cup-and-handle breakout above 2,950 with volume 3.2x the 5-day average. "
    "RSI at 61 - not overbought. Target: 3,100. Stop: 2,920. Risk/reward 5:1. Based on today's 14:30 candle close."
)

_FEW_SHOT_HIGH_EVALUATION = {
    "step1_relevance": {
        "score": 36,
        "evidence_cited": "cup-and-handle pattern explicitly named with specific price level 2,950",
        "reasoning": "This is directly actionable breakout language with a named chart pattern and threshold, so it strongly matches a trading-insight query.",
    },
    "step2_reputation": {
        "score": 18,
        "evidence_cited": "seller has 15 prior purchases, reputation score 82",
        "reasoning": "An 82 reputation score with prior purchases signals trustworthy historical behavior and supports a high-confidence buy.",
    },
    "step3_value_for_price": {
        "score": 17,
        "evidence_cited": "price target and stop-loss are explicitly stated enabling immediate action",
        "reasoning": "The listing provides enough structure to estimate risk and reward quickly, which makes the paid insight materially useful.",
    },
    "step4_specificity": {
        "score": 19,
        "evidence_cited": "specific candle time 14:30, specific price levels, specific volume ratio 3.2x all given",
        "reasoning": "Concrete time, price, and volume details make the setup highly specific and immediately tradable.",
    },
    "total_score": 90,
    "buy_confidence": 90,
    "decision": "BUY",
    "decision_reasoning": "High specificity with named pattern, actionable price levels, and volume confirmation justifies immediate purchase.",
    "improvement_suggestion": "",
    "evaluation_version": "v2",
}

_FEW_SHOT_LOW_LISTING = "NIFTY might go up today based on global cues. Markets are positive. Consider buying."

_FEW_SHOT_LOW_EVALUATION = {
    "step1_relevance": {
        "score": 15,
        "evidence_cited": "vague direction, no specific level",
        "reasoning": "The idea is loosely market-related, but it does not anchor the query to a concrete setup or technical signal.",
    },
    "step2_reputation": {
        "score": 8,
        "evidence_cited": "new seller, reputation 45",
        "reasoning": "A sub-threshold reputation score makes the seller less reliable and weakens trust in the recommendation.",
    },
    "step3_value_for_price": {
        "score": 6,
        "evidence_cited": "no price target, no stop, cannot calculate risk/reward",
        "reasoning": "The listing does not provide enough execution structure to justify meaningful paid value.",
    },
    "step4_specificity": {
        "score": 4,
        "evidence_cited": "no specific prices, no volume data, no candle reference",
        "reasoning": "The statement is generic and lacks the measurable details needed for an actionable trade decision.",
    },
    "total_score": 33,
    "buy_confidence": 33,
    "decision": "SKIP",
    "decision_reasoning": "No actionable price levels or evidence-based directional conviction justify purchasing this insight.",
    "improvement_suggestion": "Add specific entry price, stop-loss, target, and cite at least one technical indicator with its current value to warrant purchase.",
    "evaluation_version": "v2",
}

FEW_SHOT_EXAMPLE_HIGH_SCORE = (
    "Example 1 - High confidence BUY\n\n"
    f"Listing:\n{_FEW_SHOT_HIGH_LISTING}\n\n"
    "Evaluation:\n"
    f"{json.dumps(_FEW_SHOT_HIGH_EVALUATION, indent=2)}"
)

FEW_SHOT_EXAMPLE_LOW_SCORE = (
    "Example 2 - Low confidence SKIP\n\n"
    f"Listing:\n{_FEW_SHOT_LOW_LISTING}\n\n"
    "Evaluation:\n"
    f"{json.dumps(_FEW_SHOT_LOW_EVALUATION, indent=2)}"
)

EVALUATION_JSON_SCHEMA_STRING = json.dumps(EvaluationResult.model_json_schema(), indent=2, sort_keys=True)

# Failure modes this prompt is designed to prevent:
# - Anchoring to 50 by forcing full-range scoring and treating 40-60 as undecided that must be re-evaluated.
# - Grade inflation by making most insights score below 60 and requiring at least three specific data points for scores above 80.
# - Criterion collapse by requiring evidence for each criterion and forcing a low score when specific evidence cannot be named.
EVALUATION_PROMPT_V2_TEMPLATE = """## Section 1 - Role Definition
You are a rigorous financial insight evaluator. Your job is to score trading insights that an autonomous AI agent is considering purchasing.
You must be genuinely critical - grade inflation wastes the agent's capital.
Most insights should score below 60.
A score above 80 is rare and must be justified by at least three specific data points.
If a criterion lands between 40 and 60, you are undecided and must re-evaluate the evidence before finalizing the score.

## Section 2 - Step 1 Relevance to Query
Step 1 - Relevance to query (0-40 points): How directly does this insight address what the agent is searching for?
Award 30-40 only if the insight uses market-specific terminology matching the query and names at least one indicator or pattern.
Award 15-29 for general relevance.
Award 0-14 if the connection to the query is tenuous.
You must cite at least one specific piece of evidence from the listing text for this criterion. If you cannot, the score must be low.

## Section 3 - Step 2 Seller Reliability Proxy
Step 2 - Seller reliability proxy (0-20 points): Based on the provided reputation score.
80-100: 18-20 points.
70-79: 14-17 points.
60-69: 10-13 points.
50-59: 6-9 points.
Below 50: 0 points immediately - SKIP with no further evaluation.
You must cite at least one specific piece of evidence from the listing text for this criterion. If you cannot, the score must be low.

## Section 4 - Step 3 Value For Price
Step 3 - Value for price (0-20 points): Does the insight justify its cost?
An insight with a specific entry, target, and stop-loss at 0.50 USDC is better value than a vague insight at 0.05 USDC.
Award 16-20 if all three levels are stated.
Award 8-15 if at least one specific level is given.
Award 0-7 for directional-only insights.
You must cite at least one specific piece of evidence from the listing text for this criterion. If you cannot, the score must be low.

## Section 5 - Step 4 Specificity and Actionability
Step 4 - Specificity and actionability (0-20 points): Award 16-20 if the insight names a specific timeframe, specific price level, and cites at least one quantified indicator.
Award 8-15 for partial specificity.
Award 0-7 for generic statements.
You must cite at least one specific piece of evidence from the listing text for this criterion. If you cannot, the score must be low.

## Section 6 - Worked Examples
{few_shot_example_high_score}

{few_shot_example_low_score}

## Section 7 - Actual Listing
Now evaluate this listing.
Query: {query}
Seller reputation: {reputation_score}
Price: {price_usdc} USDC
Insight: {insight_text}
Output only valid JSON matching this exact structure:
{json_schema_string}
Do not include markdown fences.
Do not add commentary outside the JSON.
"""


def build_evaluation_prompt(*, query: str, reputation_score: int, price_usdc: float, insight_text: str) -> str:
    return EVALUATION_PROMPT_V2_TEMPLATE.format(
        query=query,
        reputation_score=reputation_score,
        price_usdc=price_usdc,
        insight_text=insight_text,
        json_schema_string=EVALUATION_JSON_SCHEMA_STRING,
        few_shot_example_high_score=FEW_SHOT_EXAMPLE_HIGH_SCORE,
        few_shot_example_low_score=FEW_SHOT_EXAMPLE_LOW_SCORE,
    )


def _extract_json_object(text: str) -> str:
    candidate = text.strip()
    if candidate.startswith("```"):
        candidate = re.sub(r"^```(?:json)?\s*", "", candidate, flags=re.IGNORECASE)
        candidate = re.sub(r"\s*```$", "", candidate).strip()

    start = candidate.find("{")
    end = candidate.rfind("}")
    if start == -1 or end == -1 or end <= start:
        raise ValueError("No JSON object found in evaluation response")
    return candidate[start : end + 1]


def parse_evaluation_result(text: str) -> EvaluationResult:
    return EvaluationResult.model_validate_json(_extract_json_object(text))