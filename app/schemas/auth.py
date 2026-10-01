from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

class LoginRequest(BaseModel):
    email: str
    password: str

class RegisterRequest(BaseModel):
    email: str
    password: str
    name: str

class ChangeEmailRequest(BaseModel):
    email: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str