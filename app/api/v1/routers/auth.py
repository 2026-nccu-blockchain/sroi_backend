from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import ACCOUNT_EXTERNAL, ACCOUNT_NCCU, Role, Account, ExternalInvitation, VerifiedCode, EMAIL_DOMAIN
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta, timezone
from app.core.jwt import (
    create_access_token,
    create_register_token,
    create_reset_token,
    decode_invite_token,
    decode_register_token,
    decode_reset_token,
    password_fingerprint,
)
from app.core.deps import verify_token, return_payload
from app.api.services.email import send_verification_code_email
from app.api.services.external_accounts import (
    add_years,
    is_external_expired,
    normalize_external_email,
    now_utc,
)
from app.api.services.enrollment import (
    DELETE_REASON_ENROLLMENT,
    DISABLED_REASONS,
    EXPIRED,
    enrollment_state,
    initial_due_year,
    soft_delete_account,
    student_id_of,
)
from app.schemas.auth import (
    LoginRequest,
    SendCodeRequest,
    VerifyCodeRequest,
    RegisterRequest,
    ChangePasswordRequest,
    ForgotPasswordSendCodeRequest,
    ForgotPasswordVerifyCodeRequest,
    ResetPasswordRequest,
    AcceptInvitationRequest,
    AccountIdentifier,
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
# 驗證碼用途；註冊與忘記密碼的驗證碼不能互用
PURPOSE_REGISTER = "register"
PURPOSE_RESET = "reset_password"


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


def resolve_identifier(data: AccountIdentifier) -> tuple[str, str]:
    """登入、忘記密碼的帳號：回傳 (accounts.email 的值, 帳號類型)。
    政大師生傳 email_prefix，校外人士傳完整 email；一律比對帳號類型，不能從政大分頁登入校外帳號"""
    if data.email:
        return normalize_external_email(data.email), ACCOUNT_EXTERNAL
    prefix = data.email_prefix.strip().lower()
    if not Account.verify_email_prefix(prefix):
        raise APIException(400, "10007", "invalid email format")
    return prefix, ACCOUNT_NCCU


def mail_address_of(key: str) -> str:
    """校外帳號存完整 email；政大帳號存前綴，要補上網域"""
    return key if "@" in key else key + EMAIL_DOMAIN


def disabled_account(db: Session, email: str):
    """被停權或逾期未完成在學驗證的帳號；這兩種都不能登入，也不能用相同的 email 重新註冊"""
    return db.query(Account).filter(
        Account.email == email,
        Account.is_delete == True,
        Account.delete_reason.in_(DISABLED_REASONS),
    ).order_by(Account.update_time.desc().nullslast()).first()


def raise_disabled(account: Account) -> None:
    if account.delete_reason == DELETE_REASON_ENROLLMENT:
        raise APIException(403, "10029", "account disabled: enrollment verification expired")
    raise APIException(403, "10035", "account suspended")


@router.post("/user/login", response_model=APIResponse, response_model_exclude_none=True)
def user_login(data: LoginRequest, db: Session = Depends(get_db)) -> dict:
    key, account_type = resolve_identifier(data)
    user = db.query(Account).filter(
        Account.email == key,
        Account.account_type == account_type,
        Account.is_delete == False,
    ).first()
    if user is None:
        # 密碼正確才告知停用原因，不透露帳號是否存在
        disabled = disabled_account(db, key)
        if disabled is not None and disabled.verify_password(data.password):
            raise_disabled(disabled)
        raise APIException(404, "10001", "user not found")
    if not user.verify_password(data.password):
        raise APIException(400, "10002", "invalid password")
    # 背景工作每小時才跑一次，登入時再確認一次是否已逾期
    state, _ = enrollment_state(db, user)
    if state == EXPIRED:
        soft_delete_account(db, user, DELETE_REASON_ENROLLMENT)
        db.commit()
        raise APIException(403, "10029", "account disabled: enrollment verification expired")
    # 校外帳號過了使用期限不能登入，管理員延長後就能再用
    if is_external_expired(user):
        raise APIException(403, "10038", "external account expired")
    payload = {"user_id": f"{user.user_id}"}
    token = create_access_token(payload)
    
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        token=token,
    )


