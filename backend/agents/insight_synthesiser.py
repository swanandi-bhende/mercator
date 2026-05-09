"""Gemini-backed insight synthesis for the Mercator curator pipeline."""

from __future__ import annotations

import json
import os
import re
import warnings
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Sequence

warnings.filterwarnings(
    "ignore",
    message="'_UnionGenericAlias' is deprecated and slated for removal in Python 3.17",
    category=DeprecationWarning,
    module=r"google\.genai\.types",
)

from langchain_google_genai import ChatGoogleGenerativeAI

try:
    from newsapi import NewsApiClient
except Exception:  # pragma: no cover
    NewsApiClient = None  # type: ignore[assignment]

from .market_data_fetcher import MarketSnapshot


PROMPT_TEMPLATE = """You are the Mercator curator.
Return one JSON object only with these keys:
insight_text, directional_view, confidence_score, key_metrics_cited.

Rules:
- Output valid JSON only. No markdown, no code fences, no extra commentary.
- confidence_score must be a number from 0 to 100.
- directional_view must be one of: bullish, bearish, neutral.
- insight_text must be concise and synthesis-oriented.
- key_metrics_cited must be a list of short strings.
- Use headlines only as context; paraphrase implications and never quote any headline verbatim.

Output only valid JSON with no markdown formatting and no preamble, matching this exact schema: {{insight_text, directional_view, confidence_score, key_metrics_cited}}.

Market snapshot:
{snapshot_json}

Recent headlines:
{headlines_json}
"""


@dataclass(slots=True)
class SynthesisedInsight:
    """Curator output ready to be priced and published."""

    symbol: str
    provider_symbol: str
    generated_at: datetime
    insight_text: str
    directional_view: str
    confidence_score: int
    key_metrics_cited: list[str]
    synthesis_quality: str
    price_usdc: float
    market_snapshot: dict[str, Any]
    raw_payload: dict[str, Any]
    model: str

    @property
    def headline(self) -> str:
        return self.insight_text

    @property
    def summary(self) -> str:
        return self.insight_text

    @property
    def thesis(self) -> str:
        return self.insight_text

    @property
    def direction(self) -> str:
        return self.directional_view

    @property
    def confidence(self) -> float:
        return self.confidence_score / 100.0

    @property
    def evidence(self) -> list[str]:
        return list(self.key_metrics_cited)

    @property
    def tags(self) -> list[str]:
        return list(self.key_metrics_cited)


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)).strip())
    except Exception:
        return default


def _strip_json_fences(text: str) -> str:
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = re.sub(r"^```(?:json)?\s*", "", stripped, flags=re.IGNORECASE)
        stripped = re.sub(r"\s*```$", "", stripped)
    return stripped.strip()


def _extract_json_object(text: str) -> dict[str, Any]:
    cleaned = _strip_json_fences(text)
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", cleaned, flags=re.DOTALL)
        if not match:
            raise
        return json.loads(match.group(0))


def _normalise_lines(values: Sequence[str]) -> list[str]:
    return [value.strip() for value in values if value and value.strip()]


def _fetch_headlines(symbol: str, company_name: str | None = None, limit: int = 5) -> list[str]:
    api_key = os.getenv("NEWSAPI_KEY", os.getenv("NEWSAPI_API_KEY", "")).strip()
    if not api_key or NewsApiClient is None:
        return []

    client = NewsApiClient(api_key=api_key)
    query_terms = [symbol]
    if company_name:
        query_terms.append(company_name)
    query = " OR ".join(f'"{term}"' for term in _normalise_lines(query_terms))
    response = client.get_everything(
        q=query or symbol,
        language="en",
        sort_by="publishedAt",
        page_size=limit,
    )
    articles = response.get("articles", []) if isinstance(response, dict) else []
    headlines: list[str] = []
    for article in articles:
        title = article.get("title") if isinstance(article, dict) else None
        if title:
            headlines.append(str(title))
    return headlines[:limit]


def _build_prompt(snapshot: MarketSnapshot, headlines: Sequence[str]) -> str:
    return PROMPT_TEMPLATE.format(
        snapshot_json=json.dumps(snapshot.as_dict(), sort_keys=True),
        headlines_json=json.dumps(list(headlines), sort_keys=True),
    )


def _estimate_price_usdc(snapshot: MarketSnapshot, quality_score: int, confidence_score: int) -> float:
    min_price = max(0.01, _float_env("CURATOR_INSIGHT_PRICE_MIN_USDC", 0.05))
    max_price = max(min_price, _float_env("CURATOR_INSIGHT_PRICE_MAX_USDC", 0.30))
    composite_score = max(0, min(100, int(round((quality_score + confidence_score) / 2))))
    if getattr(snapshot, "price_change_pct", None) is not None and abs(float(snapshot.price_change_pct)) > 5:
        composite_score = max(0, composite_score - 5)
    composite = composite_score / 100.0
    return round(min_price + ((max_price - min_price) * composite), 2)


