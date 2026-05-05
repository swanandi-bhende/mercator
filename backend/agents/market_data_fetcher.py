"""Market data snapshot retrieval for the Mercator curator pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone, timedelta
from typing import Any

import os
import httpx
import yfinance as yf


def _coerce_float(value: Any) -> float | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return float(value)
    except Exception:
        return None


def _coerce_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        if isinstance(value, str) and not value.strip():
            return None
        return int(float(value))
    except Exception:
        return None


def _normalise_symbol(symbol: str) -> str:
    cleaned = symbol.strip().upper()
    if not cleaned:
        raise ValueError("symbol must not be empty")
    if "." not in cleaned:
        return f"{cleaned}.NS"
    return cleaned


def _lookup(mapping: Any, *keys: str) -> Any:
    for key in keys:
        if isinstance(mapping, dict) and key in mapping:
            return mapping[key]
        try:
            value = mapping.get(key)  # type: ignore[call-arg]
        except Exception:
            value = None
        if value is not None:
            return value
        try:
            value = getattr(mapping, key)
        except Exception:
            value = None
        if value is not None:
            return value
    return None


@dataclass(slots=True)
class MarketSnapshot:
    """Compact market snapshot used by the curator synthesis step."""

    symbol: str
    display_name: str
    provider_symbol: str
    fetched_at: str
    source: str = "yfinance"
    last_price: float | None = None
    previous_close: float | None = None
    open_price: float | None = None
    day_high: float | None = None
    day_low: float | None = None
    volume_today: int | None = None
    avg_volume_5d: int | None = None
    volume_ratio: float | None = None
    price_change_pct: float | None = None
    price_vs_day_range_pct: float | None = None
    market_cap: int | None = None
    currency: str | None = None
    trailing_pe: float | None = None
    headlines: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def data_quality_score(self) -> int:
        # Compute integer 0-100 score per spec
        score = 100
        # price change missing
        if self.price_change_pct is None:
            score -= 30
        # volume missing
        if self.volume_today is None:
            score -= 20
        # no headlines
        if not self.headlines:
            score -= 20
        # volume ratio cannot be calculated
        if self.volume_ratio is None:
            score -= 10
        # price range calc fails
        if self.price_vs_day_range_pct is None:
            score -= 10
        return max(0, min(100, int(score)))

    def as_dict(self) -> dict[str, Any]:
        return {
            "symbol": self.symbol,
            "display_name": self.display_name,
            "provider_symbol": self.provider_symbol,
            "fetched_at": self.fetched_at,
            "source": self.source,
            "last_price": self.last_price,
            "previous_close": self.previous_close,
            "open_price": self.open_price,
            "day_high": self.day_high,
            "day_low": self.day_low,
            "avg_volume_5d": self.avg_volume_5d,
            "volume_today": self.volume_today,
            "volume_ratio": self.volume_ratio,
            "price_change_pct": self.price_change_pct,
            "price_vs_day_range_pct": self.price_vs_day_range_pct,
            "market_cap": self.market_cap,
            "currency": self.currency,
            "trailing_pe": self.trailing_pe,
            "headlines": list(self.headlines),
            "notes": list(self.notes),
            "data_quality_score": self.data_quality_score,
        }


def _symbol_display_name(provider_symbol: str) -> str:
    base = provider_symbol.replace(".NS", "")
    return base


def _safe_headlines(provider_symbol: str) -> list[str]:
    headlines: list[str] = []
    try:
        api_key = os.getenv("NEWSAPI_KEY", os.getenv("NEWSAPI_API_KEY", "")).strip()
        if not api_key:
            return []
        six_hours_ago = (datetime.now(timezone.utc) - timedelta(hours=6)).isoformat()
        params = {
            "q": f"NSE {provider_symbol.replace('.NS', '')}",
            "from": six_hours_ago,
            "sortBy": "publishedAt",
            "language": "en",
            "pageSize": 3,
            "apiKey": api_key,
        }
        resp = httpx.get("https://newsapi.org/v2/everything", params=params, timeout=10.0)
        if resp.status_code != 200:
            return []
        body = resp.json()
        for article in body.get("articles", [])[:3]:
            title = article.get("title") if isinstance(article, dict) else None
            if title:
                headlines.append(str(title))
    except Exception:
        return []
    return headlines[:3]


def _empty_snapshot(symbol: str, provider_symbol: str, notes: list[str] | None = None) -> MarketSnapshot:
    return MarketSnapshot(
        symbol=symbol.strip().upper(),
        display_name=_symbol_display_name(provider_symbol),
        provider_symbol=provider_symbol,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        headlines=[],
        notes=notes or [],
    )


def fetch_market_snapshot(symbol: str) -> MarketSnapshot:
    """Fetch a single market snapshot for an NSE symbol or Yahoo Finance ticker."""

    provider_symbol = _normalise_symbol(symbol)
    ticker = yf.Ticker(provider_symbol)

    # Requirement: any fast_info failure should not raise; return zero-quality snapshot.
    try:
        fast_info = getattr(ticker, "fast_info", {}) or {}
    except Exception as exc:
        return _empty_snapshot(symbol, provider_symbol, notes=[f"fast_info unavailable: {exc}"])

    try:
        history = ticker.history(period="5d", interval="1d", auto_adjust=False)
    except Exception:
        history = None

    latest_row = None
    if history is not None and getattr(history, "empty", True) is False:
        latest_row = history.iloc[-1]

    notes: list[str] = []
    last_price = _coerce_float(
        _lookup(fast_info, "last_price", "lastPrice", "regularMarketPrice", "current_price", "currentPrice")
    )
    previous_close = _coerce_float(_lookup(fast_info, "previous_close", "previousClose"))
    open_price = _coerce_float(_lookup(fast_info, "open", "openPrice", "regularMarketOpen"))
    day_high = _coerce_float(_lookup(fast_info, "day_high", "dayHigh", "regularMarketDayHigh"))
    day_low = _coerce_float(_lookup(fast_info, "day_low", "dayLow", "regularMarketDayLow"))
    volume_today = _coerce_int(_lookup(fast_info, "last_volume", "lastVolume", "regularMarketVolume", "volume"))
    market_cap = _coerce_int(_lookup(fast_info, "market_cap", "marketCap", "marketCapitalization"))
    currency = _lookup(fast_info, "currency")
    trailing_pe = _coerce_float(_lookup(fast_info, "trailing_pe", "trailingPE"))

    if latest_row is not None:
        if last_price is None:
            last_price = _coerce_float(latest_row.get("Close") or latest_row.get("close"))
        if previous_close is None:
            previous_close = _coerce_float(latest_row.get("Close") or latest_row.get("close"))
        if open_price is None:
            open_price = _coerce_float(latest_row.get("Open") or latest_row.get("open"))
        if day_high is None:
            day_high = _coerce_float(latest_row.get("High") or latest_row.get("high"))
        if day_low is None:
            day_low = _coerce_float(latest_row.get("Low") or latest_row.get("low"))
        if volume_today is None:
            volume_today = _coerce_int(latest_row.get("Volume") or latest_row.get("volume"))

    # compute 5-day average volume
    avg_volume_5d = None
    try:
        if history is not None and getattr(history, "empty", True) is False:
            history_volume = history.get("Volume") if hasattr(history, "get") else None
            if history_volume is not None:
                avg_volume_5d = _coerce_int(getattr(history_volume, "mean", lambda: None)())
    except Exception:
        avg_volume_5d = None

    # derived metrics
    price_change_pct = None
    try:
        if last_price is not None and previous_close not in (None, 0):
            price_change_pct = round(((last_price - previous_close) / previous_close) * 100.0, 4)
    except Exception:
        price_change_pct = None

    volume_ratio = None
    try:
        if volume_today is not None and avg_volume_5d not in (None, 0):
            volume_ratio = round(float(volume_today) / float(avg_volume_5d), 4)
    except Exception:
        volume_ratio = None

    price_vs_day_range_pct = None
    try:
        if last_price is not None and day_low is not None and day_high is not None and day_high != day_low:
            range_pos = (last_price - day_low) / (day_high - day_low)
            price_vs_day_range_pct = round(max(0.0, min(1.0, range_pos)) * 100.0, 2)
    except Exception:
        price_vs_day_range_pct = None

    headlines = _safe_headlines(provider_symbol)

    if last_price is None:
        notes.append("current price unavailable from fast_info/history")
    if previous_close is None:
        notes.append("previous close unavailable from fast_info/history")
    if volume_today is None:
        notes.append("volume unavailable from fast_info/history")

    return MarketSnapshot(
        symbol=symbol.strip().upper(),
        display_name=_symbol_display_name(provider_symbol),
        provider_symbol=provider_symbol,
        fetched_at=datetime.now(timezone.utc).isoformat(),
        last_price=last_price,
        previous_close=previous_close,
        open_price=open_price,
        day_high=day_high,
        day_low=day_low,
        volume_today=volume_today,
        avg_volume_5d=avg_volume_5d,
        volume_ratio=volume_ratio,
        price_change_pct=price_change_pct,
        price_vs_day_range_pct=price_vs_day_range_pct,
        market_cap=market_cap,
        currency=currency if isinstance(currency, str) else None,
        trailing_pe=trailing_pe,
        headlines=headlines,
        notes=notes,
    )