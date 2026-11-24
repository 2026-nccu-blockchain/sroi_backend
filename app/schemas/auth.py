from pydantic import BaseModel, EmailStr, Field, StringConstraints, model_validator
from datetime import datetime
from typing import Annotated, Optional


class AccountIdentifier(BaseModel):
    """政大師生傳 email_prefix（@ 前面）；校外人士傳完整 email，兩者擇一"""
    email_prefix: Optional[str] = None
    email: Optional[str] = None

    @model_validator(mode="after")
    def exactly_one(self) -> "AccountIdentifier":
        if bool(self.email_prefix) == bool(self.email):
            raise ValueError("請輸入 email_prefix 或 email 其中一個")
        return self

# email 相關欄位都只傳 @ 前面的部分，網域固定是 @nccu.edu.tw
class LoginRequest(AccountIdentifier):
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
class ForgotPasswordSendCodeRequest(AccountIdentifier):
    pass

class ForgotPasswordVerifyCodeRequest(AccountIdentifier):
    code: str

class ResetPasswordRequest(BaseModel):
    reset_token: str
    new_password: str

# 校外人士點邀請連結後設定姓名與密碼
class AcceptInvitationRequest(BaseModel):
    token: str
    name: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=20)]
    password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str