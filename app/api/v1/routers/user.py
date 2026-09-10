from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account, VerifiedInProgress, Group
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.schemas.user import (
    VerificationRequest,
    AddGroupRequest
)
import re

router = APIRouter()


@router.post("/request_verification", response_model=APIResponse, response_model_exclude_none=True)
def request_verification(request: Request, data: VerificationRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    if db.query(Account).filter(Account.campus_id == data.campus_id, Account.role == Role.VERIFIED, Account.is_delete == False).first() is not None:
        raise APIException(400, "10011", "already verified")
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if user.role != Role.UNVERIFIED:
        raise APIException(400, "10011", "already verified")
    new_ver = VerifiedInProgress(
        campus_id=data.campus_id,
        user_id=user_id,
        id_card_link=data.id_card_link,
        is_ver=True
    )
    user.role = Role.IN_PROGRESS
    db.add(new_ver)
    db.commit()
    # 這邊要寄信

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/change_campus_id", response_model=APIResponse, response_model_exclude_none=True)
def change_campus_id(request: Request, data: VerificationRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    if db.query(Account).filter(Account.campus_id == data.campus_id, Account.role != Role.UNVERIFIED, Account.Role != Role.IN_PROGRESS, Account.is_delete == False).first() is not None:
        raise APIException(400, "10012", "the same campus id")
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if user.role == Role.UNVERIFIED or user.role == Role.IN_PROGRESS:
        raise APIException(400, "10008", "permission denied")
    new_ver = VerifiedInProgress(
        campus_id=data.campus_id,
        user_id=user_id,
        id_card_link=data.id_card_link,
        is_ver=False
    )
    db.add(new_ver)
    db.commit()
    # 這邊要寄信

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/add_group", response_model=APIResponse, response_model_exclude_none=True)
def add_group(request: Request, data: AddGroupRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    if user.role == Role.UNVERIFIED or user.role == Role.IN_PROGRESS:
        raise APIException(400, "10008", "permission denied")
    new_group = Group(
        title=data.title,
        desc=data.desc,
        begin=data.begin,
        end=data.end,
        status=Role.IN_PROGRESS,
        leader_list=[f"{user_id}"]
    )
    db.add(new_group)
    db.commit()
    db.refresh(new_group)
    user.group_list = (user.group_list or []) + [f"{new_group.group_id}"]
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )