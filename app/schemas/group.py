from pydantic import BaseModel, Field, model_validator
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
    title: str = Field(min_length=1, max_length=255)
    desc: str
    begin: datetime
    end: datetime

    @model_validator(mode="after")
    def check_period(self) -> "GroupUpdateRequest":
        if self.end < self.begin:
            raise ValueError("結束時間不可早於開始時間")
        return self