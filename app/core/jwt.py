import hashlib

import jwt
from datetime import datetime, timedelta
from app.core.config import get_settings

settings = get_settings()

SECRET_KEY = settings.secret_key
ALGORITHM = settings.jwt_algorithm
JWT_EXPIRATION_MINUTES = settings.jwt_expiration_minutes

def create_access_token(data: dict, expires_delta: timedelta = timedelta(minutes=JWT_EXPIRATION_MINUTES)):
    to_encode = data.copy()
    expire = datetime.utcnow() + expires_delta
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_access_token(token: str):
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if not isinstance(payload.get("user_id"), str) or not payload["user_id"]:
        raise jwt.InvalidTokenError("Missing user_id claim")
    return payload


REGISTER_TOKEN_PURPOSE = "register"


def create_register_token(email: str, expires_delta: timedelta = timedelta(minutes=30)) -> str:
    return create_access_token({"email": email, "purpose": REGISTER_TOKEN_PURPOSE}, expires_delta)


def decode_register_token(token: str) -> str:
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if payload.get("purpose") != REGISTER_TOKEN_PURPOSE or not isinstance(payload.get("email"), str):
        raise jwt.InvalidTokenError("Not a register token")
    return payload["email"]


RESET_TOKEN_PURPOSE = "reset_password"


def password_fingerprint(hash_password: str) -> str:
    """目前密碼雜湊的指紋：重設後密碼改變，舊的重設 token 就失效（只能用一次）"""
    return hashlib.sha256(hash_password.encode("utf-8")).hexdigest()[:16]


def create_reset_token(email: str, hash_password: str, expires_delta: timedelta = timedelta(minutes=15)) -> str:
    return create_access_token(
        {"email": email, "purpose": RESET_TOKEN_PURPOSE, "pwd": password_fingerprint(hash_password)},
        expires_delta,
    )


def decode_reset_token(token: str) -> tuple[str, str]:
    """回傳 (email, 密碼指紋)"""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if (
        payload.get("purpose") != RESET_TOKEN_PURPOSE
        or not isinstance(payload.get("email"), str)
        or not isinstance(payload.get("pwd"), str)
    ):
        raise jwt.InvalidTokenError("Not a reset token")
    return payload["email"], payload["pwd"]


INVITE_TOKEN_PURPOSE = "external_invite"


def create_invite_token(invitation_id: str, nonce: str, expires_at: datetime) -> str:
    """校外邀請連結的 token；nonce 存在邀請資料裡，重寄時更換，舊連結就失效"""
    return jwt.encode(
        {"purpose": INVITE_TOKEN_PURPOSE, "invitation_id": invitation_id, "nonce": nonce, "exp": expires_at},
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def decode_invite_token(token: str) -> tuple[str, str]:
    """回傳 (invitation_id, nonce)"""
    payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    if (
        payload.get("purpose") != INVITE_TOKEN_PURPOSE
        or not isinstance(payload.get("invitation_id"), str)
        or not isinstance(payload.get("nonce"), str)
    ):
        raise jwt.InvalidTokenError("Not an invite token")
    return payload["invitation_id"], payload["nonce"]

