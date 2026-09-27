"""HTTP router exports."""

from fastapi import APIRouter

from app.api.http.routes import health, campaigns

router = APIRouter()
router.include_router(health.router)
router.include_router(campaigns.router)

__all__ = ["router"]