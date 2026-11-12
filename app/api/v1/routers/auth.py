from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account, VerifiedCode, EMAIL_DOMAIN
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta, timezone
from app.core.jwt import create_access_token, create_register_token, decode_register_token
from app.core.deps import verify_token, return_payload
from app.api.services.email import send_verification_code_email
from app.schemas.auth import (
    LoginRequest,
    SendCodeRequest,
    VerifyCodeRequest,
    RegisterRequest,
    ChangeEmailRequest,
    ChangePasswordRequest
)
import hashlib
import logging
import re
import secrets

router = APIRouter()
logger = logging.getLogger(__name__)

CODE_LENGTH = 8
# 拿掉容易看錯的 0/O、1/I/L
CODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
CODE_EXPIRE_MINUTES = 5
CODE_MAX_ATTEMPTS = 5
CODE_RESEND_SECONDS = 60


def generate_code() -> str:
    return "".join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def hash_code(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


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
    user = db.query(Account).filter(Account.email == data.email_prefix, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if not user.verify_password(data.password):
        raise APIException(400, "10002", "invalid password")
    payload = {"user_id": f"{user.user_id}"}
    token = create_access_token(payload)
    
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        token=token,
    )


@router.post("/user/send_code", response_model=APIResponse, response_model_exclude_none=True)
def send_code(data: SendCodeRequest, db: Session = Depends(get_db)) -> dict:
    email_prefix = data.email_prefix
    if db.query(Account).filter(Account.email == email_prefix, Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    now = datetime.now(timezone.utc)
    latest = db.query(VerifiedCode).filter(VerifiedCode.email == email_prefix).order_by(VerifiedCode.create_time.desc()).first()
    # 避免一直按重寄灌爆信箱
    if latest is not None and now - latest.create_time < timedelta(seconds=CODE_RESEND_SECONDS):
        raise APIException(400, "10024", "please wait before resending")
    db.query(VerifiedCode).filter(
        VerifiedCode.email == email_prefix,
        VerifiedCode.is_verified == False,
        VerifiedCode.is_delete == False,
    ).update({VerifiedCode.is_delete: True}, synchronize_session=False)
    code = generate_code()
    db.add(VerifiedCode(
        email=email_prefix,
        code_hash=hash_code(code),
        expires_at=now + timedelta(minutes=CODE_EXPIRE_MINUTES),
    ))
    try:
        send_verification_code_email(recipient_email=email_prefix + EMAIL_DOMAIN, code=code, expire_minutes=CODE_EXPIRE_MINUTES)
    except Exception:
        db.rollback()
        logger.exception("驗證碼寄送失敗：%s", email_prefix)
        raise APIException(500, "10028", "failed to send verification email")
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/user/verify_code", response_model=APIResponse, response_model_exclude_none=True)
def verify_code(data: VerifyCodeRequest, db: Session = Depends(get_db)) -> dict:
    email = data.email_prefix
    record = db.query(VerifiedCode).filter(
        VerifiedCode.email == email,
        VerifiedCode.is_verified == False,
        VerifiedCode.is_delete == False,
    ).order_by(VerifiedCode.create_time.desc()).first()
    if record is None:
        raise APIException(404, "10025", "verification code not found")
    if datetime.now(timezone.utc) > record.expires_at:
        record.is_delete = True
        db.commit()
        raise APIException(400, "10026", "verification code expired")
    if not secrets.compare_digest(hash_code(data.code.strip().upper()), record.code_hash):
        record.attempts += 1
        # 錯太多次就作廢，要重新寄送
        if record.attempts >= CODE_MAX_ATTEMPTS:
            record.is_delete = True
        db.commit()
        raise APIException(400, "10027", "invalid verification code")
    record.is_verified = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        register_token=create_register_token(email),
    )


@router.post("/user/register", response_model=APIResponse, response_model_exclude_none=True)
def user_register(data: RegisterRequest, db: Session = Depends(get_db)) -> dict:
    try:
        email = decode_register_token(data.register_token)
    except Exception:
        raise APIException(401, "10005", "Invalid or expired token")
    if db.query(Account).filter(Account.email == email, Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    if not is_strong_password(data.password):
        raise APIException(400, "10010", "password is not strong")
    new_account = Account(
        email=email,
        hash_password=" ", #不能是null，下面才會設密碼,
        name=data.name,
        role=Role.NORMAL
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


@router.put("/user/change_email", response_model=APIResponse, response_model_exclude_none=True)
def change_email(request: Request, data: ChangeEmailRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    email = data.email_prefix
    if db.query(Account).filter(Account.email == email, Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    user.email = email
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.put("/user/change_password", response_model=APIResponse, response_model_exclude_none=True)
def change_password(request: Request, data: ChangePasswordRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if not user.verify_password(data.old_password):
        raise APIException(400, "10002", "invalid password")
    if not is_strong_password(data.new_password):
        raise APIException(400, "10010", "password is not strong")
    user.set_password(data.new_password)
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )