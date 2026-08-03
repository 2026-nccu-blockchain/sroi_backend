from sqlalchemy import Column, Integer, String, Text, DateTime, Boolean, ForeignKey, Enum as SQLEnum
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base
from enum import Enum
import uuid
import bcrypt


class QuestionType(Enum):
    OQ = "OQ"
    CQ = "CQ"
    SC = "SC"
    DT = "DT"
    DS = "DS"


class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, index=True, nullable=False) # 教職員編號、學號
    email = Column(String(255), nullable=False)
    hash_password = Column(String(255), nullable=False)
    name = Column(String(20), nullable=False)
    role = Column(String(20), nullable=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    forms = relationship("Form", back_populates="author")

    def set_password(self, password: str) -> None:
        salt = bcrypt.gensalt()
        self.hash_password = bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

    def verify_password(self, plain_password: str) -> bool:
        return bcrypt.checkpw(plain_password.encode('utf-8'), self.hash_password.encode('utf-8'))


class Form(Base):
    __tablename__ = "forms"

    form_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    author_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    title = Column(String(255))
    content = Column(String(255))
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    author = relationship("User", back_populates="forms")
    questions = relationship("Question", back_populates="form")
    answers = relationship("Answer", back_populates="form")


class Question(Base):
    __tablename__ = "questions"

    question_id = Column(String(36), primary_key=True, index=True, nullable=False)
    question_type = Column(SQLEnum(QuestionType), nullable=False)
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
    title = Column(String(255))
    content = Column(Text, nullable=False)
    display_order = Column(Integer, nullable=False)
    options = Column(ARRAY(String(255)))
    is_multiple = Column(Boolean, nullable=False, default=False)
    is_delete = Column(Boolean, nullable=False, default=False)
    create_time = Column(DateTime(timezone=True), server_default=func.now())
    update_time = Column(DateTime(timezone=True), onupdate=func.now())

    form = relationship("Form", back_populates="questions")
    answers = relationship("Answer", back_populates="question")


class Answer(Base):
    __tablename__ = "answers"

    answer_id = Column(String(36), primary_key=True, index=True, nullable=False, default=lambda: str(uuid.uuid4()))
    form_id = Column(String(36), ForeignKey("forms.form_id"), nullable=False)
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