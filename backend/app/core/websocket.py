import asyncio
import json
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from fastapi import WebSocket
from pydantic import BaseModel

logger = logging.getLogger("roadresq.ws")


class WebSocketManager:
    """Manages active WebSocket connections grouped by booking channels."""

    def __init__(self) -> None:
        # booking_id -> set of connected WebSockets
        self._active_connections: dict[str, set[WebSocket]] = {}
        self._lock = asyncio.Lock()

    async def connect(self, booking_id: str, websocket: WebSocket) -> None:
        """Registers an authenticated WebSocket connection to a booking channel."""
        await websocket.accept()
        async with self._lock:
            if booking_id not in self._active_connections:
                self._active_connections[booking_id] = set()
            self._active_connections[booking_id].add(websocket)
        logger.info("WebSocket client connected to booking channel: %s", booking_id)

    async def disconnect(self, booking_id: str, websocket: WebSocket) -> None:
        """Removes a disconnected WebSocket from the booking channel."""
        async with self._lock:
            if booking_id in self._active_connections:
                self._active_connections[booking_id].discard(websocket)
                if not self._active_connections[booking_id]:
                    del self._active_connections[booking_id]
        logger.info(
            "WebSocket client disconnected from booking channel: %s", booking_id
        )

    async def broadcast_to_booking(
        self,
        booking_id: uuid.UUID | str,
        event: str,
        data: Any,
    ) -> None:
        """
        Broadcasts an event message to all connected clients listening
        to a booking channel. Silently prunes stale or disconnected clients.
        """
        channel_key = str(booking_id)
        serialized_data: Any
        if isinstance(data, BaseModel):
            serialized_data = data.model_dump(mode="json")
        elif isinstance(data, dict):
            serialized_data = data
        else:
            serialized_data = str(data)

        payload = {
            "event": event,
            "booking_id": channel_key,
            "data": serialized_data,
            "timestamp": datetime.now(UTC).isoformat(),
        }
        message_text = json.dumps(payload, default=str)

        async with self._lock:
            sockets = list(self._active_connections.get(channel_key, []))

        stale_sockets: list[WebSocket] = []
        for socket in sockets:
            try:
                await socket.send_text(message_text)
            except Exception as e:
                logger.warning(
                    "WebSocket send failed on channel %s: %s",
                    channel_key,
                    e,
                )
                stale_sockets.append(socket)

        if stale_sockets:
            async with self._lock:
                for socket in stale_sockets:
                    if channel_key in self._active_connections:
                        self._active_connections[channel_key].discard(socket)


# Global WebSocket manager singleton
ws_manager = WebSocketManager()
