from fastapi import Request
from app.core.exceptions import APIException
from app.core.jwt import decode_access_token

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