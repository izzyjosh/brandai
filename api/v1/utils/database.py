from typing import Optional
from urllib.parse import urlparse, parse_qs
from pymongo import AsyncMongoClient
from pymongo.asynchronous.database import AsyncDatabase
from pymongo.asynchronous.collection import AsyncCollection
from pymongo.errors import (
    ServerSelectionTimeoutError,
    ConnectionFailure,
    ConfigurationError,
)
from api.v1.utils.config import Config
from api.v1.utils.logger import get_logger

logger = get_logger("database")

# Global client instance
_client: Optional[AsyncMongoClient] = None
_database: Optional[AsyncDatabase] = None


def get_client() -> Optional[AsyncMongoClient]:
    return _client


def get_database() -> Optional[AsyncDatabase]:
    return _database


async def connect_to_mongodb() -> None:
    """
    Connect to MongoDB using PyMongo's AsyncMongoClient.
    """
    global _client, _database

    if _client is not None:
        logger.warning("MongoDB client already connected")
        return

    if not Config.DATABASE_URL:
        raise ConfigurationError("DATABASE_URL is not set in environment variables")

    try:
        _client = AsyncMongoClient(
            Config.DATABASE_URL,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=10000,
            socketTimeoutMS=20000,
        )

        await _client.server_info()

        parsed_url = urlparse(Config.DATABASE_URL)
        database_name = (
            parsed_url.path.lstrip("/").split("?")[0] if parsed_url.path else None
        )

        if not database_name:
            query_params = parse_qs(parsed_url.query)
            if "database" in query_params:
                database_name = query_params["database"][0]
            else:
                raise ConfigurationError(
                    "Database name not found in DATABASE_URL. "
                    "Please include database name in connection string (e.g., mongodb://host:port/database_name)."
                )

        _database = _client[database_name]

        # Extract host and port from the parsed URL
        host = parsed_url.hostname or "unknown"
        port = parsed_url.port or "unknown"

        logger.info(
            "Successfully connected to MongoDB",
            extra={
                "database": database_name,
                "host": host,
                "port": port,
            },
        )

    except (ServerSelectionTimeoutError, ConnectionFailure) as e:
        logger.error(
            "Failed to connect to MongoDB",
            extra={"error": str(e), "database_url": Config.DATABASE_URL},
        )
        _client = None
        _database = None
        raise
    except Exception as e:
        logger.error(
            "Unexpected error while connecting to MongoDB",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
        _client = None
        _database = None
        raise


async def close_mongodb_connection() -> None:
    global _client, _database

    if _client is None:
        logger.warning("MongoDB client is not connected")
        return

    try:
        await _client.close()
        logger.info("MongoDB connection closed")
    except Exception as e:
        logger.error(
            "Error while closing MongoDB connection",
            extra={"error": str(e), "error_type": type(e).__name__},
            exc_info=True,
        )
    finally:
        _client = None
        _database = None


def get_collection(collection_name: str) -> AsyncCollection:
    """
    Get a MongoDB collection.

    :param collection_name: Name of the collection
    :return: MongoDB AsyncCollection object
    :raises: RuntimeError if database is not connected
    """
    if _database is None:
        raise RuntimeError(
            "Database is not connected. Call connect_to_mongodb() first."
        )

    return _database[collection_name]


async def ping_database() -> bool:
    """
    Ping the database to check if connection is alive.

    :return: True if connection is alive, False otherwise
    """
    if _client is None:
        return False

    try:
        # server_info is async in AsyncMongoClient
        await _client.server_info()
        return True
    except Exception as e:
        logger.warning(
            "Database ping failed",
            extra={"error": str(e), "error_type": type(e).__name__},
        )
        return False
