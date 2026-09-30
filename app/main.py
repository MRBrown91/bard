"""FastAPI application entry point."""

from fastapi import FastAPI, Request, status
from fastapi.responses import JSONResponse

from app.api.http.routes import (
    campaigns,
    documents,
    entities,
    entity_recognition,
    facts,
    health,
    relationship_facts,
)
from app.api.http.routes.specialized_entities import routers as specialized_routers
from app.api.websocket import router as ws_router
from app.application.exceptions import (
    ApplicationError,
    ConflictError,
    ForbiddenError,
    NotFoundError,
    UnauthorizedError,
    ValidationError,
)
from app.schemas.common import ErrorResponse

app = FastAPI(title="Bard DM Assistant", version="0.1.0")

app.include_router(health.router)
app.include_router(campaigns.router)
app.include_router(entities.router)
app.include_router(documents.router)
app.include_router(facts.router)
app.include_router(relationship_facts.router)
app.include_router(entity_recognition.router)
for specialized_router in specialized_routers:
    app.include_router(specialized_router)
app.include_router(ws_router)

APPLICATION_ERROR_STATUS: tuple[tuple[type[ApplicationError], int], ...] = (
    (UnauthorizedError, status.HTTP_401_UNAUTHORIZED),
    (ForbiddenError, status.HTTP_403_FORBIDDEN),
    (NotFoundError, status.HTTP_404_NOT_FOUND),
    (ConflictError, status.HTTP_409_CONFLICT),
    (ValidationError, status.HTTP_422_UNPROCESSABLE_CONTENT),
)


def application_error_status(exc: ApplicationError) -> int:
    """Map an application error to its HTTP status code."""
    for error_type, status_code in APPLICATION_ERROR_STATUS:
        if isinstance(exc, error_type):
            return status_code
    return status.HTTP_500_INTERNAL_SERVER_ERROR


@app.exception_handler(ApplicationError)
async def handle_application_error(
    request: Request, exc: ApplicationError
) -> JSONResponse:
    """Translate application errors into structured HTTP responses."""
    status_code = application_error_status(exc)
    body = ErrorResponse(
        detail=exc.message,
        code=type(exc).__name__,
        extra=exc.details or None,
    )
    headers = (
        {"WWW-Authenticate": "Bearer"}
        if status_code == status.HTTP_401_UNAUTHORIZED
        else None
    )
    return JSONResponse(
        status_code=status_code, content=body.model_dump(mode="json"), headers=headers
    )
