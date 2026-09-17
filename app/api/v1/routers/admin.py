from fastapi import APIRouter, Request, Depends
from sqlalchemy import or_
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
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


@router.get("/all_user", response_model=APIResponse, response_model_exclude_none=True)
def show_all_user(request: Request, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    all_user = db.query(Account).filter(Account.is_delete == False).all()
    admin = []
    db_editor = []
    verified_user = []
    in_progress_user = []
    unverified_user = []
    for user in all_user:
        if user.role == Role.ADMIN:
            admin.append(user)
        elif user.role == Role.DB_EDITOR:
            db_editor.append(user)
        elif user.role == Role.VERIFIED:
            verified_user.append(user)
        elif user.role == Role.IN_PROGRESS:
            in_progress_user.append(user)
        elif user.role == Role.UNVERIFIED:
            unverified_user.append(user)
    
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        admin=[
            {
                "user_id": a.user_id,
                "campus_id": a.campus_id,
                "name": a.name
            }
            for a in admin
        ],
        db_editor=[
            {
                "user_id": de.user_id,
                "campus_id": de.campus_id,
                "name": de.name
            }
            for de in db_editor
        ],
        verified_user=[
            {
                "user_id": vu.user_id,
                "campus_id": vu.campus_id,
                "name": vu.name
            }
            for vu in verified_user
        ],
        in_progress_user=[
            {
                "user_id": ipu.user_id,
                "campus_id": ipu.campus_id,
                "name": ipu.name
            }
            for ipu in in_progress_user
        ],
        unverified_user=[
            {
                "user_id": uvu.user_id,
                "campus_id": uvu.campus_id,
                "name": uvu.name
            }
            for uvu in unverified_user
        ],
    )


@router.post("/add_db_editor/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def add_db_editor(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.role == Role.VERIFIED, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.DB_EDITOR
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/remove_db_editor/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def remove_db_editor(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.role == Role.DB_EDITOR, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.VERIFIED
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/add_admin/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def add_admin(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, 
                                    or_(Account.role == Role.VERIFIED, Account.role == Role.DB_EDITOR), Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.ADMIN
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/remove_admin/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def remove_admin(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.role == Role.ADMIN, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    user.role = Role.VERIFIED
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.delete("/delete_user/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def delete_user(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    user = db.query(Account).filter(Account.user_id == UserId, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    user.is_delete = True
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )