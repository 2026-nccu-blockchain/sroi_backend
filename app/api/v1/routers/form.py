from fastapi import APIRouter, Request, Depends
from sqlalchemy.orm import Session
from datetime import datetime

from app.core.exceptions import APIException
from app.core.deps import return_payload
from app.db.session import get_db
from app.models.model import Account, Form, Question, Answer
from app.schemas.form import FormAnswerRequest


router = APIRouter()


@router.post("/{form_id}/answers")
def submit_form_answers(
    form_id: str,
    data: FormAnswerRequest,
    request: Request,
    db: Session = Depends(get_db),
):
    payload = return_payload(request)

    # TODO: confirm auth.py should store Account.user_id in payload["id"]
    user_id = payload.get("id")

    if not user_id:
        raise APIException(
            401,
            "10005",
            "invalid token payload"
        )

    account = (
        db.query(Account)
        .filter(
            Account.user_id == user_id,
            Account.is_delete == False
        )
        .first()
    )

    if not account:
        raise APIException(
            404,
            "30001",
            "account not found"
        )

    # 確認表單存在
    form = (
        db.query(Form)
        .filter(
            Form.form_id == form_id,
            Form.is_delete == False
        )
        .first()
    )

    if not form:
        raise APIException(
            404,
            "30002",
            "form not found"
        )

    # 不接受空白提交
    if not data.answers:
        raise APIException(
            400,
            "30005",
            "answers cannot be empty"
        )

    # 不接受一次提交中重複出現相同 question_id
    question_ids = [item.question_id for item in data.answers]

    if len(question_ids) != len(set(question_ids)):
        raise APIException(
            400,
            "30006",
            "duplicate question in answers"
        )

    # TODO: confirm whether users can resubmit/edit an answered form
    existing_answer = (
        db.query(Answer)
        .filter(
            Answer.form_id == form_id,
            Answer.email == account.email,
            Answer.is_delete == False
        )
        .first()
    )

    if existing_answer:
        raise APIException(
            400,
            "30003",
            "form already answered"
        )

    try:
        for item in data.answers:
            question = (
                db.query(Question)
                .filter(
                    Question.question_id == item.question_id,
                    Question.form_id == form_id,
                    Question.is_delete == False
                )
                .first()
            )

            if not question:
                raise APIException(
                    404,
                    "30004",
                    f"question {item.question_id} not found"
                )

            answer = Answer(
                form_id=form_id,
                page_id=question.page_id,
                question_id=question.question_id,
                content=item.content,
                email=account.email
            )

            db.add(answer)

        db.commit()

    except APIException:
        db.rollback()
        raise

    except Exception:
        db.rollback()
        raise APIException(
            500,
            "50001",
            "failed to submit form answers"
        )

    return {
        "status_code": "20000",
        "message": "form answered successfully",
        "response_datetime": datetime.now(),
        "form_id": form_id
    }