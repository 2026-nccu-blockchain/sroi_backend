from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class InviteRequest(BaseModel):
    user_id: str

class ChangeRoleRequest(BaseModel):
    user_id: str
    is_leader: bool