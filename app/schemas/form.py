from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, Field, model_validator

from app.models.model import FormStatus, QuestionType, ResponseStatus


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True, use_enum_values=True)


class QuestionOptionCreate(BaseModel):
    option_id: Optional[str] = None
    label: str = Field(min_length=1, max_length=255)
    value: Optional[str] = Field(default=None, max_length=255)
    position: Optional[int] = Field(default=None, ge=0)


class QuestionOptionRead(ORMModel):
    option_id: str
    label: str
    value: str
    position: int


class QuestionCreate(BaseModel):
    question_type: QuestionType
    title: Optional[str] = Field(default=None, max_length=255)
    content: str = ""
    is_required: bool = False
    position: int = Field(default=0, ge=0)
    scale_begin: Optional[int] = None
    scale_end: Optional[int] = None
    is_multiple: bool = False
    jump_rules: list[dict[str, str]] = Field(default_factory=list)
    options: list[QuestionOptionCreate] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_question_settings(self):
        if self.question_type == QuestionType.DS:
            self.is_required = False
        if self.question_type == QuestionType.SC:
            if self.scale_begin is None or self.scale_end is None:
                raise ValueError("量表題必須提供 scale_begin 與 scale_end")
            if self.scale_begin >= self.scale_end:
                raise ValueError("scale_begin 必須小於 scale_end")
        if self.question_type == QuestionType.CQ and len(self.options) < 1:
            raise ValueError("選擇題至少需要一個選項")
        if self.question_type != QuestionType.CQ:
            self.options = []
            self.is_multiple = False
        return self


class QuestionUpdate(BaseModel):
    question_type: Optional[QuestionType] = None
    title: Optional[str] = Field(default=None, max_length=255)
    content: Optional[str] = None
    is_required: Optional[bool] = None
    position: Optional[int] = Field(default=None, ge=0)
    scale_begin: Optional[int] = None
    scale_end: Optional[int] = None
    is_multiple: Optional[bool] = None
    jump_rules: Optional[list[dict[str, str]]] = None
    options: Optional[list[QuestionOptionCreate]] = None


class QuestionRead(ORMModel):
    question_id: str
    page_id: str
    question_type: QuestionType
    title: Optional[str]
    content: str
    is_required: bool
    position: int
    scale_begin: Optional[int]
    scale_end: Optional[int]
    is_multiple: bool
    is_temp: bool
    pre_id: Optional[str]
    next_id: Optional[str]
    jump_rules: list[dict[str, str]] = Field(default_factory=list)
    options: list[QuestionOptionRead] = Field(default_factory=list)


class PageCreate(BaseModel):
    title: Optional[str] = Field(default=None, max_length=255)
    content: str = ""
    position: int = Field(default=0, ge=0)
    questions: list[QuestionCreate] = Field(default_factory=list)


class PageRead(ORMModel):
    page_id: str
    title: Optional[str]
    content: str
    position: int
    questions: list[QuestionRead] = Field(default_factory=list)


class FormCreate(BaseModel):
    title: str = Field(min_length=1, max_length=255)
    content: str = ""
    status: FormStatus = FormStatus.DRAFT
    pages: list[PageCreate] = Field(default_factory=lambda: [PageCreate()])


class FormUpdate(BaseModel):
    title: Optional[str] = Field(default=None, min_length=1, max_length=255)
    content: Optional[str] = None
    status: Optional[FormStatus] = None


class PageStructure(BaseModel):
    page_id: str
    question_ids: list[str] = Field(default_factory=list)


class FormStructureSave(BaseModel):
    pages: list[PageStructure] = Field(min_length=1)


class FormRead(ORMModel):
    form_id: str
    public_token: Optional[str]
    author_id: str
    title: Optional[str]
    content: Optional[str]
    status: FormStatus
    create_time: Optional[datetime]
    update_time: Optional[datetime]
    pages: list[PageRead] = Field(default_factory=list)


class PublicFormRead(ORMModel):
    public_token: str
    title: Optional[str]
    content: Optional[str]
    pages: list[PageRead] = Field(default_factory=list)


class AnswerInput(BaseModel):
    question_id: str
    text_value: Optional[str] = None
    number_value: Optional[int] = None
    date_value: Optional[date] = None
    option_ids: list[str] = Field(default_factory=list)


class FormResponseCreate(BaseModel):
    respondent_email: Optional[EmailStr] = None
    answers: list[AnswerInput] = Field(min_length=1)


class AnswerRead(ORMModel):
    answer_id: str
    question_id: str
    content: Optional[str]
    number_value: Optional[int]
    date_value: Optional[date]
    option_ids: list[str] = Field(default_factory=list)


class FormResponseRead(ORMModel):
    response_id: str
    form_id: str
    respondent_email: Optional[str]
    status: ResponseStatus
    started_at: datetime
    submitted_at: Optional[datetime]
    answers: list[AnswerRead] = Field(default_factory=list)
from pydantic import BaseModel
from typing import Optional, List


class AnswerItem(BaseModel):
    question_id: str
    content: Optional[str] = None


class FormAnswerRequest(BaseModel):
    answers: List[AnswerItem]
