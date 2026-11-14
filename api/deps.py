"""FastAPI dependency injection utilities."""

from __future__ import annotations
from fastapi import Request

from api.container import AppContainer
from api.errors import ApiError


def get_container(request: Request) -> AppContainer:
    """Retrieve the application container from application state."""
    return request.app.state.container


def require_client_header(request: Request) -> None:
    """Enforce X-RAG-Client: web on all mutating requests (POST, PUT, PATCH, DELETE)."""
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        header_val = request.headers.get("x-rag-client")
        if header_val != "web":
            raise ApiError(
                status_code=403,
                code="missing_client_header",
                title="Missing client header",
                detail="Header 'X-RAG-Client: web' is required for mutating requests.",
            )
