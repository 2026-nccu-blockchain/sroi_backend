from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from sqlalchemy import or_
from app.db.session import get_db
from app.models.model import Role, Account, VerifiedInProgress, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.schemas.group import (
    InviteRequest,
    ChangeRoleRequest
)
import re

router = APIRouter()


@router.post("/invite/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def invite_group(request: Request, GroupId: str, data: InviteRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    invited_user = db.query(Account).filter(Account.user_id == data.user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if invited_user is None:
        raise APIException(404, "10001", "user not found")
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    group_leader = db.query(GroupAccount).filter(GroupAccount.group_id == GroupId, GroupAccount.user_id == user_id, 
                                                 GroupAccount.group_role == Role.LEADER, GroupAccount.is_delete == False).first()
    if user is None or group_leader is None:
        raise APIException(400, "10008", "permission denied")
    if db.query(GroupAccount).filter(GroupAccount.group_id == GroupId, GroupAccount.user_id == invited_user.user_id,
                                      GroupAccount.is_delete == False).first() is not None:
        raise APIException(400, "10014", "group member already exists")
    group.member_list = (group.member_list or []) + [f"{invited_user.user_id}"]
    invited_user.group_list = (invited_user.group_list or []) + [f"{group.group_id}"]
    new_GA = GroupAccount(
        group_id=group.group_id,
        user_id=invited_user.user_id,
        group_role=Role.MEMBER
    )
    db.add(new_GA)
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.post("/change_permission/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def change_permission(request: Request, GroupId: str, data: ChangeRoleRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    change_user = db.query(Account).filter(Account.user_id == data.user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if change_user is None:
        raise APIException(404, "10001", "user not found")
    group_leader = db.query(GroupAccount).filter(GroupAccount.group_id == GroupId, GroupAccount.user_id == user_id, 
                                                 GroupAccount.group_role == Role.LEADER, GroupAccount.is_delete == False).first()
    if group_leader is None:
        raise APIException(400, "10008", "permission denied")
    if group_leader.user_id == change_user.user_id:
        raise APIException(400, "10015", "can't change own permissions")
    change = db.query(GroupAccount).filter(GroupAccount.user_id == data.user_id, GroupAccount.group_id == GroupId, GroupAccount.is_delete == False).first()
    if change is None:
        raise APIException(404, "10001", "user not found")
    if change.group_role == (Role.LEADER if data.is_leader else Role.MEMBER):
        raise APIException(400, "10017", "role unchanged")
    if data.is_leader:
        change.group_role = Role.LEADER
        group.member_list = [
            member for member in group.member_list
            if member != data.user_id
        ]
        group.leader_list = (group.leader_list or []) + [f"{data.user_id}"]

    else:
        change.group_role = Role.MEMBER
        group.leader_list = [
            leader for leader in group.leader_list
            if leader != data.user_id
        ]
        group.member_list = (group.member_list or []) + [f"{data.user_id}"]
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.delete("/group_member", response_model=APIResponse, response_model_exclude_none=True)
def delete_member(request: Request, GroupId: str, UserId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    delete_member = db.query(GroupAccount).filter(GroupAccount.user_id == UserId, GroupAccount.group_id == GroupId, GroupAccount.is_delete == False).first()
    if delete_member is None:
        raise APIException(404, "10001", "user not found")
    group_leader = db.query(GroupAccount).filter(GroupAccount.user_id == user_id, GroupAccount.group_id == GroupId, 
                                                 GroupAccount.group_role == Role.LEADER, GroupAccount.is_delete == False).first()
    if group_leader is None and user.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")
    if delete_member.group_role == Role.LEADER and len(group.leader_list or []) <= 1:
        raise APIException(400, "10016", "at least one leader")
    delete_member.is_delete = True
    if delete_member.group_role == Role.LEADER:
        group.leader_list = [
            leader for leader in group.leader_list
            if leader != UserId
        ]
    else:
        group.member_list = [
            member for member in group.member_list
            if member != UserId
        ]
    user = db.query(Account).filter(Account.user_id == delete_member.user_id, Account.is_delete == False).first()
    user.group_list = [
        group for group in user.group_list
        if group != GroupId
    ]
    db.commit()

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
    )


@router.get("/group_info/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def get_group_info(request: Request, GroupId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    if group.status == Role.VERIFIED:
        member = db.query(GroupAccount).filter(GroupAccount.user_id == user_id, GroupAccount.group_id == GroupId, GroupAccount.is_delete == False).first()
        if member is None:
            raise APIException(400, "10008", "permission denied")
    # 申請中、不同意的群組還沒有 GroupAccount，只有申請人（leader_list）看得到
    elif user_id not in (group.leader_list or []):
        raise APIException(404, "10013", "group not found")
    group_leaders = db.query(Account).filter(Account.user_id.in_(group.leader_list or []), Account.is_delete == False).all()
    group_members = db.query(Account).filter(Account.user_id.in_(group.member_list or []), Account.is_delete == False).all()

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
        group_leaders=[
            {
                "user_id": gl.user_id,
                "campus_id": gl.campus_id,
                "name": gl.name
            }
            for gl in group_leaders
        ],
        group_members=[
            {
                "user_id": gm.user_id,
                "campus_id": gm.campus_id,
                "name": gm.name
            }
            for gm in group_members
        ],
    )


@router.get("/group_role/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def get_group_role(request: Request, GroupId: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    member = db.query(GroupAccount).filter(GroupAccount.user_id == user_id, GroupAccount.group_id == GroupId, GroupAccount.is_delete == False).first()
    if member is None and user.role != Role.ADMIN:
        raise APIException(400, "10008", "permission denied")

    return APIResponse(
        status_code="00000",
        message="success",
        response_datetime=datetime.now(),
        group_role=member.group_role.value
    )


@router.get("/search_user", response_model=APIResponse, response_model_exclude_none=True)
def group_search_user(request: Request, GroupId: str, Search: str, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    user = db.query(Account).filter(Account.user_id == user_id, Account.role != Role.UNVERIFIED, 
                                    Account.role != Role.IN_PROGRESS, Account.is_delete == False).first()
    if user is None:    
        raise APIException(400, "10008", "permission denied")
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    group_leader = db.query(GroupAccount).filter(GroupAccount.user_id == user_id, GroupAccount.group_id == GroupId, 
                                                 GroupAccount.group_role == Role.LEADER, GroupAccount.is_delete == False).first()
    if group_leader is None and user.role != Role.ADMIN:
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