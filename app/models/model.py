from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from enum import Enum
import uuid
import bcrypt


class Role(Enum):
    ADMIN = "admin"
    DB_EDITOR = "db_editor"
    NORMAL = "normal"
    NON_AUTH = "non_auth"
    LEADER = "leader"
    MEMBER = "member"

class QuestionType(Enum):
    OQ = "OQ"
    CQ = "CQ"
    SC = "SC"
    DT = "DT"
    DS = "DS"


class Account(Base):
    __tablename__ = "accounts"

    id = Column(String(36), primary_key=True, index=True, nullable=False) # 教職員編號、學號
    uuid = Column(String(36), index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    email = Column(String(255), nullable=False)
    hash_password = Column(String(255), nullable=False)
    name = Column(String(20), nullable=False)
    role = Column(SQLEnum(Role), nullable=False)
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

    
class Group(Base):
    __tablename__ = "groups"

    group_id  = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    title = Column(String(255), nullable=False)
    desc = Column(Text, nullable=False)
    begin = Column(DateTime(timezone=True), nullable=False)
    end = Column(DateTime(timezone=True), nullable=False)
    leader_list = Column(ARRAY(String(255)))
    member_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())


class GroupAccount(Base):
    __tablename__ = "group_account"

    group_id = Column(String(36), primary_key=True, nullable=False)
    account_id = Column(String(36), primary_key=True, nullable=False)
    group_role = Column(SQLEnum(Role), nullable=False)


class Result(Base):
    __tablename__ = "results"

    result_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    content = Column(String(255), nullable=False)

class Form(Base):
    __tablename__ = "forms"

    form_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    author_id = Column(String(36), ForeignKey("accounts.id"), nullable=False)
    title = Column(String(255))
    content = Column(String(255))
    result_id_list = Column(ARRAY(String(255)))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    # author = relationship("User", back_populates="forms")
    pages = relationship("Page", back_populates="form")
    questions = relationship("Question", back_populates="form")
    answers = relationship("Answer", back_populates="form")


class Page(Base):
    __tablename__ = "pages"

    page_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    title = Column(String(255))
    content = Column(Text, nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="pages")
    questions = relationship("Question", back_populates="page")

class Question(Base):
    __tablename__ = "questions"

    question_id = Column(String(36), primary_key=True, index=True, nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    page_id = Column(String(36), ForeignKey("pages.page_id"), nullable=False)
    result_id = Column(String(36))
    title = Column(String(255))
    content = Column(Text, nullable=False)
    scale_begin = Column(Integer)
    scale_end = Column(Integer)
    options = Column(ARRAY(String(255)))
    is_multiple = Column(Boolean, nullable=False, default=False)
    pre_id = Column(String(36))
    next_id = Column(String(36))
    is_temp = Column(Boolean, nullable=False, default=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="questions")
    page = relationship("Page", back_populates="questions")
    answers = relationship("Answer", back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    answer_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    page_id = Column(String(36), ForeignKey("pages.page_id"), nullable=False)
    question_id = Column(String(36), ForeignKey("questions.question_id"), nullable=False)
    content = Column(Text)
    email = Column(String(255), nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="answers")
    question = relationship("Question", back_populates="answers")


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