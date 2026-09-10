from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from app.db.session import get_db
from app.models.model import Role, Account, VerifiedInProgress, Group, GroupAccount
from app.core.exceptions import APIException
from app.schemas.common import APIResponse
from datetime import datetime, timedelta
from app.core.deps import verify_token, return_payload
from app.schemas.group import (
    InviteRequest
)
import re

router = APIRouter()


@router.post("/invite/{GroupId}", response_model=APIResponse, response_model_exclude_none=True)
def invite_group(request: Request, GroupId: str, data: InviteRequest, db: Session = Depends(get_db)) -> dict:
    verify_token(request)
    payload = return_payload(request)
    user_id = payload["user_id"]
    group = db.query(Group).filter(Group.group_id == GroupId, Group.status == Role.VERIFIED, Group.is_delete == False).first()
    if group is None:
        raise APIException(404, "10013", "group not found")
    invited_user = db.query(Account).filter(Account.campus_id == data.campus_id, Account.role != Role.UNVERIFIED, 
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
    if data.is_leader:
        group.leader_list = (group.leader_list or []) + [f"{invited_user.user_id}"]
        invited_user.group_list = (invited_user.group_list or []) + [f"{group.group_id}"]
        new_GA = GroupAccount(
            group_id=group.group_id,
            user_id=invited_user.user_id,
            group_role=Role.LEADER
        )
        db.add(new_GA)
    else:
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