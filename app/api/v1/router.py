from fastapi import APIRouter

from app.api.v1.routers import auth
from app.api.v1.routers import health
from app.api.v1.routers import admin
from app.api.v1.routers import user
from app.api.v1.routers import group
from app.api.v1.routers import form
from app.api.v1.routers import upload
from app.api.v1.routers import project
from app.api.v1.routers import financial_proxy

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])
api_router.include_router(user.router, prefix="/user", tags=["user"])
api_router.include_router(group.router, prefix="/group", tags=["group"])
api_router.include_router(form.router, prefix="/form", tags=["form"])
api_router.include_router(upload.router, prefix="/upload", tags=["upload"])
api_router.include_router(project.router, prefix="/project", tags=["project"])
api_router.include_router(financial_proxy.router,prefix="/financial-proxy",tags=["financial-proxy"],)