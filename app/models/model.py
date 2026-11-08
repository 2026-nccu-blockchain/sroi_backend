from sqlalchemy import Column, Integer, Numeric, String, Text, Date, DateTime, Boolean, ForeignKey, Enum as SQLEnum, Index, UniqueConstraint, CheckConstraint, text
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from enum import Enum
from typing import Optional
import uuid
import bcrypt
import re


class Role(Enum):
    ADMIN = "admin"           # 管理員
    DB_EDITOR = "db_editor"   # 資料庫編輯者
    NORMAL = "normal"         # 一般使用者

class GroupStatus(Enum):
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    UNVERIFIED = "unverified"

class GroupRole(Enum):
    LEADER = "leader"   # 組長：管理成員、刪除專案、編輯內容
    EDITOR = "editor"   # 編輯者：建立、編輯專案與表單
    VIEWER = "viewer"   # 檢視者：只能查看

class QuestionType(Enum):
    OQ = "OQ"
    CQ = "CQ"
    SC = "SC"
    DT = "DT"
    DS = "DS"

class FormStatus(Enum):
    DRAFT = "draft"
    PUBLISHED = "published"
    CLOSED = "closed"

class ResponseStatus(Enum):
    DRAFT = "draft"
    SUBMITTED = "submitted"


# email 欄位只存 @ 前面的部分，寄信時才補上網域
EMAIL_DOMAIN = "@nccu.edu.tw"


class Account(Base):
    __tablename__ = "accounts"

    campus_id = Column(String(36)) # 教職員編號、學號
    user_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False)
    hash_password = Column(String(255), nullable=False)
    name = Column(String(20), nullable=False)
    role = Column(SQLEnum(Role), nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    projects = relationship("Project", back_populates="owner", foreign_keys="Project.owner_id")

    def set_password(self, password: str) -> None:
        salt = bcrypt.gensalt()
        self.hash_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), self.hash_password.encode('utf-8'))

    @staticmethod
    def verify_email(email: str) -> bool:
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_regex, email) is not None

    @staticmethod
    def verify_email_prefix(prefix: str) -> bool:
        return re.match(r'^[a-zA-Z0-9._%+-]+$', prefix) is not None

    @property
    def mail_address(self) -> str:
        # 舊資料可能已經是完整 email，就不再補網域
        return self.email if "@" in self.email else self.email + EMAIL_DOMAIN

    @staticmethod
    def campus_id_taken(db, campus_id: str, exclude_user_id: Optional[str] = None) -> bool:
        query = db.query(Account).filter(
            Account.campus_id == campus_id,
            Account.is_delete == False,
        )
        if exclude_user_id is not None:
            query = query.filter(Account.user_id != exclude_user_id)
        return query.first() is not None


class VerifiedCode(Base):
    __tablename__ = "verified_codes"

    uuid = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False, index=True)
    code_hash = Column(String(64), nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    attempts = Column(Integer, nullable=False, default=0)  # 輸入錯誤的次數
    is_verified = Column(Boolean, nullable=False, default=False)
    is_delete = Column(Boolean, nullable=False, default=False)  # 重寄、過期、錯太多次時作廢
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())


class VerifiedInProgress(Base):
    __tablename__ = "verified_in_progress"

    # 學號變更申請
    uuid  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    campus_id = Column(String(36), nullable=False) # 教職員編號、學號
    user_id = Column(String(36), nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    
class Group(Base):
    __tablename__ = "groups"

    group_id  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    desc = Column(Text, nullable=False)
    begin = Column(DateTime(timezone=True), nullable=False)
    end = Column(DateTime(timezone=True), nullable=False)
    status = Column(SQLEnum(GroupStatus), nullable=False)
    reason = Column(Text, nullable=True)
    # 建立（申請）群組的人；舊資料由遷移回填，查不到成員紀錄的舊群組會是空值
    created_by = Column(String(36), ForeignKey("accounts.user_id"), nullable=True, index=True)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    projects = relationship("Project", back_populates="group")
    creator = relationship("Account", foreign_keys=[created_by])


class GroupAccount(Base):
    __tablename__ = "group_account"
    __table_args__ = (
        # 同一個人在同一個群組只能有一筆有效成員資料（軟刪除的不算）
        Index(
            "uq_group_account_active",
            "group_id",
            "user_id",
            unique=True,
            postgresql_where=text("is_delete = false"),
        ),
    )

    uuid  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), ForeignKey("groups.group_id"), nullable=False, index=True)
    user_id = Column(String(36), ForeignKey("accounts.user_id"), nullable=False, index=True)
    group_role = Column(SQLEnum(GroupRole), nullable=False, default=GroupRole.VIEWER)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())


