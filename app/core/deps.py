from fastapi import Depends, Request
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.core.jwt import decode_access_token
from app.db.session import get_db

def verify_token(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise APIException(401, "10004", "Authorization header missing or invalid")
    token = auth_header.split(" ")[1]
    try:
        decode_access_token(token)  # 只驗證，不回傳 payload
    except Exception:
        raise APIException(401, "10005", "Invalid or expired token")
    
def return_payload(request: Request):
    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        raise APIException(401, "10004", "Authorization header missing or invalid")
    token = auth_header.split(" ")[1]
    try:
        return decode_access_token(token)
    except Exception:
        raise APIException(401, "10005", "Invalid or expired token")


def require_enrollment_access(request: Request, db: Session = Depends(get_db)) -> None:
    """需要在學驗證的學生只能用登入、個人資料與驗證相關的 API；沒帶 token 的請求（公開表單）不檢查"""
    # 放在函式裡 import，避免 deps 與 model / service 互相 import
    from app.api.services.enrollment import BLOCKING_STATES, enrollment_state
    from app.api.services.external_accounts import is_external_expired
    from app.models.model import Account

    auth_header = request.headers.get("Authorization")
    if not auth_header or not auth_header.startswith("Bearer "):
        return
    try:
        payload = decode_access_token(auth_header.split(" ")[1])
    except Exception:
        # token 無效交給各 API 自己的檢查回 401
        return
    account = db.query(Account).filter(Account.user_id == payload.get("user_id")).first()
    # 帳號已被刪除（例如逾期未驗證、停權）或校外帳號已到期時，舊的 token 也不能再用
    if account is None or account.is_delete or is_external_expired(account):
        raise APIException(401, "10005", "Invalid or expired token")
    state, _ = enrollment_state(db, account)
    if state in BLOCKING_STATES:
        raise APIException(403, "10030", "enrollment verification required")
