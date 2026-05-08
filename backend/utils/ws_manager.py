from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from collections import deque
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import WebSocket, WebSocketDisconnect


logger = logging.getLogger("mercator.websocket")


@dataclass
class ConnectedClient:
    client_id: str
    websocket: WebSocket
    connected_at: str
    last_ping_at: float


class WebSocketManager:
    def __init__(self) -> None:
        self.active_connections: dict[str, ConnectedClient] = {}
        self.recent_events: deque[dict] = deque(maxlen=300)

    async def connect(self, websocket: WebSocket) -> str:
        await websocket.accept()
        client_id = str(uuid4())
        self.active_connections[client_id] = ConnectedClient(
            client_id=client_id,
            websocket=websocket,
            connected_at=datetime.now(timezone.utc).isoformat(),
            last_ping_at=time.time(),
        )
        logger.info("[WS] Client %s connected. Total connections: %s", client_id, len(self.active_connections))
        return client_id

    def disconnect(self, client_id: str) -> None:
        if client_id in self.active_connections:
            self.active_connections.pop(client_id, None)
            logger.info("[WS] Client %s disconnected. Total connections: %s", client_id, len(self.active_connections))

    async def broadcast(self, event_type: str, payload: dict) -> None:
        message = {
            "event_type": event_type,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "payload": payload,
        }

        self.recent_events.appendleft(message)

        if not self.active_connections:
            return

        await asyncio.gather(
            *[self._send_to_client(client_id, message) for client_id in list(self.active_connections.keys())],
            return_exceptions=True,
        )

    async def _send_to_client(self, client_id: str, message: dict) -> None:
        client = self.active_connections.get(client_id)
        if client is None:
            return

        try:
            await client.websocket.send_json(message)
        except (WebSocketDisconnect, Exception):
            self.disconnect(client_id)

    def get_connection_count(self) -> int:
        return len(self.active_connections)

    def get_recent_events(self, limit: int = 20) -> list[dict]:
        safe_limit = max(1, min(limit, 300))
        return list(self.recent_events)[:safe_limit]


ws_manager = WebSocketManager()
