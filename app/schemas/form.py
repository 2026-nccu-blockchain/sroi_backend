from pydantic import BaseModel
from typing import Optional, List


class AnswerItem(BaseModel):
    question_id: str
    content: Optional[str] = None


class FormAnswerRequest(BaseModel):
    answers: List[AnswerItem]