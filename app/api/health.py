"""Health-check HTTP endpoints."""

from fastapi import APIRouter

router = APIRouter(prefix="/api", tags=["system"])


@router.get("/health")
async def health() -> dict[str, str]:
    """Return application health information."""
    return {"status": "ok"}
