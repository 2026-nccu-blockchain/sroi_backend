from pydantic import BaseModel, EmailStr, StringConstraints
from datetime import datetime
from typing import Annotated, Optional

class RejectEnrollmentRequest(BaseModel):
    # 退回一定要寫原因，學生會看到
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]

class UnconfirmGroupRequest(BaseModel):
    # 不同意一定要寫原因，空白也不行
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
