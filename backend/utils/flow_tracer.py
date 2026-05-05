from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


@dataclass
class FlowTracerEvent:
    event_type: str
    plain_english_description: str
    metadata: dict[str, object] = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


_current_session_id: str | None = None
_events: list[FlowTracerEvent] = []


def start_session(session_id: str | None = None) -> str:
    global _current_session_id, _events
    _current_session_id = session_id or uuid4().hex
    _events = []
    return _current_session_id


def get_session_id() -> str | None:
    return _current_session_id


def record_event(
    event_type: str,
    plain_english_description: str,
    metadata: dict[str, object] | None = None,
    *,
    autonomous: bool = False,
) -> None:
    if autonomous and not plain_english_description.startswith("[AUTO-APPROVED]"):
        plain_english_description = f"[AUTO-APPROVED] {plain_english_description}"

    _events.append(
        FlowTracerEvent(
            event_type=event_type,
            plain_english_description=plain_english_description,
            metadata=metadata or {},
        )
    )


def export_json(session_id: str) -> str:
    output_dir = Path("logs")
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / f"flow_trace_{session_id}.json"
    payload = {
        "session_id": session_id,
        "events": [asdict(event) for event in _events],
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    return str(path)