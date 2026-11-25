from fastapi import APIRouter, Depends

from app.core.deps import require_enrollment_access

from app.api.v1.routers import auth
from app.api.v1.routers import health
from app.api.v1.routers import admin
from app.api.v1.routers import user
from app.api.v1.routers import group
from app.api.v1.routers import form
from app.api.v1.routers import project
from app.api.v1.routers import financial_proxy

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
# 需要在學驗證的學生只能用 auth、user（個人資料與驗證）的 API，其他都擋下
enrollment_guard = [Depends(require_enrollment_access)]
api_router.include_router(admin.router, prefix="/admin", tags=["admin"], dependencies=enrollment_guard)
api_router.include_router(user.router, prefix="/user", tags=["user"])
api_router.include_router(group.router, prefix="/group", tags=["group"], dependencies=enrollment_guard)
api_router.include_router(form.router, prefix="/form", tags=["form"], dependencies=enrollment_guard)
api_router.include_router(project.router, prefix="/project", tags=["project"], dependencies=enrollment_guard)
api_router.include_router(financial_proxy.router, prefix="/financial-proxy", tags=["financial-proxy"], dependencies=enrollment_guard)