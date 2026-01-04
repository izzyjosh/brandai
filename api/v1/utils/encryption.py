import base64
from typing import Optional
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from api.v1.utils.config import Config
from api.v1.utils.logger import get_logger

logger = get_logger("encryption")

_fernet: Optional[Fernet] = None


def _get_fernet() -> Fernet:
    """Get or create Fernet instance for encryption/decryption."""
    global _fernet

    if _fernet is not None:
        return _fernet

    if not Config.ENCRYPTION_KEY:
        raise ValueError("ENCRYPTION_KEY is not set in environment variables")

    # Convert the encryption key to bytes if it's a string
    key_material = (
        Config.ENCRYPTION_KEY.encode()
        if isinstance(Config.ENCRYPTION_KEY, str)
        else Config.ENCRYPTION_KEY
    )

    # Use PBKDF2 to derive a 32-byte key
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b"brandai_github_token_salt",  # Fixed salt for consistency
        iterations=100000,
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_material))
    _fernet = Fernet(key)

    return _fernet


def encrypt_token(token: str) -> str:
    """
    Encrypt a GitHub access token before storing in database.

    :param token: The plaintext token to encrypt
    :return: Encrypted token as base64 string
    :raises: ValueError if encryption key is not configured
    """
    try:
        fernet = _get_fernet()
        encrypted_token = fernet.encrypt(token.encode())
        return base64.urlsafe_b64encode(encrypted_token).decode()
    except Exception as e:
        logger.error("Failed to encrypt token", extra={"error": str(e)})
        raise


def decrypt_token(encrypted_token: str) -> str:
    """
    Decrypt a GitHub access token from database.

    :param encrypted_token: The encrypted token from database
    :return: Decrypted plaintext token
    :raises: ValueError if decryption fails or encryption key is not configured
    """
    try:
        fernet = _get_fernet()
        encrypted_bytes = base64.urlsafe_b64decode(encrypted_token.encode())
        decrypted_token = fernet.decrypt(encrypted_bytes)
        return decrypted_token.decode()
    except Exception as e:
        logger.error("Failed to decrypt token", extra={"error": str(e)})
        raise
