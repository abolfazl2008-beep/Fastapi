from typing import Union
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import ValidationError as PydanticValidationError
from app.core.exceptions.base import AppBaseException
from app.core.logging import logger
from app.core.ip import get_real_ip
import uuid
import time


def generate_trace_id() -> str:
    return str(uuid.uuid4())


def get_or_create_trace_id(request: Request) -> str:
    if not hasattr(request.state, "trace_id"):
        request.state.trace_id = generate_trace_id()
    return request.state.trace_id


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppBaseException)
    async def app_base_exception_handler(request: Request, exc: AppBaseException):
        trace_id = get_or_create_trace_id(request)
        client_ip = get_real_ip(request)

        log_fn = logger.warning if 400 <= exc.status_code < 500 else logger.error
        log_fn(
            "App Exception",
            extra={
                "status_code": exc.status_code,
                "error_code": exc.error_code,
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "trace_id": trace_id,
                "extra": exc.extra,
            },
        )
        content = {
            "message": "Request could not be processed.",
            "error_code": exc.error_code,
            "trace_id": trace_id,
        }

        headers = {}
        if "retry_after" in exc.extra:
            headers["Retry-After"] = str(exc.extra["retry_after"])

        return JSONResponse(status_code=exc.status_code, content=content, headers=headers or None)


    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        trace_id = get_or_create_trace_id(request)
        client_ip = get_real_ip(request)

        log_fn = logger.warning if 400 <= exc.status_code < 500 else logger.error
        log_fn(
            "HTTP Exception",
            extra={
                "status_code": exc.status_code,
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "trace_id": trace_id,
                "detail": str(exc.detail),
            },
        )
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "message": "Request failed.",
                "error_code": f"HTTP_{exc.status_code}",
                "trace_id": trace_id,
            },
        )


    @app.exception_handler(RequestValidationError)
    @app.exception_handler(PydanticValidationError)
    async def validation_exception_handler(request: Request, exc: Union[RequestValidationError, PydanticValidationError]):
        trace_id = get_or_create_trace_id(request)
        client_ip = get_real_ip(request)

        errors = exc.errors() if hasattr(exc, "errors") else []

        details = [
            {
                "field": ".".join(map(str, err.get("loc", ["unknown"]))),
                "message": err.get("msg", "Invalid value"),
                "type": err.get("type"),
            }
            for err in errors
        ]
        logger.warning(
            "Validation Error",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "trace_id": trace_id,
                "errors_count": len(details),
            },
        )
        return JSONResponse(
            status_code=422,
            content={
                "message": "Validation error.",
                "error_code": "VALIDATION_ERROR",
                "trace_id": trace_id,
                "details": details,
            },
        )


    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        trace_id = get_or_create_trace_id(request)
        client_ip = get_real_ip(request)

        logger.exception(
            "Unhandled Exception",
            extra={
                "path": request.url.path,
                "method": request.method,
                "client_ip": client_ip,
                "trace_id": trace_id,
                "exception_type": type(exc).__name__,
            },
        )

        return JSONResponse(
            status_code=500,
            content={
                "message": "Internal server error",
                "error_code": "INTERNAL_SERVER_ERROR",
                "trace_id": trace_id,
            },
        )
