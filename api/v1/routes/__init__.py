from fastapi import APIRouter
from api.v1.routes import auth

version_one = APIRouter()

# Include routers
version_one.include_router(auth.router)
