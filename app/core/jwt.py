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
