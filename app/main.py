"""FastAPI application entry point."""

from fastapi import FastAPI

from app.api.http.routes import health, campaigns
from app.api.websocket import router as ws_router

app = FastAPI(title="Bard DM Assistant", version="0.1.0")
app.include_router(health.router)
app.include_router(campaigns.router)
app.include_router(ws_router)