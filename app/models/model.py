from sqlalchemy import Column, Integer, String, Text, Date, DateTime, Boolean, ForeignKey, Enum as SQLEnum, UniqueConstraint
from sqlalchemy.dialects.postgresql import ARRAY, JSONB
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from enum import Enum
import uuid
import bcrypt
import re


class Role(Enum):
    ADMIN = "admin"
    DB_EDITOR = "db_editor"
    VERIFIED = "verified"
    IN_PROGRESS = "in_progress"
    UNVERIFIED = "unverified"
    LEADER = "leader"
    MEMBER = "member"

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


class Account(Base):
    __tablename__ = "accounts"

    campus_id = Column(String(36)) # 教職員編號、學號
    user_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False)
    hash_password = Column(String(255), nullable=False)
    name = Column(String(20), nullable=False)
    role = Column(SQLEnum(Role), nullable=False)
    id_card_link = Column(String(255))
    group_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    # forms = relationship("Form", back_populates="author")

    def set_password(self, password: str) -> None:
        salt = bcrypt.gensalt()
        self.hash_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), self.hash_password.encode('utf-8'))

    @staticmethod
    def verify_email(email: str) -> bool:
        email_regex = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        return re.match(email_regex, email) is not None


class VerifiedInProgress(Base):
    __tablename__ = "verified_in_progress"

    uuid  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    is_ver = Column(Boolean, nullable=False) # 是認證還是更改
    campus_id = Column(String(36), nullable=False) # 教職員編號、學號
    user_id = Column(String(36), nullable=False)
    id_card_link = Column(String(255), nullable=False)
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
    status = Column(SQLEnum(Role), nullable=False)
    leader_list = Column(ARRAY(String(255)))
    member_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())


class GroupAccount(Base):
    __tablename__ = "group_account"

    uuid  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    group_id = Column(String(36), nullable=False)
    user_id = Column(String(36), nullable=False)
    group_role = Column(SQLEnum(Role), nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())


class Result(Base):
    __tablename__ = "results"

    result_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    content = Column(String(255), nullable=False)

class Form(Base):
    __tablename__ = "forms"

    form_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    author_id = Column(String(36), ForeignKey("accounts.user_id"), nullable=False)
    title = Column(String(255))
    content = Column(Text)
    status = Column(SQLEnum(FormStatus), nullable=False, default=FormStatus.DRAFT)
    result_id_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    # author = relationship("User", back_populates="forms")
    pages = relationship("Page", back_populates="form", cascade="all, delete-orphan", order_by="Page.position")
    questions = relationship("Question", back_populates="form", order_by="Question.position")
    answers = relationship("Answer", back_populates="form")
    responses = relationship("FormResponse", back_populates="form", cascade="all, delete-orphan")


class Page(Base):
    __tablename__ = "pages"

    page_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    title = Column(String(255))
    content = Column(Text, nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="pages")
    questions = relationship("Question", back_populates="page", cascade="all, delete-orphan", order_by="Question.position")

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
    options = relationship("QuestionOption", back_populates="question", cascade="all, delete-orphan", order_by="QuestionOption.position")


class QuestionOption(Base):
    __tablename__ = "question_options"

    option_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    question_id = Column(String(36), ForeignKey("questions.question_id", ondelete="CASCADE"), nullable=False, index=True)
    label = Column(String(255), nullable=False)
    value = Column(String(255), nullable=False)
    position = Column(Integer, nullable=False, default=0)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    question = relationship("Question", back_populates="options")
    answer_choices = relationship("AnswerChoice", back_populates="option")


class FormResponse(Base):
    __tablename__ = "form_responses"

    response_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id", ondelete="CASCADE"), nullable=False, index=True)
    respondent_email = Column(String(255))
    status = Column(SQLEnum(ResponseStatus), nullable=False, default=ResponseStatus.DRAFT)
    started_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    submitted_at = Column(DateTime(timezone=True))

    form = relationship("Form", back_populates="responses")
    answers = relationship("Answer", back_populates="response", cascade="all, delete-orphan")


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
    selected_options = relationship("AnswerChoice", back_populates="answer", cascade="all, delete-orphan")


class AnswerChoice(Base):
    __tablename__ = "answer_choices"

    answer_id = Column(String(36), ForeignKey("answers.answer_id", ondelete="CASCADE"), primary_key=True)
    option_id = Column(String(36), ForeignKey("question_options.option_id", ondelete="CASCADE"), primary_key=True)

    answer = relationship("Answer", back_populates="selected_options")
    option = relationship("QuestionOption", back_populates="answer_choices")


# class OpenQuestion(Base):
#     __tablename__ = "open_questions"

#     OQ_id = Column(String(36), primary_key=True, index=True, nullable=False)
#     form_id = Column(String(36), ForeignKey("forms.id"), nullable=False)
#     title = Column(String(255), nullable=False)
#     ans_list = Column(ARRAY(String(255)))
#     is_delete = Column(Boolean, nullable=False, default=False)
#     create_time = Column(DateTime(timezone=True), server_default=func.now())
#     update_time = Column(DateTime(timezone=True), onupdate=func.now())


# class ChoiceQuestion(Base):
#     __tablename__ = "choice_questions"

#     CQ_id = Column(String(36), primary_key=True, index=True, nullable=False)
#     form_id = Column(String(36), ForeignKey("forms.id"), nullable=False)
#     title = Column(String(255), nullable=False)
#     options = Column(ARRAY(String(255)))
#     is_multiple = Column(Boolean, nullable=False, default=False)
#     ans_list = Column(ARRAY(String(255)))
#     is_delete = Column(Boolean, nullable=False, default=False)
#     create_time = Column(DateTime(timezone=True), server_default=func.now())
#     update_time = Column(DateTime(timezone=True), onupdate=func.now())


# class Scale(Base):
#     __tablename__ = "scales"

#     SC_id = Column(String(36), primary_key=True, index=True, nullable=False)
#     form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
#     title = Column(String(255), nullable=False)
#     ans_list = Column(ARRAY(String(255)))
#     is_delete = Column(Boolean, nullable=False, default=False)
#     create_time = Column(DateTime(timezone=True), server_default=func.now())
#     update_time = Column(DateTime(timezone=True), onupdate=func.now())


# class DateRecord(Base):
#     __tablename__ = "dates"

#     DT_id = Column(String(36), primary_key=True, index=True, nullable=False)
#     form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
#     title = Column(String(255), nullable=False)
#     ans_list = Column(ARRAY(String(255)))
#     is_delete = Column(Boolean, nullable=False, default=False)
#     create_time = Column(DateTime(timezone=True), server_default=func.now())
#     update_time = Column(DateTime(timezone=True), onupdate=func.now())


# class TextBlock(Base):
#     __tablename__ = "text_blocks"

#     TB_id = Column(String(36), primary_key=True, index=True, nullable=False)
#     form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
#     title = Column(String(255))
#     content = Column(Text)
#     is_delete = Column(Boolean, nullable=False, default=False)
#     create_time = Column(DateTime(timezone=True), server_default=func.now())
#     update_time = Column(DateTime(timezone=True), onupdate=func.now())

#     form = relationship("Form", back_populates="text_blocks")
