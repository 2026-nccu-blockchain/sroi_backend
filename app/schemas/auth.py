from pydantic import BaseModel, EmailStr
from datetime import datetime
from typing import Optional

# email 相關欄位都只傳 @ 前面的部分，網域固定是 @nccu.edu.tw
class LoginRequest(BaseModel):
    email_prefix: str
    password: str

class SendCodeRequest(BaseModel):
    email_prefix: str

class VerifyCodeRequest(BaseModel):
    email_prefix: str
    code: str

# email 由驗證碼通過後拿到的 register_token 提供
class RegisterRequest(BaseModel):
    register_token: str
    password: str
    name: str

# 忘記密碼：寄驗證碼 → 驗證碼換 reset_token → 用 reset_token 設定新密碼
class ForgotPasswordSendCodeRequest(BaseModel):
    email_prefix: str

class ForgotPasswordVerifyCodeRequest(BaseModel):
    email_prefix: str
    code: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str