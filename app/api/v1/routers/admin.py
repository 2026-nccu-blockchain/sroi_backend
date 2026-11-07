from fastapi import APIRouter, Request, Depends
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from app.db.session import get_db
from app.models.model import Role, GroupRole, GroupStatus, Account, VerifiedInProgress, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.core.permissions import count_group_leaders, get_group_members
from app.schemas.admin import (
    UnconfirmGroupRequest
)
import re

router = APIRouter()

def latest_change_request(db: Session, user_id: str):
    return db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == user_id, VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).first()


def latest_change_requests(db: Session) -> dict:
    # 每位使用者只取最新一筆待審核的學號變更申請
    pending = db.query(VerifiedInProgress).filter(VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).all()
    latest = {}
    for v in pending:
        latest.setdefault(v.user_id, v)
    return latest


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
    if user is None:
        raise APIException(404, "10001", "user not found")
    # 舊資料可能有多筆待審核，以最新一筆為準，其餘一併結案
    verifications = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_delete == False).order_by(VerifiedInProgress.create_time.desc()).all()
    if not verifications:
        raise APIException(404, "10001", "user not found")
    verification = verifications[0]
    # 送出申請後學號可能已被其他帳號審核通過
    if Account.campus_id_taken(db, verification.campus_id, exclude_user_id=UserId):
        raise APIException(400, "10012", "the same campus id")
    user.campus_id = verification.campus_id
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
    if user is None:
        raise APIException(404, "10001", "user not found")
    verifications = db.query(VerifiedInProgress).filter(VerifiedInProgress.user_id == UserId, VerifiedInProgress.is_delete == False).all()
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
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == GroupStatus.IN_PROGRESS, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    # 申請人在 add_group 時就已經是組長，這裡只要改狀態
    if count_group_leaders(db, group.group_id) == 0:
        raise APIException(400, "10023", "group has no applicant")
    group.status = GroupStatus.VERIFIED
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/unconfirm_group/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def unconfirm_group(request: Request, GroupId: str, data: UnconfirmGroupRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == GroupStatus.IN_PROGRESS, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    group.status = GroupStatus.UNVERIFIED
    group.reason = data.reason
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
    normal_user = []
    for user in all_user:
        if user.role == Role.ADMIN:
            admin.append(user)
        elif user.role == Role.DB_EDITOR:
            db_editor.append(user)
        elif user.role == Role.NORMAL:
            normal_user.append(user)
    # 學號變更申請不影響角色，使用者同時也會出現在原本的角色清單
    change_requests = latest_change_requests(db)
    change_request_user = [user for user in all_user if user.user_id in change_requests]

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
        normal_user=[
            {
                "user_id": nu.user_id,
                "campus_id": nu.campus_id,
                "name": nu.name
            }
            for nu in normal_user
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
        change_request={
            "campus_id": change.campus_id,
            "create_time": change.create_time
        } if change else None
    )


@router.get("/all_groups", response_model=APIResponse, response_model_exclude_none=True)
def show_all_groups(request: Request, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")    
    # 一次載入建立者，避免每個群組各查一次
    all_groups = db.query(Group).options(selectinload(Group.creator)).filter(Group.is_delete == False).all()
    agree_groups = []
    in_progress_groups = []
    disagree_groups = []
    for group in all_groups:
        if group.status == GroupStatus.VERIFIED:
            agree_groups.append(group)
        elif group.status == GroupStatus.IN_PROGRESS:
            in_progress_groups.append(group)
        elif group.status == GroupStatus.UNVERIFIED:
            disagree_groups.append(group)

    def creator_of(group: Group) -> dict | None:
        creator = group.creator
        if creator is None:
            return None
        return {"user_id": creator.user_id, "campus_id": creator.campus_id, "name": creator.name}

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        agree_groups=[
            {
                "group_id": ag.group_id,
                "title": ag.title,
                "desc": ag.desc,
                "begin": ag.begin,
                "end": ag.end,
                "creator": creator_of(ag)
            }
            for ag in agree_groups
        ],
        in_progress_groups=[
            {
                "group_id": ipg.group_id,
                "title": ipg.title,
                "desc": ipg.desc,
                "begin": ipg.begin,
                "end": ipg.end,
                "creator": creator_of(ipg)
            }
            for ipg in in_progress_groups
        ],
        disagree_groups=[
            {
                "group_id": dg.group_id,
                "title": dg.title,
                "desc": dg.desc,
                "begin": dg.begin,
                "end": dg.end,
                "reason": dg.reason,
                "creator": creator_of(dg)
            }
            for dg in disagree_groups
        ],
    )


@router.get("/one_group/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def show_one_group(request: Request, GroupId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    admin_id = payload["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    # 管理員可以看任何狀態的群組
    group = db.query(Group).filter(Group.group_id == GroupId, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    group_leaders, group_members = get_group_members(db, GroupId)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        group_id=group.group_id,
        title=group.title,
        desc=group.desc,
        begin=group.begin,
        end=group.end,
        status=group.status.value,
        reason=group.reason,
        group_leaders=group_leaders,
        group_members=group_members,
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
    user = db.query(Account).filter(Account.user_id == UserId, Account.role == Role.NORMAL, Account.is_delete == False).first()
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
    user.role = Role.NORMAL
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
                                    or_(Account.role == Role.NORMAL, Account.role == Role.DB_EDITOR), Account.is_delete == False).first()
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
    user.role = Role.NORMAL
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
    users = db.query(Account).filter(or_(Account.campus_id.ilike(f"%{Search}%"), Account.name.ilike(f"%{Search}%")), Account.is_delete == False).all()

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