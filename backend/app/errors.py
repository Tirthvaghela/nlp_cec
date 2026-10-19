"""Consistent error responses: {"detail": str, "code": str, "errors"?: [...]}."""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

log = logging.getLogger(__name__)


class AppError(Exception):
    status_code = 400
    code = "bad_request"

    def __init__(self, detail: str, code: str | None = None, status_code: int | None = None):
        super().__init__(detail)
        self.detail = detail
        if code:
            self.code = code
        if status_code:
            self.status_code = status_code


class Unauthorized(AppError):
    status_code, code = 401, "unauthorized"


class Forbidden(AppError):
    status_code, code = 403, "forbidden"


class NotFound(AppError):
    status_code, code = 404, "not_found"


class Conflict(AppError):
    status_code, code = 409, "conflict"


class Unprocessable(AppError):
    status_code, code = 422, "unprocessable"


class TooManyRequests(AppError):
    status_code, code = 429, "rate_limited"

    def __init__(self, detail: str, retry_after: int):
        super().__init__(detail)
        self.retry_after = retry_after


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(_: Request, exc: AppError):
        headers = {"WWW-Authenticate": "Bearer"} if exc.status_code == 401 else None
        if isinstance(exc, TooManyRequests):
            headers = {"Retry-After": str(exc.retry_after)}
        return JSONResponse({"detail": exc.detail, "code": exc.code}, status_code=exc.status_code, headers=headers)

    @app.exception_handler(RequestValidationError)
    async def _validation(_: Request, exc: RequestValidationError):
        errors = []
        for e in exc.errors():
            loc = [str(p) for p in e.get("loc", []) if p not in ("body", "query", "path")]
            msg = e.get("msg", "Invalid value").removeprefix("Value error, ")
            errors.append({"field": ".".join(loc), "message": msg})
        first = errors[0] if errors else {"field": "", "message": "Invalid request"}
        detail = f"{first['field']}: {first['message']}" if first["field"] else first["message"]
        return JSONResponse({"detail": detail, "code": "validation_error", "errors": errors}, status_code=422)

    @app.exception_handler(StarletteHTTPException)
    async def _http(_: Request, exc: StarletteHTTPException):
        return JSONResponse({"detail": exc.detail, "code": "http_error"}, status_code=exc.status_code)

    @app.exception_handler(Exception)
    async def _unhandled(request: Request, exc: Exception):
        # Log type and path only - never request bodies (they may contain passwords or answers).
        log.exception("Unhandled error on %s %s: %s", request.method, request.url.path, type(exc).__name__)
        return JSONResponse({"detail": "An unexpected error occurred.", "code": "internal_error"}, status_code=500)