def issue_code(db: Session, email_prefix: str, purpose: str) -> None:
    """寄出新的驗證碼：同一用途 60 秒內不能重寄，舊的未使用驗證碼作廢"""
    now = datetime.now(timezone.utc)
    latest = db.query(VerifiedCode).filter(
        VerifiedCode.email == email_prefix,
        VerifiedCode.purpose == purpose,
    ).order_by(VerifiedCode.create_time.desc()).first()
    # 避免一直按重寄灌爆信箱
    if latest is not None and now - latest.create_time < timedelta(seconds=CODE_RESEND_SECONDS):
        raise APIException(400, "10024", "please wait before resending")
    db.query(VerifiedCode).filter(
        VerifiedCode.email == email_prefix,
        VerifiedCode.purpose == purpose,
        VerifiedCode.is_verified == False,
        VerifiedCode.is_delete == False,
    ).update({VerifiedCode.is_delete: True}, synchronize_session=False)
    code = generate_code()
    db.add(VerifiedCode(
        email=email_prefix,
        code_hash=hash_code(code),
        purpose=purpose,
        expires_at=now + timedelta(minutes=CODE_EXPIRE_MINUTES),
        # 用程式時間：資料庫的 now() 在同一交易內相同，重寄間隔與「最新一筆」會判斷錯
        create_time=now,
    ))
    try:
        send_verification_code_email(
            recipient_email=mail_address_of(email_prefix),
            code=code,
            expire_minutes=CODE_EXPIRE_MINUTES,
            purpose=purpose,
        )
    except Exception:
        db.rollback()
        logger.exception("驗證碼寄送失敗：%s", email_prefix)
        raise APIException(500, "10028", "failed to send verification email")
    db.commit()


def check_code(db: Session, email_prefix: str, purpose: str, code: str) -> None:
    """驗證碼正確就標記已使用；過期、錯誤都丟出對應的錯誤（錯 5 次作廢）"""
    record = db.query(VerifiedCode).filter(
        VerifiedCode.email == email_prefix,
        VerifiedCode.purpose == purpose,
        VerifiedCode.is_verified == False,
        VerifiedCode.is_delete == False,
    ).order_by(VerifiedCode.create_time.desc()).first()
    if record is None:
        raise APIException(404, "10025", "verification code not found")
    if datetime.now(timezone.utc) > record.expires_at:
        record.is_delete = True
        db.commit()
        raise APIException(400, "10026", "verification code expired")
    if not secrets.compare_digest(hash_code(code.strip().upper()), record.code_hash):
        record.attempts += 1
        # 錯太多次就作廢，要重新寄送
        if record.attempts >= CODE_MAX_ATTEMPTS:
            record.is_delete = True
        db.commit()
        raise APIException(400, "10027", "invalid verification code")
    record.is_verified = True
    db.commit()


@router.post("/user/send_code", response_model=APIResponse, response_model_exclude_none=True)
def send_code(data: SendCodeRequest, db: Session = Depends(get_db)) -> dict:
    email_prefix = data.email_prefix.strip().lower()
    # 自行註冊只限政大信箱；前綴不能含 @（校外人士要由管理員邀請）
    if not Account.verify_email_prefix(email_prefix):
        raise APIException(400, "10007", "invalid email format")
    if db.query(Account).filter(Account.email == email_prefix, Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    # 停權、逾期未驗證的學號（email 前綴）不能重新註冊；逾期的重新註冊會再拿到一年
    disabled = disabled_account(db, email_prefix)
    if disabled is not None:
        raise_disabled(disabled)
    issue_code(db, email_prefix, PURPOSE_REGISTER)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/user/verify_code", response_model=APIResponse, response_model_exclude_none=True)
def verify_code(data: VerifyCodeRequest, db: Session = Depends(get_db)) -> dict:
    email = data.email_prefix
    check_code(db, email, PURPOSE_REGISTER, data.code)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        register_token=create_register_token(email),
    )


def active_account_for_reset(db: Session, data: AccountIdentifier) -> Account:
    """忘記密碼的帳號：要存在；被停權、逾期未驗證、校外帳號已到期的直接告知，不能用重設密碼繞過"""
    key, account_type = resolve_identifier(data)
    user = db.query(Account).filter(
        Account.email == key,
        Account.account_type == account_type,
        Account.is_delete == False,
    ).first()
    if user is not None:
        if is_external_expired(user):
            raise APIException(403, "10038", "external account expired")
        return user
    disabled = disabled_account(db, key)
    if disabled is not None:
        raise_disabled(disabled)
    raise APIException(404, "10001", "user not found")


@router.post("/user/forgot_password/send_code", response_model=APIResponse, response_model_exclude_none=True)
def forgot_password_send_code(data: ForgotPasswordSendCodeRequest, db: Session = Depends(get_db)) -> dict:
    """忘記密碼第 1 步：寄重設密碼的驗證碼（政大信箱，或校外人士的 email）"""
    user = active_account_for_reset(db, data)
    issue_code(db, user.email, PURPOSE_RESET)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/user/forgot_password/verify_code", response_model=APIResponse, response_model_exclude_none=True)
