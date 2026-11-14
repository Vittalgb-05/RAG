"""FastAPI application initialization, middlewares, routing, and lifecycle."""

from __future__ import annotations
from contextlib import asynccontextmanager
import logging
from pathlib import Path
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.staticfiles import StaticFiles

from api.config import Settings
from api.container import AppContainer
from api.deps import require_client_header
from api.errors import install_error_handlers
from api.routers import (
    chat,
    documents,
    jobs,
    search,
    settings as settings_r,
    summaries,
    system,
    visualize,
)

logger = logging.getLogger(__name__)


def configure_logging(log_dir: Path, level: str = "INFO") -> None:
    """Ensure logging directory exists and configure file handler."""
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / "rag.log"
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_file, encoding="utf-8"),
        ],
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage application startup, singletons, and background hydration."""
    s = Settings()
    configure_logging(log_dir=s.log_dir, level=s.log_level)
    app.state.container = AppContainer.build(s)
    app.state.container.start_background_hydration()
    yield
    app.state.container.shutdown()


def create_app() -> FastAPI:
    """Build and configure the FastAPI application instance."""
    s = Settings()
    app = FastAPI(title="RAG Assistant API", version="2.0.0", lifespan=lifespan)

    # DNS-rebinding guard
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=s.allowed_hosts)

    # CORS middleware
    app.add_middleware(
        CORSMiddleware,
        allow_origins=s.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["content-type", "x-rag-client", "last-event-id"],
    )

    install_error_handlers(app)

    for r in (system, settings_r, documents, jobs, chat, summaries, search, visualize):
        app.include_router(
            r.router,
            prefix="/api/v1",
            dependencies=[Depends(require_client_header)],
        )

    if s.serve_frontend and Path("frontend/out").exists():
        app.mount("/", StaticFiles(directory="frontend/out", html=True), name="web")

    return app


app = create_app()


def run() -> None:
    """Console script entry point for rag-api command."""
    import uvicorn

    s = Settings()
    uvicorn.run("api.main:app", host=s.api_host, port=s.api_port, reload=False)
