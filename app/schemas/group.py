from pydantic import BaseModel
from datetime import datetime
from typing import Optional
from app.models.model import GroupRole

class InviteRequest(BaseModel):
    user_id: str
    group_role: GroupRole = GroupRole.VIEWER

class ChangeRoleRequest(BaseModel):
    user_id: str
    group_role: Optional[GroupRole] = None
    is_leader: Optional[bool] = None  # 舊版前端相容用，請改用 group_role

    def target_role(self) -> GroupRole | None:
        if self.group_role is not None:
            return self.group_role
        if self.is_leader is not None:
            return GroupRole.LEADER if self.is_leader else GroupRole.EDITOR
        return None

class GroupUpdateRequest(BaseModel):
    title: str
    desc: str
    begin: datetime
    end: datetime