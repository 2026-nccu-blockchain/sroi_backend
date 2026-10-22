from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.models.model import FormStatus, GroupRole


DEFAULT_PROJECT_NAME = "未命名的專案"


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


class CostCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    price: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    description: str = ""


class CostUpdate(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    price: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=2)
    description: Optional[str] = None


class CostRead(ORMModel):
    cost_id: str
    name: str
    price: Decimal
    description: str
    position: int
    create_time: Optional[datetime]
    update_time: Optional[datetime]


class ProjectCostsRead(BaseModel):
    project_id: str
    costs: list[CostRead]
    total_cost: Decimal


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
    group_id: Optional[str] = None  # 不帶就是個人專案
    name: str = Field(default=DEFAULT_PROJECT_NAME, max_length=255)
    organization: str = Field(default="", max_length=255)
    description: str = ""
    begin: datetime
    end: datetime
    status: Literal["draft", "published"] = "draft"
    stakeholders: list[StakeholderInput] = Field(default_factory=list)
    outcomes: list[OutcomeInput] = Field(default_factory=list)

    @field_validator("name")
    @classmethod
    def default_name(cls, value: str) -> str:
        return value.strip() or DEFAULT_PROJECT_NAME

    @model_validator(mode="after")
    def check_period(self) -> "ProjectCreate":
        if self.end < self.begin:
            raise ValueError("結束時間不可早於開始時間")
        return self


class ProjectUpdate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=255)
    organization: Optional[str] = Field(default=None, max_length=255)
    description: Optional[str] = None
    begin: Optional[datetime] = None
    end: Optional[datetime] = None
    status: Optional[Literal["draft", "published"]] = None
    stakeholders: Optional[list[StakeholderInput]] = None
    outcomes: Optional[list[OutcomeInput]] = None

    # 明確送 null 仍交給 router 擋，只把空白名稱換成預設值
    @field_validator("name")
    @classmethod
    def default_name(cls, value: Optional[str]) -> Optional[str]:
        return None if value is None else value.strip() or DEFAULT_PROJECT_NAME


class ProjectRead(ORMModel):
    project_id: str
    owner_id: Optional[str]
    group_id: Optional[str]
    created_by: str
    my_role: Optional[GroupRole] = None
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
    costs: list[CostRead] = Field(default_factory=list)
    interview_files: list[InterviewFileRead] = Field(default_factory=list)
    create_time: Optional[datetime]
    update_time: Optional[datetime]


class OutcomeValuationInput(BaseModel):
    outcome_id: str
    quantity: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    financial_proxy_value: Decimal = Field(default=Decimal("0"), ge=0, max_digits=14, decimal_places=2)
    deadweight_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=5, decimal_places=4)
    attribution_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=5, decimal_places=4)
    displacement_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=5, decimal_places=4)
    duration_years: int = Field(default=1, ge=1, le=20)
    dropoff_rate: Decimal = Field(default=Decimal("0"), ge=0, le=1, max_digits=5, decimal_places=4)
    is_included: bool = True


class ProjectSROIUpdate(BaseModel):
    discount_rate: Decimal = Field(ge=0, le=1, max_digits=5, decimal_places=4)
    outcomes: list[OutcomeValuationInput] = Field(default_factory=list)

    @model_validator(mode="after")
    def check_unique_outcomes(self) -> "ProjectSROIUpdate":
        outcome_ids = [item.outcome_id for item in self.outcomes]
        if len(outcome_ids) != len(set(outcome_ids)):
            raise ValueError("成果不可重複")
        return self


class OutcomeValuationRead(BaseModel):
    outcome_id: str
    outcome_name: str
    position: int
    quantity: Decimal
    financial_proxy_value: Decimal
    deadweight_rate: Decimal
    attribution_rate: Decimal
    displacement_rate: Decimal
    duration_years: int
    dropoff_rate: Decimal
    is_included: bool
    scale_score: Optional[float]
    scale_answer_count: int
    suggested_eligible: Optional[bool]
    calculated_value: Decimal


class ProjectSROIRead(BaseModel):
    project_id: str
    project_name: str
    actual_input_cost: Decimal
    discount_rate: Decimal
    outcomes: list[OutcomeValuationRead]
    total_social_value: Decimal
    sroi_ratio: Optional[Decimal]
