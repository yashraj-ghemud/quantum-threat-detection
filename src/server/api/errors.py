"""
server/api/errors.py
====================
Uniform error responses::

    {"error": {"code": "...", "message": "...", "status": 409, "detail": {...}, "request_id": "..."}}
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from sentinel.adversary.catalog import AttackSpecError
from sentinel.channels import ChannelSpecError
from sentinel.protocol.encoding import MessageTooLong
from sentinel.protocol.params import ParamsError
from server.services.engine import ApiConflict, ApiNotFound
from server.services.jobs import JobConflict

__all__ = ["install_error_handlers", "error_response"]

log = logging.getLogger("qveris.api")

_STATUS = {"MESSAGE_TOO_LONG": 413, "VALIDATION_ERROR": 422, "NOT_FOUND": 404, "FEATURE_DISABLED": 403,
           "UNAUTHORIZED": 401, "RATE_LIMITED": 429}


def error_response(request: Request, status: int, code: str, message: str, detail: dict | None = None,
                   headers: dict | None = None) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse(status_code=status, headers=headers,
                        content={"error": {"code": code, "message": message, "status": status,
                                           "detail": detail or {}, "request_id": rid}})


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiConflict)
    async def _conflict(request: Request, exc: ApiConflict):
        return error_response(request, _STATUS.get(exc.code, 409), exc.code, exc.message, exc.detail)

    @app.exception_handler(ApiNotFound)
    async def _nf(request: Request, exc: ApiNotFound):
        return error_response(request, 404, "NOT_FOUND", f"not found: {exc}")

    @app.exception_handler(JobConflict)
    async def _job(request: Request, exc: JobConflict):
        return error_response(request, 409, "JOB_CONFLICT", "a job of this kind is already running", {"job_id": str(exc)})

    for cls in (ChannelSpecError, AttackSpecError, ParamsError):
        @app.exception_handler(cls)
        async def _val(request: Request, exc: Exception):
            return error_response(request, 422, "VALIDATION_ERROR", str(exc))

    @app.exception_handler(MessageTooLong)
    async def _long(request: Request, exc: MessageTooLong):
        return error_response(request, 413, "MESSAGE_TOO_LONG", str(exc))

    @app.exception_handler(PermissionError)
    async def _perm(request: Request, exc: PermissionError):
        return error_response(request, 403, "FEATURE_DISABLED", str(exc))

    @app.exception_handler(RequestValidationError)
    async def _rv(request: Request, exc: RequestValidationError):
        errs = [{"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")} for e in exc.errors()]
        return error_response(request, 422, "VALIDATION_ERROR", "request validation failed", {"errors": errs})

    @app.exception_handler(StarletteHTTPException)
    async def _http(request: Request, exc: StarletteHTTPException):
        code = {404: "NOT_FOUND", 405: "METHOD_NOT_ALLOWED", 401: "UNAUTHORIZED", 403: "FORBIDDEN"}.get(exc.status_code, "HTTP_ERROR")
        return error_response(request, exc.status_code, code, str(exc.detail))

    @app.exception_handler(Exception)
    async def _any(request: Request, exc: Exception):
        log.exception("unhandled error on %s %s", request.method, request.url.path)
        return error_response(request, 500, "INTERNAL", "internal error — see server log with this request id")
