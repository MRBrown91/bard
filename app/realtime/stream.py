"""WebSocket protocol skeleton for live transcript processing."""

from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["realtime"])


@router.websocket("/ws/stream")
async def stream(websocket: WebSocket) -> None:
    """Accept transcript messages and acknowledge them during Phase 1."""
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
