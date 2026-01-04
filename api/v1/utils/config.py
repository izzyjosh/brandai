import os


class Config:
    DATABASE_URL: str = os.environ.get("DATABASE_URL")
    DEBUG: str = os.environ.get("DEBUG")
    SERVER_PORT: str = os.environ.get("SERVER_PORT", 5001)

    # GitHub OAuth Configuration
    GITHUB_CLIENT_ID: str = os.environ.get("GITHUB_CLIENT_ID")
    GITHUB_CLIENT_SECRET: str = os.environ.get("GITHUB_CLIENT_SECRET")
    GITHUB_REDIRECT_URI: str = os.environ.get("GITHUB_REDIRECT_URI", "")
    GITHUB_DEVICE_CLIENT_ID: str = os.environ.get("GITHUB_DEVICE_CLIENT_ID")

    # JWT Configuration
    JWT_SECRET_KEY: str = os.environ.get("JWT_SECRET_KEY", "")
    JWT_ALGORITHM: str = os.environ.get("JWT_ALGORITHM")
    JWT_EXPIRATION_HOURS: int = int(os.environ.get("JWT_EXPIRATION_HOURS"))

    # Encryption Configuration
    ENCRYPTION_KEY: str = os.environ.get("ENCRYPTION_KEY")
