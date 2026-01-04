import asyncio
import secrets
from datetime import datetime, timedelta
from typing import Optional, Tuple
import httpx
import jwt
from fastapi import HTTPException, status
from api.v1.models.user import User
from api.v1.utils.config import Config
from api.v1.utils.encryption import encrypt_token
from api.v1.utils.logger import get_logger

logger = get_logger("auth_service")

# GitHub OAuth endpoints
GITHUB_AUTHORIZE_URL = "https://github.com/login/oauth/authorize"
GITHUB_TOKEN_URL = "https://github.com/login/oauth/access_token"
GITHUB_USER_URL = "https://api.github.com/user"
GITHUB_DEVICE_CODE_URL = "https://github.com/login/device/code"
GITHUB_DEVICE_TOKEN_URL = "https://github.com/login/oauth/access_token"

# OAuth scopes
GITHUB_SCOPES = ["repo", "read:org", "read:user"]


class AuthService:
    """Service class for authentication operations."""

    @staticmethod
    def generate_state() -> str:
        """Generate a random state for CSRF protection."""
        return secrets.token_urlsafe(32)

    @staticmethod
    def initiate_github_oauth(state: Optional[str] = None) -> Tuple[str, str]:
        """
        Generate GitHub OAuth authorization URL.

        :param state: Optional state parameter for CSRF protection
        :return: Tuple of (auth_url, state)
        """
        if not Config.GITHUB_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth is not configured",
            )

        state_param = state or AuthService.generate_state()
        scopes = " ".join(GITHUB_SCOPES)

        params = {
            "client_id": Config.GITHUB_CLIENT_ID,
            "redirect_uri": Config.GITHUB_REDIRECT_URI,
            "scope": scopes,
            "state": state_param,
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        auth_url = f"{GITHUB_AUTHORIZE_URL}?{query_string}"

        return auth_url, state_param

    @staticmethod
    async def handle_github_callback(code: str, state: Optional[str] = None) -> dict:
        """
        Handle GitHub OAuth callback and exchange code for token.

        :param code: Authorization code from GitHub
        :param state: State parameter for CSRF protection
        :return: Dictionary with JWT token and user info
        """
        if not Config.GITHUB_CLIENT_ID or not Config.GITHUB_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub OAuth is not configured",
            )

        # Exchange code for access token
        async with httpx.AsyncClient() as client:
            try:
                token_response = await client.post(
                    GITHUB_TOKEN_URL,
                    data={
                        "client_id": Config.GITHUB_CLIENT_ID,
                        "client_secret": Config.GITHUB_CLIENT_SECRET,
                        "code": code,
                    },
                    headers={"Accept": "application/json"},
                    timeout=10.0,
                )
                token_response.raise_for_status()
                token_data = token_response.json()

                if "error" in token_data:
                    logger.error(
                        "GitHub token exchange error",
                        extra={"error": token_data.get("error")},
                    )
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail=f"Failed to exchange code for token: {token_data.get('error')}",
                    )

                access_token = token_data.get("access_token")
                if not access_token:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="No access token received from GitHub",
                    )

                # Fetch user information from GitHub
                user_response = await client.get(
                    GITHUB_USER_URL,
                    headers={
                        "Authorization": f"token {access_token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=10.0,
                )
                user_response.raise_for_status()
                github_user = user_response.json()

            except httpx.HTTPError as e:
                logger.error("GitHub API error", extra={"error": str(e)})
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to communicate with GitHub API",
                )

        # Create or update user in database
        github_id = github_user["id"]
        username = github_user["login"]
        email = github_user.get("email")

        # Encrypt token before storing
        encrypted_token = encrypt_token(access_token)

        # Check if user exists
        user = await User.find_by_github_id(github_id)

        if user:
            # Update existing user
            user.username = username
            user.email = email
            user.github_access_token = encrypted_token
            user = await user.save()
        else:
            # Create new user
            user = User(
                github_id=github_id,
                username=username,
                email=email,
                github_access_token=encrypted_token,
            )
            user = await user.save()

        # Generate JWT token
        jwt_token = AuthService.generate_jwt_token(str(user._id))

        logger.info(
            "User authenticated via GitHub",
            extra={"github_id": github_id, "username": username},
        )

        return {
            "access_token": jwt_token,
            "token_type": "Bearer",
            "expires_in": Config.JWT_EXPIRATION_HOURS * 3600,
            "user": {
                "id": str(user._id),
                "github_id": user.github_id,
                "username": user.username,
                "email": user.email,
            },
        }

    @staticmethod
    async def initiate_device_flow() -> dict:
        """
        Initiate GitHub device flow.

        :return: Device flow information
        """
        if not Config.GITHUB_DEVICE_CLIENT_ID:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub device flow is not configured",
            )

        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(
                    GITHUB_DEVICE_CODE_URL,
                    data={
                        "client_id": Config.GITHUB_DEVICE_CLIENT_ID,
                        "scope": " ".join(GITHUB_SCOPES),
                    },
                    headers={"Accept": "application/json"},
                    timeout=10.0,
                )
                response.raise_for_status()
                device_data = response.json()

                return {
                    "device_code": device_data["device_code"],
                    "user_code": device_data["user_code"],
                    "verification_uri": device_data["verification_uri"],
                    "verification_uri_complete": device_data[
                        "verification_uri_complete"
                    ],
                    "expires_in": device_data["expires_in"],
                    "interval": device_data.get("interval", 5),
                    "message": f"Visit {device_data['verification_uri']} and enter code {device_data['user_code']}",
                }
            except httpx.HTTPError as e:
                logger.error(
                    "GitHub device flow initiation error", extra={"error": str(e)}
                )
                raise HTTPException(
                    status_code=status.HTTP_502_BAD_GATEWAY,
                    detail="Failed to initiate device flow",
                )

    @staticmethod
    async def verify_device_code(device_code: str, user_code: str) -> dict:
        """
        Verify device code and exchange for access token.

        :param device_code: Device code from initiation
        :param user_code: User code to verify
        :return: Dictionary with JWT token and user info
        """
        if not Config.GITHUB_DEVICE_CLIENT_ID or not Config.GITHUB_CLIENT_SECRET:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="GitHub device flow is not configured",
            )

        async with httpx.AsyncClient() as client:
            max_attempts = 20
            interval = 5

            for attempt in range(max_attempts):
                try:
                    response = await client.post(
                        GITHUB_DEVICE_TOKEN_URL,
                        data={
                            "client_id": Config.GITHUB_DEVICE_CLIENT_ID,
                            "client_secret": Config.GITHUB_CLIENT_SECRET,
                            "device_code": device_code,
                            "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        },
                        headers={"Accept": "application/json"},
                        timeout=10.0,
                    )
                    response.raise_for_status()
                    token_data = response.json()

                    if "error" in token_data:
                        error = token_data["error"]
                        if error == "authorization_pending":
                            # Wait and retry
                            await asyncio.sleep(interval)
                            continue
                        elif error == "slow_down":
                            interval += 5
                            await asyncio.sleep(interval)
                            continue
                        elif error == "expired_token":
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail="Device code has expired",
                            )
                        else:
                            raise HTTPException(
                                status_code=status.HTTP_400_BAD_REQUEST,
                                detail=f"Device verification failed: {error}",
                            )

                    access_token = token_data.get("access_token")
                    if not access_token:
                        raise HTTPException(
                            status_code=status.HTTP_400_BAD_REQUEST,
                            detail="No access token received from GitHub",
                        )

                    # Fetch user information
                    user_response = await client.get(
                        GITHUB_USER_URL,
                        headers={
                            "Authorization": f"token {access_token}",
                            "Accept": "application/vnd.github.v3+json",
                        },
                        timeout=10.0,
                    )
                    user_response.raise_for_status()
                    github_user = user_response.json()

                    # Create or update user
                    github_id = github_user["id"]
                    username = github_user["login"]
                    email = github_user.get("email")
                    encrypted_token = encrypt_token(access_token)

                    user = await User.find_by_github_id(github_id)
                    if user:
                        user.username = username
                        user.email = email
                        user.github_access_token = encrypted_token
                        user = await user.save()
                    else:
                        user = User(
                            github_id=github_id,
                            username=username,
                            email=email,
                            github_access_token=encrypted_token,
                        )
                        user = await user.save()

                    jwt_token = AuthService.generate_jwt_token(str(user._id))

                    logger.info(
                        "User authenticated via device flow",
                        extra={"github_id": github_id, "username": username},
                    )

                    return {
                        "access_token": jwt_token,
                        "token_type": "Bearer",
                        "expires_in": Config.JWT_EXPIRATION_HOURS * 3600,
                        "user": {
                            "id": str(user._id),
                            "github_id": user.github_id,
                            "username": user.username,
                            "email": user.email,
                        },
                    }

                except httpx.HTTPError as e:
                    logger.error(
                        "GitHub device verification error", extra={"error": str(e)}
                    )
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail="Failed to verify device code",
                    )

        raise HTTPException(
            status_code=status.HTTP_408_REQUEST_TIMEOUT,
            detail="Device verification timed out",
        )

    @staticmethod
    def generate_jwt_token(user_id: str) -> str:
        """
        Generate JWT token for API authentication.

        :param user_id: User ID from database
        :return: JWT token string
        """
        if not Config.JWT_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT secret key is not configured",
            )

        expiration = datetime.utcnow() + timedelta(hours=Config.JWT_EXPIRATION_HOURS)

        payload = {
            "sub": user_id,
            "exp": expiration,
            "iat": datetime.utcnow(),
        }

        token = jwt.encode(
            payload, Config.JWT_SECRET_KEY, algorithm=Config.JWT_ALGORITHM
        )
        return token

    @staticmethod
    def verify_jwt_token(token: str) -> dict:
        """
        Verify and decode JWT token.

        :param token: JWT token string
        :return: Decoded token payload
        :raises: HTTPException if token is invalid
        """
        if not Config.JWT_SECRET_KEY:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="JWT secret key is not configured",
            )

        try:
            payload = jwt.decode(
                token, Config.JWT_SECRET_KEY, algorithms=[Config.JWT_ALGORITHM]
            )
            return payload
        except jwt.ExpiredSignatureError:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED, detail="Token has expired"
            )
        except jwt.InvalidTokenError as e:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail=f"Invalid token: {str(e)}",
            )
