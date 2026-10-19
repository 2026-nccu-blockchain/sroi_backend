from fastapi import FastAPI, Request
from datetime import datetime, timedelta
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import APIException
from app.schemas.common import ErrorResponse
from app.core.middleware import CustomHeaderMiddleware, RateLimitMiddleware
from app.api.v1.router import api_router


settings = get_settings()
MAX_REQUESTS=settings.max_requests
WINDOW_SECONDS=settings.window_seconds

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.sroi_debug,
)

app.add_middleware(CustomHeaderMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=MAX_REQUESTS,
    window_seconds=WINDOW_SECONDS
)
# 正式環境由 nginx 同網域轉發、開發時由 Vite proxy 轉發，預設不開放跨域
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
        allow_headers=["Authorization", "Content-Type"],
    )

@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    return JSONResponse(
        status_code=exc.status_code,
          content=jsonable_encoder(ErrorResponse(
            status_code=exc.status_code_str,
            message=exc.message,
            response_datetime=datetime.now()
          ))
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)