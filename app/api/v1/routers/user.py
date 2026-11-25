from fastapi import APIRouter, Request, Depends, File, UploadFile
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import GroupRole, GroupStatus, Account, EnrollmentStatus, EnrollmentVerification, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta, timezone
from app.core.deps import require_enrollment_access, verify_token, return_payload
from app.api.services.enrollment import UPLOADABLE_STATES, enrollment_state, serialize_enrollment
from app.api.services.external_accounts import account_extra, is_external_expired
from app.api.services.enrollment_files import detect_enrollment_type, read_enrollment_file, save_enrollment_file
from app.schemas.user import (
    AddGroupRequest,
)

router = APIRouter()

# user 路由的個人資料與驗證 API 要讓需要驗證的學生使用，所以只在群組相關的 API 個別擋下
@router.post("/add_group", response_model=APIResponse, response_model_exclude_none=True, dependencies=[Depends(require_enrollment_access)])
def add_group(request: Request, data: AddGroupRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    new_group = Group(
        title=data.title,
        desc=data.desc,
        begin=data.begin,
        end=data.end,
        status=GroupStatus.IN_PROGRESS,
        created_by=user_id,
    )
    db.add(new_group)
    db.flush()
    # 申請人直接成為組長；權限判斷只採計 VERIFIED 群組，審核通過前不會生效
    db.add(GroupAccount(
        group_id=new_group.group_id,
        user_id=user_id,
        group_role=GroupRole.LEADER
    ))
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.get("/my_group", response_model=APIResponse, response_model_exclude_none=True, dependencies=[Depends(require_enrollment_access)])
def my_group(request: Request, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    groups = db.query(Group).join(GroupAccount, GroupAccount.group_id == Group.group_id).filter(
        GroupAccount.user_id == user_id,
        GroupAccount.is_delete == False,
        Group.is_delete == False,
    ).all()
    verified_group = []
    in_progress_group = []
    unverified_group = []
    for group in groups:
        if group.status == GroupStatus.VERIFIED:
            verified_group.append(group)
        elif group.status == GroupStatus.IN_PROGRESS:
            in_progress_group.append(group)
        elif group.status == GroupStatus.UNVERIFIED:
            unverified_group.append(group)

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        verified_groups=[
            {
                "group_id": vg.group_id,
                "title": vg.title,
                "desc": vg.desc,
                "begin": vg.begin,
                "end": vg.end
            }
            for vg in verified_group
        ],
        in_progress_groups=[
            {
                "group_id": ipg.group_id,
                "title": ipg.title,
                "desc": ipg.desc,
                "begin": ipg.begin,
                "end": ipg.end
            }
            for ipg in in_progress_group
        ],
        unverified_groups=[
            {
                "group_id": uvg.group_id,
                "title": uvg.title,
                "desc": uvg.desc,
                "begin": uvg.begin,
                "end": uvg.end,
                "reason": uvg.reason
            }
            for uvg in unverified_group
        ],
    )


@router.get("/profile", response_model=APIResponse, response_model_exclude_none=True)
def my_profile(request: Request, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    # 帳號已被停權、刪除，或校外帳號已到期：回 401 讓前端登出，不要停在錯誤畫面
    if user is None or is_external_expired(user):
        raise APIException(401, "10005", "Invalid or expired token")

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        user_id=user.user_id,
        campus_id=user.campus_id,
        email=user.email,
        name=user.name,
        role=user.role.value,
        # 前端用 enrollment.state 決定要不要導到驗證頁
        enrollment=serialize_enrollment(db, user),
        **account_extra(user),
    )


def _current_account(request: Request, db: Session) -> Account:
    verify_token(request)
    user_id = return_payload(request)["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    return user


@router.get("/enrollment", response_model=APIResponse, response_model_exclude_none=True)
def my_enrollment(request: Request, db: Session = Depends(get_db)) -> dict:
    """在學驗證狀態：是不是學生、目前狀態、截止日、最近一次上傳的審核結果"""
    user = _current_account(request, db)
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        enrollment=serialize_enrollment(db, user),
    )


@router.post("/enrollment/proof", response_model=APIResponse, response_model_exclude_none=True)
async def upload_enrollment_proof(
    request: Request,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    """上傳在學證明：只有驗證期間（需要驗證、被退回、審核中）可以上傳；審核中再上傳會取代舊的"""
    user = _current_account(request, db)
    state, latest = enrollment_state(db, user)
    if state not in UPLOADABLE_STATES:
        raise APIException(400, "10031", "enrollment verification not required now")
    data = await read_enrollment_file(file)
    detected = detect_enrollment_type(data)
    if detected is None:
        raise APIException(400, "10033", "unsupported file type")
    extension, content_type = detected
    if latest is not None and latest.status == EnrollmentStatus.PENDING:
        latest.is_delete = True
    db.add(EnrollmentVerification(
        user_id=user.user_id,
        due_year=user.verify_due_year,
        stored_name=save_enrollment_file(data, extension),
        original_name=(file.filename or f"在學證明{extension}")[:255],
        content_type=content_type,
        size_bytes=len(data),
        # 用程式時間而不是資料庫的 now()：now() 是交易開始時間，同一交易內會相同，排不出哪份最新
        create_time=datetime.now(timezone.utc),
    ))
    db.commit()
    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        enrollment=serialize_enrollment(db, user),
    )

