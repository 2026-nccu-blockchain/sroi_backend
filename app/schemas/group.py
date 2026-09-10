from pydantic import BaseModel
from datetime import datetime
from typing import Optional

class InviteRequest(BaseModel):
    campus_id: str
    is_leader: bool