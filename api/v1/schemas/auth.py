from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, HttpUrl


class GitHubLoginResponse(BaseModel):
    auth_url: HttpUrl
    message: str = "Redirect to this URL to authorize GitHub access"


class GitHubCallbackRequest(BaseModel):
    code: str = Field(..., description="Authorization code from GitHub")
    state: Optional[str] = Field(
        None, description="State parameter for CSRF protection"
    )


class DeviceFlowRequest(BaseModel):
    pass


class DeviceFlowInitiateResponse(BaseModel):
    device_code: str
    user_code: str
    verification_uri: HttpUrl
    verification_uri_complete: HttpUrl
    expires_in: int
    interval: int
    message: str = "Visit the verification URI and enter the user code"


class DeviceFlowVerifyRequest(BaseModel):
    device_code: str = Field(..., description="Device code from initiation")
    user_code: str = Field(..., description="User code to verify")


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    user: dict


class GitHubDataRequest(BaseModel):
    since: Optional[datetime] = Field(
        None, description="Start date/time (ISO 8601 format)"
    )
    until: Optional[datetime] = Field(
        None, description="End date/time (ISO 8601 format)"
    )
    repo: Optional[str] = Field(
        None, description="Repository name (format: owner/repo)"
    )
    state: Optional[str] = Field(
        None, description="State filter for PRs/issues (open, closed, all)"
    )
    author: Optional[str] = Field(None, description="Author filter for commits")
    page: Optional[int] = Field(1, ge=1, description="Page number for pagination")
    per_page: Optional[int] = Field(30, ge=1, le=100, description="Items per page")


class GitHubUserInfo(BaseModel):
    id: int
    login: str
    email: Optional[str] = None
    name: Optional[str] = None
    avatar_url: Optional[str] = None
