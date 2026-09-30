"""
server/api/middleware.py
========================
Request ids, per-client token-bucket rate limiting for heavy endpoints,
and optional API-key protection of mutating requests.
"""

from __future__ import annotations

import time
import uuid

from fastapi import FastAPI, Request

from server.api.errors import error_response

__all__ = ["install_middleware"]

HEAVY = ("/api/v1/keys/distribute", "/api/v1/signatures/sign-and-verify", "/api/v1/attacks/run",
         "/api/v1/analytics/jobs", "/certify", "/reverify", "/api/v1/detection/baselines/calibrate")


class TokenBucket:
    def __init__(self, capacity: float, refill_per_s: float) -> None:
        self.capacity, self.refill = capacity, refill_per_s
        self.state: dict = {}

    def take(self, key: str) -> float:
        """Returns 0 if allowed, else seconds until a token is available."""
        now = time.monotonic()
        tokens, last = self.state.get(key, (self.capacity, now))
        tokens = min(self.capacity, tokens + (now - last) * self.refill)
        if tokens >= 1:
            self.state[key] = (tokens - 1, now)
            return 0.0
        self.state[key] = (tokens, now)
        return (1 - tokens) / self.refill


def install_middleware(app: FastAPI, api_key: str | None = None, heavy_capacity: float = 12,
                       heavy_refill: float = 1.0) -> None:
    heavy = TokenBucket(heavy_capacity, heavy_refill)

    @app.middleware("http")
    async def _mw(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex[:16]
        path = request.url.path
        if request.method in ("POST", "PUT", "PATCH", "DELETE") and path.startswith("/api/"):
            if api_key and request.headers.get("x-api-key") != api_key:
                return error_response(request, 401, "UNAUTHORIZED", "missing or invalid X-API-Key")
            if any(h in path for h in HEAVY):
                client = request.client.host if request.client else "local"
                wait = heavy.take(client)
                if wait > 0:
                    return error_response(request, 429, "RATE_LIMITED", "too many heavy requests; slow down",
                                          {"retry_after_s": round(wait, 2)}, headers={"Retry-After": str(int(wait) + 1)})
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        return response
