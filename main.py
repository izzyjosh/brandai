from contextlib import asynccontextmanager
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.exceptions import RequestValidationError
import uvicorn

from api.v1.responses.success_response import success_response
from api.v1.utils.logger import setup_logger
from api.v1.middlewares.logging_middleware import LoggingMiddleware

from api.v1.routes import version_one
from starlette.exceptions import HTTPException as StarletteHTTPException
from api.v1.utils.database import connect_to_mongodb, close_mongodb_connection
from api.v1.middlewares.exception_handler import (
    validation_exception_handler,
    starlette_http_exception_handler,
    general_exception_handler,
    mongodb_duplicate_key_error_handler,
    mongodb_bulk_write_error_handler,
    mongodb_write_error_handler,
    mongodb_connection_error_handler,
    mongodb_operation_failure_handler,
    mongodb_configuration_error_handler,
    mongodb_execution_timeout_handler,
)
from pymongo.errors import (
    DuplicateKeyError,
    WriteError,
    BulkWriteError,
    OperationFailure,
    ServerSelectionTimeoutError,
    ConnectionFailure,
    ConfigurationError,
    ExecutionTimeout,
    NetworkTimeout,
)
from api.v1.utils.config import Config

load_dotenv()

setup_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    yield
    await close_mongodb_connection()


app: FastAPI = FastAPI(
    debug=Config.DEBUG != "False",
    docs_url="/docs",
    redoc_url=None,
    title="BrandAI",
    lifespan=lifespan,
)

app.add_middleware(LoggingMiddleware)

# Exception middleware

app.add_exception_handler(RequestValidationError, validation_exception_handler)
app.add_exception_handler(StarletteHTTPException, starlette_http_exception_handler)
app.add_exception_handler(DuplicateKeyError, mongodb_duplicate_key_error_handler)
app.add_exception_handler(BulkWriteError, mongodb_bulk_write_error_handler)
app.add_exception_handler(WriteError, mongodb_write_error_handler)
app.add_exception_handler(ServerSelectionTimeoutError, mongodb_connection_error_handler)
app.add_exception_handler(ConnectionFailure, mongodb_connection_error_handler)
app.add_exception_handler(NetworkTimeout, mongodb_connection_error_handler)
app.add_exception_handler(OperationFailure, mongodb_operation_failure_handler)
app.add_exception_handler(ConfigurationError, mongodb_configuration_error_handler)
app.add_exception_handler(ExecutionTimeout, mongodb_execution_timeout_handler)

app.add_exception_handler(Exception, general_exception_handler)

# cors middleware

origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(version_one)


@app.get("/")
async def index():
    return success_response(message="Welcome to BrandAI")


# start server

if __name__ == "__main__":
    uvicorn.run(app, port=int(Config.SERVER_PORT), reload=False)
