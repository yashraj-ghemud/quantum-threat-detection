"""
server/app.py
=============
Application factory (backend plan section 10).

``create_app(settings)`` wires the :class:`AppContext`, background workers,
middleware, error handlers, the REST router, the ``/ws`` stream and — when
``web/dist`` has been built — the single-page frontend.
"""

from __future__ import annotations

import asyncio
import logging
import threading
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from sentinel import __version__ as ENGINE_VERSION
from server.api.errors import error_response, install_error_handlers
from server.api.middleware import install_middleware
from server.api.routes.v1 import router as v1_router
from server.api.ws import router as ws_router
from server.context import AppContext
from server.db.database import dumps
from server.services.workers import Workers
from server.settings import Settings

__all__ = ["create_app", "StrictJSONResponse"]

log = logging.getLogger("qveris")


class StrictJSONResponse(JSONResponse):
    """JSON that browsers can always parse: numpy → Python, NaN/inf → null."""

    def render(self, content: Any) -> bytes:
        return dumps(content).encode("utf-8")


def _boot(ctx: AppContext) -> None:
    """Startup work that must not block serving: baselines, then the self-test."""
    try:
        if not ctx.settings.skip_calibration:
            stale = ctx.engine.stale_links()
            if stale:
                log.info("calibrating %d link baseline(s): %s", len(stale), ", ".join(stale))
                ctx.engine.calibrate(stale)
        ctx.selftest.run()
        failed = [c["id"] for c in ctx.selftest.checks if c["status"] == "fail"]
        if failed:
            log.warning("self-test failures: %s", ", ".join(failed))
            ctx.hub.publish("system", "system.notice", {"level": "warning", "message": f"self-test failed: {', '.join(failed)}"})
        else:
            log.info("self-test passed (%d checks)", len(ctx.selftest.checks))
    except Exception:  # pragma: no cover - surfaced in the log and the selftest endpoint
        log.exception("boot sequence failed")


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    settings = settings or Settings.from_env()
    logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO),
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        ctx: AppContext = app.state.ctx
        ctx.hub.bind(asyncio.get_running_loop())
        workers = None
        if settings.background:
            threading.Thread(target=_boot, args=(ctx,), daemon=True, name="qveris-boot").start()
            workers = Workers(ctx)
            workers.start()
            if settings.autostart_traffic:
                ctx.traffic.paused_idle = False
        app.state.workers = workers
        log.info("QVeris %s ready — preset=%s, data=%s", ENGINE_VERSION, ctx.engine.preset, settings.data_dir)
        try:
            yield
        finally:
            if workers is not None:
                await workers.shutdown()
            ctx.close()

    app = FastAPI(
        title="QVeris API",
        version=ENGINE_VERSION,
        description="Teleportation-based quantum digital signatures with QSentinel threat detection.",
        default_response_class=StrictJSONResponse,
        lifespan=lifespan,
    )
    app.state.settings = settings
    app.state.ctx = AppContext(settings)

    app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=False,
                       allow_methods=["*"], allow_headers=["*"], expose_headers=["X-Request-ID", "Retry-After"])
    install_middleware(app, api_key=settings.api_key, heavy_capacity=settings.heavy_rate_capacity,
                       heavy_refill=settings.heavy_rate_refill)
    install_error_handlers(app)
    app.include_router(v1_router)
    app.include_router(ws_router)
    _mount_frontend(app, Path(settings.web_dist))
    return app


def _mount_frontend(app: FastAPI, dist: Path) -> None:
    index = dist / "index.html"
    if not index.is_file():
        @app.get("/", include_in_schema=False)
        def _root():
            return {"name": "QVeris API", "version": ENGINE_VERSION, "docs": "/docs", "openapi": "/openapi.json",
                    "hint": "build the web app (cd web && npm ci && npm run build) to serve the UI here"}
        return

    if (dist / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")
    root = dist.resolve()

    @app.get("/{path:path}", include_in_schema=False)
    def _spa(path: str, request: Request):
        if path.startswith(("api/", "ws")) or path in ("docs", "redoc", "openapi.json"):
            return error_response(request, 404, "NOT_FOUND", f"not found: /{path}")
        if path:
            candidate = (dist / path).resolve()
            if candidate.is_file() and root in candidate.parents:
                return FileResponse(candidate)
        return FileResponse(index, headers={"Cache-Control": "no-cache"})
