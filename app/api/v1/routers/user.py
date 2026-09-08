from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.schemas.user import (
    VerificationRequest,
)
import re

router = APIRouter()


@router.post("/request_verification", response_model=APIResponse, response_model_exclude_none=True)
def user_request_verification(request: Request, data: VerificationRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    if db.query(Account).filter(Account.campus_id == data.campus_id and Account.role == Role.VERIFIED and Account.is_delete == False).first() is not None:
        raise APIException(400, "10011", "already verified")
    user = db.query(Account).filter(Account.user_id == user_id and Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if user.role != Role.UNVERIFIED:
        raise APIException(400, "10011", "already verified")
    user.role = Role.IN_PROGRESS
    user.campus_id = data.campus_id
    user.id_card_link = data.id_card_link
    db.commit()
    db.refresh(user)
    # 這邊要寄信

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


