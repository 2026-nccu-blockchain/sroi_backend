from fastapi import FastAPI, Request
from datetime import datetime
from fastapi.encoders import jsonable_encoder
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import get_settings
from app.core.exceptions import APIException
from app.schemas.common import ErrorResponse
from app.core.middleware import CustomHeaderMiddleware, RateLimitMiddleware
from app.api.v1.router import api_router
import pytz


settings = get_settings()
MAX_REQUESTS=settings.max_requests
WINDOW_SECONDS=settings.window_seconds

app = FastAPI(
    title=settings.app_name,
    version=settings.app_version,
    debug=settings.debug,
)

app.add_middleware(CustomHeaderMiddleware)
app.add_middleware(
    RateLimitMiddleware,
    max_requests=MAX_REQUESTS,
    window_seconds=WINDOW_SECONDS
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.exception_handler(APIException)
async def api_exception_handler(request: Request, exc: APIException):
    return JSONResponse(
        status_code=exc.status_code,
          content=jsonable_encoder(ErrorResponse(
            status_code=exc.status_code_str,
            desc=exc.desc,
            response_datetime=datetime.now(pytz.timezone('Asia/Taipei'))
          ))
    )

app.include_router(api_router, prefix=settings.api_v1_prefix)