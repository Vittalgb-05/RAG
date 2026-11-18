"""RFC 9457 Problem Details for HTTP APIs error handling with redaction."""

from __future__ import annotations
import logging
import uuid
from typing import Any
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from core.redaction import redact_text
from retrieval.hybrid_retriever import VectorIndexError

logger = logging.getLogger(__name__)


class ApiError(Exception):
    """Domain API exception carrying HTTP status and problem code."""

    def __init__(self, status_code: int, code: str, detail: str, title: str | None = None) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.code = code
        self.detail = detail
        self.title = title or code.replace("_", " ").title()


def problem_payload(
    status: int,
    code: str,
    title: str,
    detail: str,
    request_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build an RFC 9457 problem detail dictionary with redacted message."""
    redacted_detail = redact_text(detail)
    payload: dict[str, Any] = {
        "type": f"https://rag.local/errors/{code}",
        "title": title,
        "status": status,
        "code": code,
        "detail": redacted_detail,
        "request_id": request_id or str(uuid.uuid4()),
    }
    if extra:
        payload.update(extra)
    return payload


def problem_response(
    status: int,
    code: str,
    title: str,
    detail: str,
    request_id: str | None = None,
    extra: dict[str, Any] | None = None,
) -> JSONResponse:
    """Return JSONResponse formatted as application/problem+json."""
    data = problem_payload(status, code, title, detail, request_id, extra)
    return JSONResponse(
        status_code=status,
        content=data,
        media_type="application/problem+json",
    )


def problem_from_exc(exc: Exception, request_id: str | None = None) -> dict[str, Any]:
    """Map any Python exception into an RFC 9457 problem dictionary."""
    if isinstance(exc, ApiError):
        return problem_payload(exc.status_code, exc.code, exc.title, exc.detail, request_id)

    if isinstance(exc, PermissionError):
        return problem_payload(
            403,
            "consent_required",
            "Cloud consent required",
            str(exc),
            request_id,
        )

    if isinstance(exc, TimeoutError):
        return problem_payload(
            503,
            "gpu_busy",
            "GPU busy",
            "Inference engine is currently busy; please try again shortly.",
            request_id,
        )

    if isinstance(exc, VectorIndexError):
        return problem_payload(
            503,
            "index_unavailable",
            "Vector index unavailable",
            str(exc),
            request_id,
        )

    if isinstance(exc, ValueError):
        msg = str(exc)
        code = "validation_failed"
        if "not a valid PDF" in msg or "not a PDF" in msg:
            code = "not_a_pdf"
        elif "exceeds maximum allowed size" in msg or "size" in msg.lower():
            code = "upload_too_large"
        elif "page limit" in msg.lower() or "too many pages" in msg.lower():
            code = "too_many_pages"
        return problem_payload(422, code, "Validation error", msg, request_id)

    if isinstance(exc, NotImplementedError):
        return problem_payload(
            422,
            "unsupported_operation",
            "Unsupported operation",
            str(exc),
            request_id,
        )

    if isinstance(exc, RuntimeError):
        return problem_payload(
            502,
            "provider_unreachable",
            "Provider unreachable",
            str(exc),
            request_id,
        )

    return problem_payload(
        500,
        "internal",
        "Internal server error",
        "An internal server error occurred.",
        request_id,
    )


def install_error_handlers(app: FastAPI) -> None:
    """Register global exception handlers for the FastAPI application."""

    @app.exception_handler(ApiError)
    async def api_error_handler(request: Request, exc: ApiError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return problem_response(exc.status_code, exc.code, exc.title, exc.detail, req_id)

    @app.exception_handler(PermissionError)
    async def permission_error_handler(request: Request, exc: PermissionError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return problem_response(403, "consent_required", "Cloud consent required", str(exc), req_id)

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(request: Request, exc: TimeoutError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return problem_response(503, "gpu_busy", "GPU busy", "Inference engine is currently busy.", req_id)

    @app.exception_handler(VectorIndexError)
    async def vector_error_handler(request: Request, exc: VectorIndexError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        return problem_response(503, "index_unavailable", "Vector index unavailable", str(exc), req_id)

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        payload = problem_from_exc(exc, req_id)
        return JSONResponse(status_code=payload["status"], content=payload, media_type="application/problem+json")

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        errors = exc.errors()
        detail = "; ".join(f"{'.'.join(str(loc) for loc in err['loc'])}: {err['msg']}" for err in errors)
        return problem_response(422, "validation_failed", "Validation error", detail, req_id)

    @app.exception_handler(Exception)
    async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
        req_id = getattr(request.state, "request_id", str(uuid.uuid4()))
        logger.exception("Unhandled server exception [request_id=%s]: %s", req_id, exc)
        payload = problem_from_exc(exc, req_id)
        return JSONResponse(status_code=payload["status"], content=payload, media_type="application/problem+json")
