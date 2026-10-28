from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import GroupRole, GroupStatus, Account, VerifiedInProgress, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.schemas.user import (
    CampusIdChangeRequest,
    AddGroupRequest,
)

router = APIRouter()

@router.post("/change_campus_id", response_model=APIResponse, response_model_exclude_none=True)
def change_campus_id(request: Request, data: CampusIdChangeRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    if Account.campus_id_taken(db, data.campus_id):
        raise APIException(400, "10012", "the same campus id")
    user = db.query(Account).filter(Account.user_id == user_id, Account.is_delete == False).first()
    if user is None:
        raise APIException(404, "10001", "user not found")
    # 同一時間只保留一筆待審核的變更申請，新的取代舊的
    db.query(VerifiedInProgress).filter(
        VerifiedInProgress.user_id == user_id,
        VerifiedInProgress.is_delete == False,
    ).update({VerifiedInProgress.is_delete: True}, synchronize_session=False)
    new_ver = VerifiedInProgress(
        campus_id=data.campus_id,
        user_id=user_id,
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
    new_group = Group(
        title=data.title,
        desc=data.desc,
        begin=data.begin,
        end=data.end,
        status=GroupStatus.IN_PROGRESS,
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


@router.get("/my_group", response_model=APIResponse, response_model_exclude_none=True)
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
    if user is None:
        raise APIException(404, "10001", "user not found")

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        user_id=user.user_id,
        campus_id=user.campus_id,
        email=user.email,
        name=user.name,
        role=user.role.value
    )