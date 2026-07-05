from pydantic import BaseModel
from datetime import datetime
from typing import Optional


# 合法請求的回應格式
class APIResponse(BaseModel):
    status_code: str
    message: Optional[str] = None
    response_datetime: datetime
    # 不加 data 欄位，或直接把要回傳的欄位寫在這層
    # 其他欄位依需求加
    

# 錯誤回應的格式 
class ErrorResponse(BaseModel):
    status_code: str
    message: str
    response_datetime: datetime