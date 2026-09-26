"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.health import router as health_router
from app.realtime.stream import router as realtime_router

app = FastAPI(title="Bard DM Assistant", version="0.1.0")
app.include_router(health_router)
app.include_router(realtime_router)
