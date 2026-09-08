from fastapi import APIRouter

from app.api.v1.routers import auth
from app.api.v1.routers import health
from app.api.v1.routers import admin
from app.api.v1.routers import user
from app.api.v1.routers import form

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(user.router, prefix="/user", tags=["user"])
api_router.include_router(form.router, prefix="/form", tags=["form"])