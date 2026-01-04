from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from api.v1.services.auth import AuthService
from api.v1.models.user import User
from api.v1.utils.logger import get_logger

logger = get_logger("dependencies")

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> User:
    """
    Dependency to get the current authenticated user from JWT token.

    :param credentials: HTTP Bearer token credentials
    :return: Authenticated User instance
    :raises: HTTPException if token is invalid or user not found
    """
    token = credentials.credentials

    try:
        # Verify token
        payload = AuthService.verify_jwt_token(token)
        user_id = payload.get("sub")

        if not user_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid token payload",
            )

        # Fetch user from database
        user = await User.find_by_id(user_id)
        if not user:
            logger.warning("User not found", extra={"user_id": user_id})
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="User not found",
            )

        logger.debug("User authenticated", extra={"user_id": user_id})
        return user

    except HTTPException:
        raise
    except Exception as e:
        logger.error("Authentication error", extra={"error": str(e)})
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
        )
