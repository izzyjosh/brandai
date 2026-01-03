import os


class Config:
    DATABASE_URL: str = os.environ.get("DATABASE_URL")
    DEBUG: str = os.environ.get("DEBUG")
    SERVER_PORT: str = os.environ.get("SERVER_PORT", 5001)
