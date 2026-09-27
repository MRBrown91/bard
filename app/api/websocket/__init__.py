"""WebSocket router exports."""

from fastapi import APIRouter

from app.api.websocket.routes import stream

router = APIRouter()
router.include_router(stream.router)

__all__ = ["router"]