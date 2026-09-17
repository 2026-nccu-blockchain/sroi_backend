from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account, VerifiedInProgress, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
# from app.schemas.admin import (
# )
import re

router = APIRouter()


@router.post("/confirm_verification/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def confirm_verification(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.is_delete == False).first()
    if user is None or user.role != Role.IN_PROGRESS:
        raise APIException(404, "10001", "user not found")
    verification = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == True, VerifiedInProgress.is_delete == False).first()
    if verification is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.VERIFIED
    user.campus_id = verification.campus_id
    user.id_card_link = verification.id_card_link
    verification.is_delete = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/unconfirm_verification/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def unconfirm_verification(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.is_delete == False).first()
    if user is None or user.role != Role.IN_PROGRESS:
        raise APIException(404, "10001", "user not found")
    verification = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == True, VerifiedInProgress.is_delete == False).first()
    if verification is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.UNVERIFIED
    verification.is_delete = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/confirm_change/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def confirm_change(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.is_delete == False).first()
    if user is None or user.role == Role.UNVERIFIED or user.role == Role.IN_PROGRESS:
        raise APIException(404, "10001", "user not found")
    verification = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).first()
    if verification is None:
        raise APIException(404, "10001", "user not found")
    user.campus_id = verification.campus_id
    user.id_card_link = verification.id_card_link
    verification.is_delete = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/unconfirm_change/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def unconfirm_change(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.is_delete == False).first()
    if user is None or user.role == Role.UNVERIFIED or user.role == Role.IN_PROGRESS:
        raise APIException(404, "10001", "user not found")
    verification = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).first()
    if verification is None:
        raise APIException(404, "10001", "user not found")
    verification.is_delete = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/confirm_group/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def confirm_group(request: Request, GroupId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.IN_PROGRESS, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    group.status = Role.VERIFIED
    new_GA = GroupAccount(
        group_id=group.group_id,
        user_id=group.leader_list[0],
        group_role=Role.LEADER
    )
    db.add(new_GA)
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/unconfirm_group/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def unconfirm_group(request: Request, GroupId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    if payload["role"] != Role.ADMIN.value:
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.IN_PROGRESS, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    group.status = Role.UNVERIFIED
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )