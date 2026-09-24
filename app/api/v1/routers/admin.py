from fastapi import APIRouter, Request, Depends
from fastapi.responses import FileResponse
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
from pathlib import Path

router = APIRouter()

UPLOAD_DIR = (Path(__file__).resolve().parents[3] / "uploads" / "images").resolve()


def latest_change_request(db: Session, user_id: str):
    return db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == user_id, VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).first()


def latest_change_requests(db: Session) -> dict:
    # 每位使用者只取最新一筆待審核的學號變更申請
    pending = db.query(VerifiedInProgress).filter(VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).all()
    latest = {}
    for v in pending:
        latest.setdefault(v.user_id, v)
    return latest


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
    # 送出申請後學號可能已被其他帳號審核通過
    if Account.campus_id_taken(db, verification.campus_id):
        raise APIException(400, "10012", "the same campus id")
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
    # 舊資料可能有多筆待審核，以最新一筆為準，其餘一併結案
    verifications = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).all()
    if not verifications:
        raise APIException(404, "10001", "user not found")
    verification = verifications[0]
    # 送出申請後學號可能已被其他帳號審核通過
    if Account.campus_id_taken(db, verification.campus_id, exclude_user_id=UserId):
        raise APIException(400, "10012", "the same campus id")
    user.campus_id = verification.campus_id
    user.id_card_link = verification.id_card_link
    for v in verifications:
        v.is_delete = True
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
    verifications = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == False, VerifiedInProgress.is_delete == False).all()
    if not verifications:
        raise APIException(404, "10001", "user not found")
    for v in verifications:
        v.is_delete = True
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
    # 學號變更申請不影響角色，使用者同時也會出現在原本的角色清單
    change_requests = latest_change_requests(db)
    change_request_user = [
        user for user in all_user
        if user.user_id in change_requests and user.role in (Role.ADMIN, Role.DB_EDITOR, Role.VERIFIED)
    ]

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
        change_request_user=[
            {
                "user_id": cru.user_id,
                "campus_id": cru.campus_id,
                "name": cru.name,
                "new_campus_id": change_requests[cru.user_id].campus_id
            }
            for cru in change_request_user
        ],
    )


@router.get("/one_user/{UserId}", response_model=APIResponse, response_model_exclude_none=True)
def show_one_user(request: Request, UserId: str, db: Session = Depends(get_db)) -> dict:
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
    if user.role == Role.ADMIN or user.role == Role.DB_EDITOR or user.role == Role.VERIFIED:
        change = latest_change_request(db, UserId)
        return APIResponse(
            status_code="00000",
            message="success",
            response_datetime=datetime.now(),
            user_id=user.user_id,
            campus_id=user.campus_id,
            name=user.name,
            email=user.email,
            role=user.role.value,
            id_card_link=user.id_card_link,
            change_request={
                "campus_id": change.campus_id,
                "id_card_link": change.id_card_link,
                "create_time": change.create_time
            } if change else None
        )
    elif user.role == Role.IN_PROGRESS:
        progress = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_ver == True, VerifiedInProgress.is_delete == False).first()
        if progress is None:
            raise APIException(404, "10001", "user not found")
        return APIResponse(
            status_code="00000",
            message="success",
            response_datetime=datetime.now(),
            user_id=user.user_id,
            campus_id=progress.campus_id,
            name=user.name,
            email=user.email,
            role=user.role.value,
            id_card_link=progress.id_card_link
        )
    # 未驗證：沒有學號和照片
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        user_id=user.user_id,
        name=user.name,
        email=user.email,
        role=user.role.value,
    )


@router.get("/id_card/{filename}")
def get_id_card(request: Request, filename: str, db: Session = Depends(get_db)):
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    # 防止 ../ 讀到上傳資料夾以外的檔案
    path = (UPLOAD_DIR / filename).resolve()
    if path.parent != UPLOAD_DIR or not path.is_file():
        raise APIException(404, "10021", "image not found")
    return FileResponse(path)


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
    # 不能移除自己，確保系統至少保留一位管理員
    if UserId == admin_id:
        raise APIException(400, "10015", "can't change own permissions")
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
    if UserId == admin_id:
        raise APIException(400, "10015", "can't change own permissions")
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


@router.get("/search_user", response_model=APIResponse, response_model_exclude_none=True)
def group_search_user(request: Request, Search: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    users = db.query(Account).filter(or_(Account.campus_id.ilike(f"%{Search}%"), Account.name.ilike(f"%{Search}%")), 
                                     Account.role != Role.UNVERIFIED, Account.role != Role.IN_PROGRESS, Account.is_delete == False).all()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        users=[
            {
                "user_id": user.user_id,
                "campus_id": user.campus_id,
                "name": user.name
            }
            for user in users
        ],
    )