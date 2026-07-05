from fastapi import APIRouter

from app.api.v1.routers import auth
from app.api.v1.routers import health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])