def _normalise_confidence(value: Any) -> int:
    try:
        raw = float(value)
    except Exception:
        raw = 0.0
    confidence = int(round(raw * 100)) if 0.0 <= raw <= 1.0 else int(round(raw))
    return max(0, min(100, confidence))


def _synthesis_quality_label(confidence_score: int) -> str:
    if confidence_score >= 70:
        return "high"
    if confidence_score >= 50:
        return "medium"
    return "low"


def _parse_payload_fields(payload: dict[str, Any]) -> tuple[str, str, int, list[str]]:
    insight_text = str(payload.get("insight_text", payload.get("headline", "")) or "").strip()
    directional_view = str(payload.get("directional_view", payload.get("direction", "neutral")) or "neutral").strip()
    if directional_view not in {"bullish", "bearish", "neutral"}:
        directional_view = "neutral"
    confidence_score = _normalise_confidence(payload.get("confidence_score", payload.get("confidence", 0)))
    key_metrics = payload.get("key_metrics_cited", payload.get("evidence", []))
    if not isinstance(key_metrics, list):
        key_metrics = []
    metrics = [str(item).strip() for item in key_metrics if str(item).strip()]
    return insight_text, directional_view, confidence_score, metrics


def synthesise_insight(
    snapshot: MarketSnapshot,
    *,
    company_name: str | None = None,
    model_name: str | None = None,
    headlines: Sequence[str] | None = None,
) -> SynthesisedInsight:
    """Synthesize a sellable curator insight from a market snapshot and recent headlines."""

    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise ValueError("GEMINI_API_KEY is required for curator synthesis")

    selected_model = model_name or os.getenv("CURATOR_GEMINI_MODEL", os.getenv("GEMINI_MODEL", "gemini-2.0-flash"))
    minimum_quality_raw = _float_env("CURATOR_MIN_DATA_QUALITY_SCORE", 60)
    minimum_quality = int(round(minimum_quality_raw * 100)) if 0.0 <= minimum_quality_raw <= 1.0 else int(round(minimum_quality_raw))
    news_headlines = list(headlines) if headlines is not None else list(getattr(snapshot, "headlines", []) or [])
    if not news_headlines:
        news_headlines = _fetch_headlines(snapshot.symbol, company_name=company_name)

    llm = ChatGoogleGenerativeAI(
        model=selected_model,
        google_api_key=api_key,
        temperature=float(os.getenv("CURATOR_GEMINI_TEMPERATURE", "0.2")),
    )

    prompt = _build_prompt(snapshot, news_headlines)
    last_error: Exception | None = None

    def _run_once() -> tuple[dict[str, Any], str, str, int, list[str]]:
        response = llm.invoke(prompt)
        content = getattr(response, "content", response)
        raw_payload = _extract_json_object(str(content))
        insight_text, directional_view, confidence_score, key_metrics = _parse_payload_fields(raw_payload)
        if not insight_text:
            raise ValueError("Synthesised insight missing insight_text")
        return raw_payload, insight_text, directional_view, confidence_score, key_metrics

    try:
        raw_payload, insight_text, directional_view, confidence_score, key_metrics = _run_once()
    except Exception as exc:
        last_error = exc
        try:
            raw_payload, insight_text, directional_view, confidence_score, key_metrics = _run_once()
        except Exception as exc2:
            last_error = exc2
            snapshot_quality = int(round(float(getattr(snapshot, "data_quality_score", 0))))
            price_usdc = _estimate_price_usdc(snapshot, snapshot_quality, 0)
            return SynthesisedInsight(
                symbol=snapshot.symbol,
                provider_symbol=snapshot.provider_symbol,
                generated_at=datetime.now(timezone.utc),
                insight_text="",
                directional_view="neutral",
                confidence_score=0,
                key_metrics_cited=[],
                synthesis_quality="low",
                price_usdc=price_usdc,
                market_snapshot=snapshot.as_dict(),
                raw_payload={"error": str(last_error) if last_error else "unknown"},
                model=selected_model,
            )

    snapshot_quality = int(round(float(getattr(snapshot, "data_quality_score", 0))))
    synthesis_quality = _synthesis_quality_label(confidence_score)
    if snapshot_quality < minimum_quality:
        synthesis_quality = "low"

    price_usdc = _estimate_price_usdc(snapshot, snapshot_quality, confidence_score)

    return SynthesisedInsight(
        symbol=snapshot.symbol,
        provider_symbol=snapshot.provider_symbol,
        generated_at=datetime.now(timezone.utc),
        insight_text=insight_text,
        directional_view=directional_view,
        confidence_score=confidence_score,
        key_metrics_cited=key_metrics,
        synthesis_quality=synthesis_quality,
        price_usdc=price_usdc,
        market_snapshot=snapshot.as_dict(),
        raw_payload=raw_payload,
        model=selected_model,
    )