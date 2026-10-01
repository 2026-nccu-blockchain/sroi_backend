from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.model import FormStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class StakeholderInput(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="", max_length=100)
    email: Optional[EmailStr] = None
    notes: str = ""


class StakeholderRead(ORMModel):
    stakeholder_id: str
    name: str
    role: str
    email: Optional[str]
    notes: str
    position: int


class LinkedFormRead(ORMModel):
    form_id: str
    title: Optional[str]
    status: FormStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    organization: str = Field(default="", max_length=255)
    description: str = ""
    year: int = Field(ge=1900, le=2200)
    status: Literal["draft", "published"] = "draft"
    linked_form_id: Optional[str] = None
    stakeholders: list[StakeholderInput] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    organization: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    year: Optional[int] = Field(default=None, ge=1900, le=2200)
    status: Optional[Literal["draft", "published"]] = None
    linked_form_id: Optional[str] = None
    stakeholders: Optional[list[StakeholderInput]] = None


class ProjectRead(ORMModel):
    project_id: str
    owner_id: str
    name: str
    organization: str
    description: str
    year: int
    status: str
    linked_form_id: Optional[str]
    linked_form: Optional[LinkedFormRead]
    stakeholders: list[StakeholderRead] = Field(default_factory=list)
    create_time: Optional[datetime]
    update_time: Optional[datetime]
