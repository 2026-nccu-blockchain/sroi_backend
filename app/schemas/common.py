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
    token: Optional[str] = None
    user_id: Optional[str] = None
    campus_id: Optional[str] = None
    email: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None
    users: Optional[list] = None
    id_card_link: Optional[str] = None
    agree_groups: Optional[list] = None
    in_progress_groups: Optional[list] = None
    disagree_groups: Optional[list] = None
    verified_groups: Optional[list] = None
    unverified_groups: Optional[list] = None
    status: Optional[str] = None
    reason: Optional[str] = None
    group_id: Optional[str] = None
    title: Optional[str] = None
    desc: Optional[str] = None
    begin: Optional[datetime] = None
    end: Optional[datetime] = None
    group_leaders: Optional[list] = None
    group_members: Optional[list] = None
    group_role: Optional[str] = None
    admin: Optional[list] = None
    db_editor: Optional[list] = None
    verified_user: Optional[list] = None
    in_progress_user: Optional[list] = None
    unverified_user: Optional[list] = None
    change_request_user: Optional[list] = None
    change_request: Optional[dict] = None
    

# 錯誤回應的格式 
class ErrorResponse(BaseModel):
    status_code: str
    message: str
    response_datetime: datetime