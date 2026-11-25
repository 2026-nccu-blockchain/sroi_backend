from pydantic import BaseModel, EmailStr, Field, StringConstraints
from datetime import datetime
from typing import Annotated, Optional

class ExternalInviteRequest(BaseModel):
    email: str
    organization: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=255)]
    # 帳號使用年限，從完成註冊開始算
    valid_years: int = Field(ge=1, le=4)

class ExtendExternalRequest(BaseModel):
    years: int = Field(ge=1, le=4)

class RejectEnrollmentRequest(BaseModel):
    # 退回一定要寫原因，學生會看到
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class UnconfirmGroupRequest(BaseModel):
    # 不同意一定要寫原因，空白也不行
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