class Form(Base):
    __tablename__ = "forms"

    form_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    public_token = Column(String(32), unique=True, index=True)
    author_id = Column(String(36), ForeignKey("accounts.user_id"), nullable=False)
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=True, index=True)
    title = Column(String(255))
    content = Column(Text)
    status = Column(SQLEnum(FormStatus), nullable=False, default=FormStatus.DRAFT)
    shuffle_outcome_questions = Column(Boolean, nullable=False, default=True, server_default=text("true"))
    result_id_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    # author = relationship("User", back_populates="forms")
    pages = relationship("Page", back_populates="form", order_by="Page.position")
    questions = relationship("Question", back_populates="form", order_by="Question.position")
    answers = relationship("Answer", back_populates="form")

    responses = relationship("FormResponse", back_populates="form")
    project = relationship("Project", back_populates="forms", foreign_keys=[project_id])
    pre_test_stakeholders = relationship(
        "ProjectStakeholder",
        back_populates="pre_form",
        foreign_keys="ProjectStakeholder.pre_form_id",
    )
    post_test_stakeholders = relationship(
        "ProjectStakeholder",
        back_populates="post_form",
        foreign_keys="ProjectStakeholder.post_form_id",
    )


class Project(Base):
    __tablename__ = "projects"
    __table_args__ = (
        # 個人專案只有 owner_id，群組專案只有 group_id
        CheckConstraint(
            "(owner_id IS NOT NULL AND group_id IS NULL) OR (owner_id IS NULL AND group_id IS NOT NULL)",
            name="ck_project_single_owner",
        ),
    )

    project_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    owner_id = Column(String(36), ForeignKey("accounts.user_id"), nullable=True, index=True)  # 個人專案擁有者
    group_id = Column(String(36), ForeignKey("groups.group_id"), nullable=True, index=True)  # 群組專案擁有者
    created_by = Column(String(36), ForeignKey("accounts.user_id"), nullable=False)
    name = Column(String(255), nullable=False)
    organization = Column(String(255), nullable=False, default="")
    description = Column(Text, nullable=False, default="")
    actual_input_cost = Column(Numeric(14, 2), nullable=False, default=0)
    begin = Column(DateTime(timezone=True), nullable=False)
    end = Column(DateTime(timezone=True), nullable=False)
    sroi_discount_rate = Column(Numeric(5, 4), nullable=False, default=0.035, server_default="0.035")
    status = Column(String(20), nullable=False, default="draft")
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    owner = relationship("Account", back_populates="projects", foreign_keys=[owner_id])
    group = relationship("Group", back_populates="projects")
    creator = relationship("Account", foreign_keys=[created_by])
    forms = relationship(
        "Form",
        back_populates="project",
        foreign_keys="Form.project_id",
        order_by="Form.create_time.desc()",
    )
    costs = relationship(
        "ProjectCost",
        back_populates="project",
        order_by="ProjectCost.position",
    )
    stakeholders = relationship(
        "ProjectStakeholder",
        back_populates="project",
        order_by="ProjectStakeholder.position",
    )
    outcomes = relationship(
        "ProjectOutcome",
        back_populates="project",
        order_by="ProjectOutcome.position",
    )
    interview_files = relationship(
        "ProjectInterviewFile",
        back_populates="project",
        order_by="ProjectInterviewFile.create_time",
    )
    outcome_valuations = relationship("ProjectOutcomeValuation", back_populates="project")

    @property
    def is_personal(self) -> bool:
        return self.group_id is None


