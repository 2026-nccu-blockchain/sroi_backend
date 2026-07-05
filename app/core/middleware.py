from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware
from fastapi import Request
from collections import defaultdict
from datetime import datetime, timedelta
import time


class CustomHeaderMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request, call_next):
        start_time = time.time()
        response = await call_next(request)
        process_time = time.time() - start_time
        response.headers["X-Process-Time"] = str(process_time)
        return response
    

class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(
        self,
        app,
        max_requests: int,
        window_seconds: int
    ):
        super().__init__(app)
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.clients = defaultdict(dict)
        # {
        #   ip: {
        #       count: 5,
        #       reset_time: datetime
        #   }
        # }

    async def dispatch(self, request: Request, call_next):
        client_ip = request.client.host
        now = datetime.now()
        if client_ip not in self.clients:
            self.clients[client_ip] = {
                "count": 1,
                "reset_time": now + timedelta(seconds=self.window_seconds)
            }
        else:
            client = self.clients[client_ip]
            if now > client["reset_time"]:
                client["count"] = 1
                client["reset_time"] = now + timedelta(seconds=self.window_seconds)
            else:
                client["count"] += 1
                if client["count"] > self.max_requests:
                    return JSONResponse(
                        status_code=429,
                        content={
                            "code": "00007",
                            "message": "too many requests"
                        }
                    )

        return await call_next(request)