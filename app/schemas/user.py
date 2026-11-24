from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class AddGroupRequest(BaseModel):
    title: str
    desc: str
    begin: datetime
    end: datetime