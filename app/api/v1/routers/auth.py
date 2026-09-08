from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.jwt import create_access_token, decode_access_token
from app.core.deps import verify_token, return_payload
from app.schemas.auth import (
    LoginRequest,
    RegisterRequest,
)
import re

router = APIRouter()

def is_strong_password(password: str) -> bool:
    if len(password) < 8:
        return False
    if not re.search(r"[A-Z]", password):
        return False
    if not re.search(r"[a-z]", password):
        return False
    if not re.search(r"\d", password):
        return False
    return True


@router.post("/user/login", response_model=APIResponse, response_model_exclude_none=True)
def user_login(data: LoginRequest, db: Session = Depends(get_db)) -> dict:
    if not Account.verify_email(data.email):
        raise APIException(400, "10007", "incorrect email format")
    user = db.query(Account).filter(Account.email == data.email and Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if not user.verify_password(data.password):
        raise APIException(400, "10002", "invalid password")
    payload = {"user_id": f"{user.user_id}", "role": f"{user.role.value}"}
    token = create_access_token(payload)
    
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        token=token,
    )


@router.post("/user/register", response_model=APIResponse, response_model_exclude_none=True)
def user_register(data: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    if not Account.verify_email(data.email):
        raise APIException(400, "10007", "incorrect email format")
    if not is_strong_password(data.password):
        raise APIException(400, "10010", "password is not strong")
    if db.query(Account).filter(Account.email == data.email and Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    new_account = Account(
        email=data.email,
        hash_password=" ", #不能是null，下面才會設密碼,
        name=data.name,
        role=Role.UNVERIFIED
    )
    new_account.set_password(data.password)
    db.add(new_account)
    db.commit()
    db.refresh(new_account)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )