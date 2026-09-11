import uuid
from typing import Any

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect, status
from sqlalchemy import select

from app.core.db import AsyncSessionLocal
from app.core.logging import get_logger
from app.core.security import decode_token
from app.core.websocket import ws_manager
from app.models.booking import Booking
from app.models.enums import UserRole, UserStatus
from app.models.provider import Provider
from app.models.user import User

logger = get_logger("roadresq.ws")
router = APIRouter(tags=["Realtime WebSockets"])


@router.websocket("/ws/bookings/{booking_id}")
async def booking_realtime_websocket(
    websocket: WebSocket,
    booking_id: uuid.UUID,
    token: str = Query(..., description="JWT Bearer access token for authentication"),
) -> None:
    """
    Authenticated WebSocket endpoint for receiving live booking updates,
    provider GPS coordinates, estimate revisions, and job lifecycle events.
    """
    # 1. Authenticate JWT token
    payload = decode_token(token)
    if not payload:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    user_id_str = payload.get("sub")
    if not user_id_str:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    try:
        user_uuid = uuid.UUID(user_id_str)
    except ValueError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return

    # 2. Authorize channel access against database
    async with AsyncSessionLocal() as session:
        # Verify user status
        user_stmt = select(User).where(
            User.id == user_uuid, User.status == UserStatus.ACTIVE.value
        )
        user_res = await session.execute(user_stmt)
        user = user_res.scalar_one_or_none()
        if not user:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        # Verify booking ownership or assignment
        booking_stmt = select(Booking).where(Booking.id == booking_id)
        booking_res = await session.execute(booking_stmt)
        booking = booking_res.scalar_one_or_none()
        if not booking:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        is_authorized = False
        if user.role in (UserRole.ADMIN.value, UserRole.SUPPORT.value):
            is_authorized = True
        elif user.role == UserRole.CUSTOMER.value and booking.customer_id == user.id:
            is_authorized = True
        elif user.role == UserRole.PROVIDER.value:
            prov_stmt = select(Provider).where(Provider.user_id == user.id)
            prov_res = await session.execute(prov_stmt)
            provider = prov_res.scalar_one_or_none()
            if provider and booking.provider_id == provider.id:
                is_authorized = True

        if not is_authorized:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

    # 3. Register connection with channel manager
    channel_key = str(booking_id)
    await ws_manager.connect(channel_key, websocket)

    try:
        while True:
            # Keep-alive loop and listen for client pings
            data: Any = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text('{"event": "pong"}')
    except WebSocketDisconnect:
        await ws_manager.disconnect(channel_key, websocket)
    except Exception as e:
        logger.warning("WebSocket error on booking channel %s: %s", channel_key, e)
        await ws_manager.disconnect(channel_key, websocket)