class ProjectCost(Base):
    __tablename__ = "project_costs"

    cost_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    # 所屬利害關係人；舊資料或專案沒有利害關係人時為 NULL
    stakeholder_id = Column(String(36), ForeignKey("project_stakeholders.stakeholder_id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)  # 項目
    price = Column(Numeric(14, 2), nullable=False, default=0)  # 單價
    quantity = Column(Integer, nullable=False, default=1, server_default="1")  # 個數
    funding_source = Column(String(255), nullable=False, default="", server_default="")  # 經費來源
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="costs")
    stakeholder = relationship("ProjectStakeholder", back_populates="costs")


class ProjectStakeholder(Base):
    __tablename__ = "project_stakeholders"

    stakeholder_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    name = Column(String(255), nullable=False)
    # 已停用：舊的「關係／類型」文字，已搬到 stakeholder_type，API 不再使用
    role = Column(String(100), nullable=False, default="")
    # 關係（影響力／參與度），選「其他」時存自訂文字
    relation = Column(String(100), nullable=False, default="", server_default="")
    # 類型（直接受益者等），選「其他」時存自訂文字
    stakeholder_type = Column(String(100), nullable=False, default="", server_default="")
    notes = Column(Text, nullable=False, default="")
    pre_form_id = Column(String(36), ForeignKey("forms.form_id", ondelete="SET NULL"), nullable=True, index=True)  # 前測表單
    post_form_id = Column(String(36), ForeignKey("forms.form_id", ondelete="SET NULL"), nullable=True, index=True)  # 後測表單
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False, server_default="false")
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="stakeholders")
    pre_form = relationship(
        "Form",
        back_populates="pre_test_stakeholders",
        foreign_keys=[pre_form_id],
    )
    post_form = relationship(
        "Form",
        back_populates="post_test_stakeholders",
        foreign_keys=[post_form_id],
    )
    interview_files = relationship(
        "ProjectInterviewFile",
        back_populates="stakeholder",
        order_by="ProjectInterviewFile.create_time",
    )
    outcome_valuations = relationship("ProjectOutcomeValuation", back_populates="stakeholder")
    outcomes = relationship(
        "ProjectOutcome",
        back_populates="stakeholder",
        order_by="ProjectOutcome.position",
    )
    costs = relationship(
        "ProjectCost",
        back_populates="stakeholder",
        order_by="ProjectCost.position",
    )


class ProjectOutcome(Base):
    __tablename__ = "project_outcomes"

    outcome_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    # 所屬利害關係人；舊資料或專案沒有利害關係人時為 NULL（視為所有利害關係人共用）
    stakeholder_id = Column(String(36), ForeignKey("project_stakeholders.stakeholder_id", ondelete="CASCADE"), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False, server_default="false")
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="outcomes")
    stakeholder = relationship("ProjectStakeholder", back_populates="outcomes")
    form_pages = relationship("Page", back_populates="project_outcome")
    valuations = relationship("ProjectOutcomeValuation", back_populates="outcome")


class ProjectOutcomeValuation(Base):
    __tablename__ = "project_outcome_valuations"
    __table_args__ = (
        UniqueConstraint(
            "stakeholder_id",
            "outcome_id",
            name="uq_project_outcome_valuation_stakeholder_outcome",
        ),
    )

    valuation_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    stakeholder_id = Column(String(36), ForeignKey("project_stakeholders.stakeholder_id", ondelete="CASCADE"), nullable=True, index=True)
    outcome_id = Column(String(36), ForeignKey("project_outcomes.outcome_id", ondelete="CASCADE"), nullable=False, index=True)
    quantity = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    financial_proxy_value = Column(Numeric(14, 2), nullable=False, default=0, server_default="0")
    deadweight_rate = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    attribution_rate = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    displacement_rate = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    duration_years = Column(Integer, nullable=False, default=1, server_default="1")
    dropoff_rate = Column(Numeric(5, 4), nullable=False, default=0, server_default="0")
    is_included = Column(Boolean, nullable=False, default=True, server_default="true")
    is_delete = Column(Boolean, nullable=False, default=False, server_default="false")
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    project = relationship("Project", back_populates="outcome_valuations")
    stakeholder = relationship("ProjectStakeholder", back_populates="outcome_valuations")
    outcome = relationship("ProjectOutcome", back_populates="valuations")


class ProjectInterviewFile(Base):
    __tablename__ = "project_interview_files"

    file_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    project_id = Column(String(36), ForeignKey("projects.project_id", ondelete="CASCADE"), nullable=False, index=True)
    stakeholder_id = Column(String(36), ForeignKey("project_stakeholders.stakeholder_id", ondelete="CASCADE"), nullable=False, index=True)
    original_name = Column(String(255), nullable=False)
    stored_name = Column(String(255), nullable=False, unique=True)
    content_type = Column(String(100), nullable=False)
    size_bytes = Column(Integer, nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False, server_default="false")
    create_time = Column(DateTime(timezone=True), server_default=func.now())

    project = relationship("Project", back_populates="interview_files")
    stakeholder = relationship("ProjectStakeholder", back_populates="interview_files")


