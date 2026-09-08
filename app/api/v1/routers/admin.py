from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
# from app.schemas.admin import (
# )
import re

router = APIRouter()


@router.post("/confirm_verification/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def admin_confirm_verification(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId and Account.is_delete == False).first()
    if user is None and user.role.value != Role.IN_PROGRESS.value:
        raise APIException(404, "10001", "user not found")
    user.role = Role.VERIFIED
    db.commit()
    db.refresh(user)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )