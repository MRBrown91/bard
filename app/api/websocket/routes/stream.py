"""WebSocket protocol for live transcript processing."""

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query

from app.integrations.auth import get_auth_provider, AuthenticationError

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/stream")
async def stream(
    websocket: WebSocket,
    token: str = Query(...),
) -> None:
    """Accept transcript messages and acknowledge them during Phase 1."""
    # Validate token
    provider = get_auth_provider()
    try:
        identity = await provider.validate_token(token)
    except AuthenticationError:
        await websocket.close(code=4001, reason="Invalid authentication")
        return

    await websocket.accept()
    try:
        while True:
            message: Any = await websocket.receive_json()
            transcript = message.get("transcript", "")
            await websocket.send_json(
                {
                    "type": "transcript_ack",
                    "transcript": transcript,
                    "matches": [],
                }
            )
    except WebSocketDisconnect:
        return