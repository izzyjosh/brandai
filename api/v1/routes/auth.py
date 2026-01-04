from fastapi import APIRouter, Query, HTTPException, status
from api.v1.responses.success_response import success_response
from api.v1.schemas.auth import (
    GitHubLoginResponse,
    TokenResponse,
    DeviceFlowInitiateResponse,
    DeviceFlowVerifyRequest,
)
from api.v1.services.auth import AuthService

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/github/login", response_model=GitHubLoginResponse)
async def github_login(
    state: str = Query(None, description="Optional state parameter for CSRF protection")
):
    """
    Initiate GitHub OAuth login flow.
    Returns the authorization URL that the user should be redirected to.
    """
    try:
        auth_url, state_param = AuthService.initiate_github_oauth(state)
        return success_response(
            message="GitHub OAuth URL generated",
            data={
                "auth_url": auth_url,
                "state": state_param,
            },
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate GitHub OAuth: {str(e)}",
        )


@router.get("/github/callback")
async def github_callback(
    code: str = Query(..., description="Authorization code from GitHub"),
    state: str = Query(None, description="State parameter for CSRF protection"),
):
    """
    Handle GitHub OAuth callback.
    Exchanges the authorization code for an access token and returns a JWT token.
    """
    try:
        result = await AuthService.handle_github_callback(code, state)
        return success_response(message="Authentication successful", data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to handle GitHub callback: {str(e)}",
        )


@router.post("/github/device/initiate", response_model=DeviceFlowInitiateResponse)
async def device_flow_initiate():
    """
    Initiate GitHub device flow.
    Returns device code and user code that the user needs to enter on GitHub.
    """
    try:
        result = await AuthService.initiate_device_flow()
        return success_response(message="Device flow initiated", data=result)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate device flow: {str(e)}",
        )


@router.post("/github/device/verify", response_model=TokenResponse)
async def device_flow_verify(request: DeviceFlowVerifyRequest):
    """
    Verify device code and exchange for access token.
    This endpoint should be polled until the user authorizes the device.
    """
    try:
        result = await AuthService.verify_device_code(
            request.device_code, request.user_code
        )
        return success_response(
            message="Device verified and authenticated", data=result
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to verify device code: {str(e)}",
        )
