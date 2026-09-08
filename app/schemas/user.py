from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class VerificationRequest(BaseModel):
    campus_id: str
    id_card_link: str