def forgot_password_verify_code(data: ForgotPasswordVerifyCodeRequest, db: Session = Depends(get_db)) -> dict:
    """忘記密碼第 2 步：驗證碼正確就發 15 分鐘有效、只能用一次的 reset_token"""
    user = active_account_for_reset(db, data)
    check_code(db, user.email, PURPOSE_RESET, data.code)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        reset_token=create_reset_token(user.email, user.hash_password),
    )


@router.post("/user/forgot_password/reset", response_model=APIResponse, response_model_exclude_none=True)
def forgot_password_reset(data: ResetPasswordRequest, db: Session = Depends(get_db)) -> dict:
    """忘記密碼第 3 步：用 reset_token 設定新密碼"""
    try:
        email, fingerprint = decode_reset_token(data.reset_token)
    except Exception:
        raise APIException(401, "10037", "invalid or expired reset token")
    user = db.query(Account).filter(Account.email == email, Account.is_delete == False).first()
    # 密碼已經改過（token 用過了）或帳號已被停用，token 都不能再用
    if user is None or not secrets.compare_digest(password_fingerprint(user.hash_password), fingerprint):
        raise APIException(401, "10037", "invalid or expired reset token")
    if not is_strong_password(data.new_password):
        raise APIException(400, "10010", "password is not strong")
    user.set_password(data.new_password)
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
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
    disabled = disabled_account(db, email)
    if disabled is not None:
        raise_disabled(disabled)
    # email 前綴是 9 碼數字才是學生，學號就是前綴；註冊後不能改 email，所以學號固定
    campus_id = student_id_of(email)
    new_account = Account(
        email=email,
        hash_password=" ", #不能是null，下面才會設密碼,
        name=data.name,
        role=Role.NORMAL,
        campus_id=campus_id,
        verify_due_year=initial_due_year(campus_id) if campus_id else None,
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


def pending_invitation(db: Session, token: str) -> ExternalInvitation:
    """邀請連結對應的邀請：連結要有效、沒被重寄取代、沒取消、還沒完成"""
    try:
        invitation_id, nonce = decode_invite_token(token)
    except Exception:
        raise APIException(400, "10039", "invalid or expired invitation link")
    invitation = db.query(ExternalInvitation).filter(
        ExternalInvitation.invitation_id == invitation_id,
        ExternalInvitation.is_delete == False,
        ExternalInvitation.accepted_at.is_(None),
    ).first()
    if (
        invitation is None
        or not secrets.compare_digest(invitation.token_nonce, nonce)
        or now_utc() >= invitation.expires_at
    ):
        raise APIException(400, "10039", "invalid or expired invitation link")
    return invitation


@router.get("/external_invitation", response_model=APIResponse, response_model_exclude_none=True)
def get_external_invitation(token: str, db: Session = Depends(get_db)) -> dict:
    """設定密碼頁：顯示邀請的 email（帳號）與所屬單位"""
    invitation = pending_invitation(db, token)
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        invitation={
            "email": invitation.email,
            "organization": invitation.organization,
            "valid_years": invitation.valid_years,
            "expires_at": invitation.expires_at,
        },
    )


@router.post("/external_invitation/accept", response_model=APIResponse, response_model_exclude_none=True)
def accept_external_invitation(data: AcceptInvitationRequest, db: Session = Depends(get_db)) -> dict:
    """校外人士設定姓名與密碼，這時才建立帳號；使用年限從今天開始算"""
    invitation = pending_invitation(db, data.token)
    if db.query(Account).filter(Account.email == invitation.email, Account.is_delete == False).first() is not None:
        raise APIException(400, "10006", "register duplicate")
    disabled = disabled_account(db, invitation.email)
    if disabled is not None:
        raise_disabled(disabled)
    if not is_strong_password(data.password):
        raise APIException(400, "10010", "password is not strong")
    now = now_utc()
    account = Account(
        email=invitation.email,
        hash_password=" ",
        name=data.name,
        role=Role.NORMAL,
        account_type=ACCOUNT_EXTERNAL,
        organization=invitation.organization,
        valid_until=add_years(now, invitation.valid_years),
    )
    account.set_password(data.password)
    db.add(account)
    db.flush()
    invitation.accepted_at = now
    invitation.accepted_user_id = account.user_id
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )

