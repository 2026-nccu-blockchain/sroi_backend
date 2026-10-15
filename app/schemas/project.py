from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.model import FormStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class StakeholderInput(BaseModel):
    stakeholder_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=255)
    role: str = Field(default="", max_length=100)
    notes: str = ""
    pre_form_id: Optional[str] = None
    post_form_id: Optional[str] = None

    @model_validator(mode="after")
    def check_forms(self) -> "StakeholderInput":
        if self.pre_form_id and self.pre_form_id == self.post_form_id:
            raise ValueError("前測與後測不可使用同一份表單")
        return self


class OutcomeInput(BaseModel):
    outcome_id: Optional[str] = None
    name: str = Field(min_length=1, max_length=255)


class OutcomeRead(ORMModel):
    outcome_id: str
    name: str
    position: int


class InterviewFileRead(ORMModel):
    file_id: str
    stakeholder_id: str
    original_name: str
    content_type: str
    size_bytes: int
    create_time: Optional[datetime]


class LinkedFormRead(ORMModel):
    form_id: str
    title: Optional[str]
    status: FormStatus


class StakeholderRead(ORMModel):
    stakeholder_id: str
    name: str
    role: str
    notes: str
    position: int
    pre_form_id: Optional[str]
    post_form_id: Optional[str]
    pre_form: Optional[LinkedFormRead]
    post_form: Optional[LinkedFormRead]
    interview_files: list[InterviewFileRead] = Field(default_factory=list)


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    organization: str = Field(default="", max_length=255)
    description: str = ""
    actual_input_cost: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    begin: datetime
    end: datetime
    status: Literal["draft", "published"] = "draft"
    stakeholders: list[StakeholderInput] = Field(default_factory=list)
    outcomes: list[OutcomeInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_period(self) -> "ProjectCreate":
        if self.end < self.begin:
            raise ValueError("結束時間不可早於開始時間")
        return self


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    organization: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    actual_input_cost: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    begin: Optional[datetime] = None
    end: Optional[datetime] = None
    status: Optional[Literal["draft", "published"]] = None
    stakeholders: Optional[list[StakeholderInput]] = None
    outcomes: Optional[list[OutcomeInput]] = None


class ProjectRead(ORMModel):
    project_id: str
    owner_id: str
    name: str
    organization: str
    description: str
    actual_input_cost: Decimal
    begin: datetime
    end: datetime
    status: str
    forms: list[LinkedFormRead] = Field(default_factory=list)
    stakeholders: list[StakeholderRead] = Field(default_factory=list)
    outcomes: list[OutcomeRead] = Field(default_factory=list)
    interview_files: list[InterviewFileRead] = Field(default_factory=list)
    create_time: Optional[datetime]
    update_time: Optional[datetime]
