from pydantic import BaseModel, EmailStr, StringConstraints
from datetime import datetime
from typing import Annotated, Optional

class UnconfirmGroupRequest(BaseModel):
    # 不同意一定要寫原因，空白也不行
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
