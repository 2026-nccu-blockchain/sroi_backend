from datetime import datetime
from decimal import Decimal
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


class OutcomeInput(BaseModel):
    outcome_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=255)


class OutcomeRead(ORMModel):
    outcome_id: str
    name: str
    position: int


class InterviewFileRead(ORMModel):
    file_id: str
    original_name: str
    content_type: str
    size_bytes: int
    create_time: Optional[datetime]


class LinkedFormRead(ORMModel):
    form_id: str
    title: Optional[str]
    status: FormStatus


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    organization: str = Field(default="", max_length=255)
    description: str = ""
    actual_input_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    year: int = Field(ge=1900, le=2200)
    status: Literal["draft", "published"] = "draft"
    linked_form_id: Optional[str] = None
    stakeholders: list[StakeholderInput] = Field(default_factory=list)
    outcomes: list[OutcomeInput] = Field(default_factory=list)


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    organization: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    actual_input_cost: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    year: Optional[int] = Field(default=None, ge=1900, le=2200)
    status: Optional[Literal["draft", "published"]] = None
    linked_form_id: Optional[str] = None
    stakeholders: Optional[list[StakeholderInput]] = None
    outcomes: Optional[list[OutcomeInput]] = None


class ProjectRead(ORMModel):
    project_id: str
    owner_id: str
    name: str
    organization: str
    description: str
    actual_input_cost: Decimal
    year: int
    status: str
    linked_form_id: Optional[str]
    linked_form: Optional[LinkedFormRead]
    forms: list[LinkedFormRead] = Field(default_factory=list)
    stakeholders: list[StakeholderRead] = Field(default_factory=list)
    outcomes: list[OutcomeRead] = Field(default_factory=list)
    interview_files: list[InterviewFileRead] = Field(default_factory=list)
    create_time: Optional[datetime]
    update_time: Optional[datetime]
