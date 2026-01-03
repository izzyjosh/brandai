from fastapi import Request, status, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.encoders import jsonable_encoder
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.v1.utils.logger import get_logger
from pymongo.errors import (
    DuplicateKeyError,
    WriteError,
    BulkWriteError,
    OperationFailure,
    ConfigurationError,
    ExecutionTimeout,
)

logger = get_logger("exception_handler")


async def validation_exception_handler(request: Request, exc: RequestValidationError):
    errors = []
    for error in exc.errors():
        field = ".".join(str(loc) for loc in error["loc"] if loc != "body")
        errors.append(
            {
                "field": field if field else "body",
                "message": error["msg"],
                "type": error["type"],
            }
        )

    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "Validation error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "errors": errors,
        },
    )

    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_422_UNPROCESSABLE_ENTITY,
                "message": "Validation error",
                "errors": errors,
            }
        ),
    )


async def http_exception_handler(request: Request, exc: HTTPException):
    request_id = getattr(request.state, "request_id", None)
    logger.warning(
        "HTTP exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "detail": exc.detail,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {"success": False, "status_code": exc.status_code, "message": exc.detail}
        ),
    )


async def starlette_http_exception_handler(
    request: Request, exc: StarletteHTTPException
):
    if exc.detail:
        message = exc.detail
    else:
        if exc.status_code == 404:
            message = "Resource not found"
        elif exc.status_code == 405:
            message = "Method not allowed"
        elif exc.status_code == 403:
            message = "Forbidden"
        elif exc.status_code == 401:
            message = "Unauthorized"
        else:
            message = "An error occurred"

    request_id = getattr(request.state, "request_id", None)
    log_level = "warning" if exc.status_code < 500 else "error"
    getattr(logger, log_level)(
        "HTTP exception",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "status_code": exc.status_code,
            "response_message": message,
        },
    )

    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(
            {"success": False, "status_code": exc.status_code, "message": message}
        ),
    )


async def mongodb_duplicate_key_error_handler(request: Request, exc: DuplicateKeyError):
    """Handle MongoDB duplicate key errors (unique constraint violations)."""
    request_id = getattr(request.state, "request_id", None)

    # Extract field name from error details
    error_details = exc.details if hasattr(exc, "details") else {}
    index_name = error_details.get("index", "unknown")

    # Try to extract field name from index name or error message
    field_name = "field"
    if index_name and index_name != "unknown":
        # Index names often follow pattern: field_name_1 or field_name_-1
        field_name = index_name.split("_")[0] if "_" in index_name else index_name

    message = f"A record with this {field_name} already exists"

    logger.warning(
        "MongoDB duplicate key error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "index": index_name,
            "error_code": error_details.get("code"),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_409_CONFLICT,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_409_CONFLICT,
                "message": message,
            }
        ),
    )


async def mongodb_bulk_write_error_handler(request: Request, exc: BulkWriteError):
    """Handle MongoDB bulk write errors."""
    request_id = getattr(request.state, "request_id", None)

    # Check if it's a duplicate key error in bulk write
    write_errors = exc.details.get("writeErrors", [])
    duplicate_error = None

    for error in write_errors:
        if error.get("code") == 11000:  # Duplicate key error code
            duplicate_error = error
            break

    if duplicate_error:
        index_name = duplicate_error.get("indexPattern", {}).get("index", "unknown")
        field_name = "field"
        if index_name and index_name != "unknown":
            field_name = index_name.split("_")[0] if "_" in index_name else index_name

        message = f"A record with this {field_name} already exists"
        status_code = status.HTTP_409_CONFLICT
    else:
        message = "Database write operation failed"
        status_code = status.HTTP_400_BAD_REQUEST

    logger.warning(
        "MongoDB bulk write error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "write_errors_count": len(write_errors),
            "error_code": duplicate_error.get("code") if duplicate_error else None,
        },
    )

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status_code,
                "message": message,
            }
        ),
    )


async def mongodb_write_error_handler(request: Request, exc: WriteError):
    """Handle MongoDB write errors."""
    request_id = getattr(request.state, "request_id", None)

    error_code = exc.details.get("code", 0) if hasattr(exc, "details") else 0

    # Handle specific error codes
    if error_code == 11000:  # Duplicate key error
        error_details = exc.details if hasattr(exc, "details") else {}
        index_name = error_details.get("index", "unknown")
        field_name = "field"
        if index_name and index_name != "unknown":
            field_name = index_name.split("_")[0] if "_" in index_name else index_name
        message = f"A record with this {field_name} already exists"
        status_code = status.HTTP_409_CONFLICT
    else:
        message = "Database write operation failed"
        status_code = status.HTTP_400_BAD_REQUEST

    logger.warning(
        "MongoDB write error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_code": error_code,
        },
    )

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status_code,
                "message": message,
            }
        ),
    )


async def mongodb_connection_error_handler(
    request: Request,
    exc: Exception,
):
    """Handle MongoDB connection errors (ServerSelectionTimeoutError, ConnectionFailure, NetworkTimeout)."""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        "MongoDB connection error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_503_SERVICE_UNAVAILABLE,
                "message": "Database connection unavailable. Please try again later.",
            }
        ),
    )


async def mongodb_operation_failure_handler(request: Request, exc: OperationFailure):
    """Handle MongoDB operation failures."""
    request_id = getattr(request.state, "request_id", None)

    error_code = exc.code if hasattr(exc, "code") else None

    # Handle specific error codes
    if error_code == 11000:  # Duplicate key error
        message = "A record with this value already exists"
        status_code = status.HTTP_409_CONFLICT
    elif error_code == 50:  # MaxTimeMSExpired
        message = "Database operation timed out"
        status_code = status.HTTP_408_REQUEST_TIMEOUT
    else:
        message = "Database operation failed"
        status_code = status.HTTP_400_BAD_REQUEST

    logger.warning(
        "MongoDB operation failure",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_code": error_code,
            "error_message": str(exc),
        },
    )

    return JSONResponse(
        status_code=status_code,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status_code,
                "message": message,
            }
        ),
    )


async def mongodb_configuration_error_handler(
    request: Request, exc: ConfigurationError
):
    """Handle MongoDB configuration errors."""
    request_id = getattr(request.state, "request_id", None)

    logger.error(
        "MongoDB configuration error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_message": str(exc),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "Database configuration error",
            }
        ),
    )


async def mongodb_execution_timeout_handler(request: Request, exc: ExecutionTimeout):
    """Handle MongoDB execution timeout errors."""
    request_id = getattr(request.state, "request_id", None)

    logger.warning(
        "MongoDB execution timeout",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_message": str(exc),
        },
    )

    return JSONResponse(
        status_code=status.HTTP_408_REQUEST_TIMEOUT,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_408_REQUEST_TIMEOUT,
                "message": "Database operation timed out",
            }
        ),
    )


async def general_exception_handler(request: Request, exc: Exception):
    request_id = getattr(request.state, "request_id", None)
    logger.error(
        "Unexpected error",
        extra={
            "request_id": request_id,
            "path": request.url.path,
            "method": request.method,
            "error_type": type(exc).__name__,
            "error_message": str(exc),
        },
        exc_info=True,
    )

    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=jsonable_encoder(
            {
                "success": False,
                "status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
                "message": "An unexpected error occurred",
            }
        ),
    )
