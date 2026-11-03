"""FastAPI application. Phase 1: health endpoint and database wiring only."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.engine import Engine

from .api import router
from .db import init_db, make_engine, session_factory
from .services import MovementError
from .sharepoint import SharePointConfig, SharePointService


@asynccontextmanager
async def lifespan(app: FastAPI):
    engine = getattr(app.state, "engine", None) or make_engine()
    init_db(engine)
    app.state.engine = engine
    app.state.session_factory = session_factory(engine)
    yield


def create_app(engine: Engine | None = None, sharepoint: object | None = None) -> FastAPI:
    app = FastAPI(title="IMS", version="0.1.0", lifespan=lifespan)
    if engine is not None:
        app.state.engine = engine
    app.state.sharepoint = sharepoint  # None = SharePoint not configured
    app.include_router(router)

    @app.exception_handler(MovementError)
    async def _movement_error(_request: Request, exc: MovementError):
        return JSONResponse(status_code=422, content={"detail": str(exc)})

    @app.get("/api/health")
    def health(request: Request) -> dict[str, str]:
        with request.app.state.engine.connect() as conn:
            conn.exec_driver_sql("SELECT 1")
        return {"status": "ok"}

    # The packaged app serves the built UI from the same address as the API.
    # Mounted last so /api routes always take precedence.
    web_dir = os.environ.get("IMS_WEB_DIR")
    if web_dir and Path(web_dir).is_dir():
        app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")

    return app


def _load_sharepoint():
    return SharePointService(SharePointConfig.load())


app = create_app(sharepoint=_load_sharepoint())
