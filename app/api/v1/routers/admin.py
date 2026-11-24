from fastapi import APIRouter, Request, Depends
from fastapi.responses import FileResponse
from sqlalchemy import or_
from sqlalchemy.orm import Session, selectinload
from app.db.session import get_db
from app.models.model import Role, GroupRole, GroupStatus, Account, EnrollmentStatus, EnrollmentVerification, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.core.permissions import count_group_leaders, get_group_members
from app.schemas.admin import (
    RejectEnrollmentRequest,
    UnconfirmGroupRequest
)
from app.api.services.enrollment import DELETE_REASON_ADMIN, serialize_enrollment, soft_delete_account
from app.api.services.enrollment_files import enrollment_file_path
import re

router = APIRouter()

def require_admin(request: Request, db: Session) -> Account:
    verify_token(request)
    admin_id = return_payload(request)["user_id"]
    admin = db.query(Account).filter(Account.user_id == admin_id, Account.is_delete == False).first()
    if admin is None:
        raise APIException(404, "10001", "user not found")
    if admin.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    return admin


def pending_enrollments(db: Session) -> dict:
    """每位使用者這一期最新一筆審核中的在學證明"""
    rows = db.query(EnrollmentVerification).join(
        Account, Account.user_id == EnrollmentVerification.user_id
    ).filter(
        EnrollmentVerification.status == EnrollmentStatus.PENDING,
        EnrollmentVerification.is_delete == False,
        EnrollmentVerification.due_year == Account.verify_due_year,
        Account.is_delete == False,
    ).order_by(EnrollmentVerification.create_time.asc()).all()
    latest = {}
    for row in rows:
        latest[row.user_id] = row
    return latest


def pending_verification(db: Session, verification_id: str) -> EnrollmentVerification:
    verification = db.query(EnrollmentVerification).filter(
        EnrollmentVerification.verification_id == verification_id,
        EnrollmentVerification.status == EnrollmentStatus.PENDING,
        EnrollmentVerification.is_delete == False,
    ).first()
    if verification is None:
        raise APIException(404, "10034", "verification not found or already reviewed")
    return verification


@router.get("/enrollment_proof/{VerificationId}")
def download_enrollment_proof(request: Request, VerificationId: str, db: Session = Depends(get_db)):
    require_admin(request, db)
    verification = db.query(EnrollmentVerification).filter(
        EnrollmentVerification.verification_id == VerificationId,
        EnrollmentVerification.is_delete == False,
    ).first()
    if verification is None:
        raise APIException(404, "10034", "verification not found")
    path = enrollment_file_path(verification.stored_name)
    if not path.is_file():
        raise APIException(404, "10034", "verification not found")
    # inline：瀏覽器可以直接預覽 PDF 與圖片
    return FileResponse(
        path,
        media_type=verification.content_type,
        filename=verification.original_name,
        content_disposition_type="inline",
    )


@router.post("/approve_enrollment/{VerificationId}", response_model=APIResponse, response_model_exclude_none=True)
def approve_enrollment(request: Request, VerificationId: str, db: Session = Depends(get_db)) -> dict:
    admin = require_admin(request, db)
    verification = pending_verification(db, VerificationId)
    user = db.query(Account).filter(Account.user_id == verification.user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    # 只審這一期的證明；通過就延長一年，下次驗證年 + 1
    if user.verify_due_year != verification.due_year:
        raise APIException(404, "10034", "verification not found or already reviewed")
    verification.status = EnrollmentStatus.APPROVED
    verification.reviewed_by = admin.user_id
    verification.reviewed_at = datetime.now().astimezone()
    user.verify_due_year = verification.due_year + 1
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/reject_enrollment/{VerificationId}", response_model=APIResponse, response_model_exclude_none=True)
def reject_enrollment(request: Request, VerificationId: str, data: RejectEnrollmentRequest, db: Session = Depends(get_db)) -> dict:
    admin = require_admin(request, db)
    verification = pending_verification(db, VerificationId)
    verification.status = EnrollmentStatus.REJECTED
    verification.reason = data.reason
    verification.reviewed_by = admin.user_id
    verification.reviewed_at = datetime.now().astimezone()
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
    # 在學驗證不影響角色，使用者同時也會出現在原本的角色清單
    pending = pending_enrollments(db)
    users_by_id = {user.user_id: user for user in all_user}

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
        enrollment_pending_user=[
            {
                "user_id": user_id,
                "campus_id": users_by_id[user_id].campus_id,
                "name": users_by_id[user_id].name,
                "submitted_at": verification.create_time
            }
            for user_id, verification in pending.items()
            if user_id in users_by_id
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

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        user_id=user.user_id,
        campus_id=user.campus_id,
        name=user.name,
        email=user.email,
        role=user.role.value,
        enrollment=serialize_enrollment(db, user),
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
    # 一併退出所有群組，失去組長的群組自動遞補
    soft_delete_account(db, user, DELETE_REASON_ADMIN)
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