class Page(Base):
    __tablename__ = "pages"

    page_id = Column(
        String(36),
        primary_key=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    form_id = Column(
        String(36),
        ForeignKey("forms.form_id"),
        nullable=False,
    )
    project_outcome_id = Column(
        String(36),
        ForeignKey("project_outcomes.outcome_id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    is_respondent_info = Column(Boolean, nullable=False, default=False)
    title = Column(String(255))
    content = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship(
        "Form",
        back_populates="pages",
    )
    project_outcome = relationship("ProjectOutcome", back_populates="form_pages")

    questions = relationship(
        "Question",
        back_populates="page",
        order_by="Question.position",
    )

class Question(Base):
    __tablename__ = "questions"

    question_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    page_id = Column(String(36), ForeignKey("pages.page_id"), nullable=False)
    result_id = Column(String(36))
    title = Column(String(255))
    content = Column(Text, nullable=False)
    is_required = Column(Boolean, nullable=False, default=False)
    position = Column(Integer, nullable=False, default=0)
    scale_begin = Column(Integer)
    scale_end = Column(Integer)
    legacy_options = Column("options", ARRAY(String(255)))
    is_multiple = Column(Boolean, nullable=False, default=False)
    pre_id = Column(String(36))
    next_id = Column(String(36))
    jump_rules = Column(JSONB, nullable=False, default=list)
    is_temp = Column(Boolean, nullable=False, default=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="questions")
    page = relationship("Page", back_populates="questions")
    answers = relationship("Answer", back_populates="question")
    options = relationship("QuestionOption",back_populates="question",order_by="QuestionOption.position")


class QuestionOption(Base):
    __tablename__ = "question_options"

    option_id = Column(
        String(36),
        primary_key=True,
        index=True,
        nullable=False,
        default=lambda: str(uuid.uuid4()),
    )
    question_id = Column(
        String(36),
        ForeignKey("questions.question_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    label = Column(String(255), nullable=False)
    value = Column(String(255), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    question = relationship(
        "Question",
        back_populates="options",
    )

    answer_choices = relationship(
        "AnswerChoice",
        back_populates="option",
    )


class FormResponse(Base):
    __tablename__ = "form_responses"
    __table_args__ = (
        Index(
            "uq_form_response_email",
            "form_id",
            "respondent_email",
            unique=True,
            postgresql_where=text("is_duplicate_legacy = false AND is_delete = false"),
        ),
    )

    response_id = Column(String(36),primary_key=True,index=True,nullable=False,default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36),ForeignKey("forms.form_id", ondelete="CASCADE"),nullable=False,index=True)
    respondent_email = Column(String(255))
    status = Column(SQLEnum(ResponseStatus),nullable=False,default=ResponseStatus.DRAFT)
    started_at = Column(DateTime(timezone=True),server_default=func.now(),nullable=False)
    submitted_at = Column(DateTime(timezone=True))
    is_duplicate_legacy = Column(Boolean, nullable=False, default=False, server_default="false")
    is_delete = Column(Boolean, nullable=False, default=False, server_default="false")
    form = relationship("Form",back_populates="responses")
    answers = relationship("Answer",back_populates="response")

class Answer(Base):
    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("response_id", "question_id", name="uq_response_question_answer"),)

    answer_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    page_id = Column(String(36), ForeignKey("pages.page_id"), nullable=False)
    question_id = Column(String(36), ForeignKey("questions.question_id"), nullable=False)
    response_id = Column(String(36), ForeignKey("form_responses.response_id", ondelete="CASCADE"), nullable=True, index=True)
    content = Column(Text)
    number_value = Column(Integer)
    date_value = Column(Date)
    email = Column(String(255), nullable=True)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="answers")
    question = relationship("Question", back_populates="answers")
    response = relationship("FormResponse", back_populates="answers")
    selected_options = relationship("AnswerChoice", back_populates="answer")


class AnswerChoice(Base):
    __tablename__ = "answer_choices"

    answer_id = Column(String(36), ForeignKey("answers.answer_id", ondelete="CASCADE"), primary_key=True)
    option_id = Column(String(36), ForeignKey("question_options.option_id", ondelete="CASCADE"), primary_key=True)

    answer = relationship("Answer", back_populates="selected_options")
    option = relationship("QuestionOption", back_populates="answer_choices")


class FinancialProxy(Base):
    __tablename__ = "financial_proxies"

    proxy_id = Column(
        String(36),
        primary_key=True,
        default=lambda: str(uuid.uuid4()),
    )

    name = Column(String(255), nullable=False)
    value = Column(Numeric(18, 4), nullable=False)
    note = Column(Text, nullable=False, default="")

    created_by = Column(
        String(36),
        ForeignKey("accounts.user_id"),
        nullable=False,
        index=True,
    )

    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(
        DateTime(timezone=True),
        server_default=func.now(),
    )
