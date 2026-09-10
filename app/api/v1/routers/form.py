from datetime import datetime, timedelta, timezone

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session
from sqlalchemy.orm import selectinload, with_loader_criteria

from app.core.deps import return_payload
from app.core.exceptions import APIException
from app.db.session import get_db
from app.models.model import (
    Answer,
    AnswerChoice,
    Form,
    FormResponse,
    FormStatus,
    Page,
    Question,
    QuestionOption,
    QuestionType,
    ResponseStatus,
)
from app.schemas.form import (
    AnswerRead,
    FormCreate,
    FormRead,
    FormResponseCreate,
    FormResponseRead,
    FormStructureSave,
    FormUpdate,
    PageCreate,
    PageRead,
    QuestionCreate,
    QuestionRead,
    QuestionUpdate,
)

router = APIRouter()


def _user_id(payload: dict) -> str:
    user_id = payload.get("id")
    if not user_id:
        raise APIException(401, "10005", "Invalid token payload")
    return str(user_id)


def _owned_form(db: Session, form_id: str, user_id: str) -> Form:
    form = db.query(Form).filter(
        Form.form_id == form_id,
        Form.author_id == user_id,
        Form.is_delete.is_(False),
    ).first()
    if form is None:
        raise APIException(404, "20001", "Form not found")
    return form


def _form_query(db: Session):
    return db.query(Form).options(
        selectinload(Form.pages).selectinload(Page.questions).selectinload(Question.options),
        with_loader_criteria(Page, Page.is_delete.is_(False)),
        with_loader_criteria(Question, Question.is_delete.is_(False)),
        with_loader_criteria(QuestionOption, QuestionOption.is_delete.is_(False)),
    )


def _public_form_query(db: Session):
    return db.query(Form).options(
        selectinload(Form.pages).selectinload(Page.questions).selectinload(Question.options),
        with_loader_criteria(Page, Page.is_delete.is_(False)),
        with_loader_criteria(
            Question,
            Question.is_delete.is_(False) & Question.is_temp.is_(False),
        ),
        with_loader_criteria(QuestionOption, QuestionOption.is_delete.is_(False)),
    )


def _cleanup_expired_temporary_questions(db: Session) -> int:
    cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
    expired = db.query(Question).filter(
        Question.is_temp.is_(True),
        Question.create_time < cutoff,
    ).all()
    for question in expired:
        db.delete(question)
    if expired:
        db.commit()
    return len(expired)


def _add_question(
    form: Form,
    page: Page,
    data: QuestionCreate,
    *,
    is_temp: bool = False,
) -> Question:
    question = Question(
        form=form,
        page=page,
        question_type=data.question_type,
        title=data.title,
        content=data.content,
        is_required=data.is_required,
        position=data.position,
        scale_begin=data.scale_begin,
        scale_end=data.scale_end,
        is_multiple=data.is_multiple,
        jump_rules=data.jump_rules,
        is_temp=is_temp,
    )
    for index, option in enumerate(data.options):
        question.options.append(QuestionOption(
            label=option.label,
            value=option.value or option.label,
            position=option.position if option.position is not None else index,
        ))
    return question


def _link_questions(questions: list[Question]) -> None:
    for index, question in enumerate(questions):
        question.pre_id = questions[index - 1].question_id if index > 0 else None
        question.next_id = questions[index + 1].question_id if index + 1 < len(questions) else None


@router.post("", response_model=FormRead, status_code=status.HTTP_201_CREATED)
def create_form(
    data: FormCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Form:
    form = Form(
        author_id=_user_id(payload),
        title=data.title,
        content=data.content,
        status=data.status,
    )
    for page_data in data.pages:
        page = Page(
            title=page_data.title,
            content=page_data.content,
            position=page_data.position,
        )
        form.pages.append(page)
        for question_data in page_data.questions:
            _add_question(form, page, question_data)

    db.add(form)
    db.flush()
    ordered_questions = [
        question
        for page in sorted(form.pages, key=lambda item: item.position)
        for question in sorted(page.questions, key=lambda item: item.position)
    ]
    _link_questions(ordered_questions)
    db.commit()
    return _form_query(db).filter(Form.form_id == form.form_id).one()


@router.get("", response_model=list[FormRead])
def list_forms(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[Form]:
    _cleanup_expired_temporary_questions(db)
    return _form_query(db).filter(
        Form.author_id == _user_id(payload),
        Form.is_delete.is_(False),
    ).order_by(Form.create_time.desc()).all()


@router.get("/{form_id}", response_model=FormRead)
def get_form(
    form_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Form:
    _cleanup_expired_temporary_questions(db)
    _owned_form(db, form_id, _user_id(payload))
    return _form_query(db).filter(Form.form_id == form_id).one()


@router.get("/{form_id}/public", response_model=FormRead)
def get_published_form(form_id: str, db: Session = Depends(get_db)) -> Form:
    form = _public_form_query(db).filter(
        Form.form_id == form_id,
        Form.status == FormStatus.PUBLISHED,
        Form.is_delete.is_(False),
    ).first()
    if form is None:
        raise APIException(404, "20001", "Published form not found")
    return form


@router.patch("/{form_id}", response_model=FormRead)
def update_form(
    form_id: str,
    data: FormUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Form:
    form = _owned_form(db, form_id, _user_id(payload))
    for field, value in data.model_dump(exclude_unset=True).items():
        setattr(form, field, value)
    db.commit()
    return _form_query(db).filter(Form.form_id == form_id).one()


@router.put("/{form_id}/structure", response_model=FormRead)
def save_form_structure(
    form_id: str,
    data: FormStructureSave,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Form:
    """Finalize temporary questions and build the default linked-list order."""
    form = _owned_form(db, form_id, _user_id(payload))
    active_pages = db.query(Page).filter(
        Page.form_id == form_id,
        Page.is_delete.is_(False),
    ).all()
    page_map = {page.page_id: page for page in active_pages}
    submitted_page_ids = [item.page_id for item in data.pages]
    if len(set(submitted_page_ids)) != len(submitted_page_ids):
        raise APIException(400, "20020", "Duplicate page in form structure")
    if set(submitted_page_ids) != set(page_map):
        raise APIException(400, "20021", "Form structure must contain every active page")

    active_questions = db.query(Question).filter(
        Question.form_id == form_id,
        Question.is_delete.is_(False),
    ).all()
    question_map = {question.question_id: question for question in active_questions}
    ordered_questions: list[Question] = []
    seen_question_ids: set[str] = set()

    for page_position, page_data in enumerate(data.pages):
        page = page_map[page_data.page_id]
        page.position = page_position
        for question_position, question_id in enumerate(page_data.question_ids):
            if question_id in seen_question_ids:
                raise APIException(400, "20022", "Duplicate question in form structure")
            question = question_map.get(question_id)
            if question is None:
                raise APIException(400, "20023", "Question does not belong to this form")
            seen_question_ids.add(question_id)
            question.page = page
            question.position = question_position
            question.is_temp = False
            ordered_questions.append(question)

    saved_question_ids = {
        question.question_id for question in active_questions if not question.is_temp
    }
    if not saved_question_ids.issubset(seen_question_ids):
        raise APIException(400, "20024", "Saved questions cannot be omitted from form structure")

    _link_questions(ordered_questions)

    db.commit()
    return _form_query(db).filter(Form.form_id == form.form_id).one()


@router.delete("/{form_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_form(
    form_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> None:
    form = _owned_form(db, form_id, _user_id(payload))
    form.is_delete = True
    db.commit()


@router.post("/{form_id}/pages", response_model=PageRead, status_code=status.HTTP_201_CREATED)
def create_page(
    form_id: str,
    data: PageCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Page:
    form = _owned_form(db, form_id, _user_id(payload))
    page = Page(form=form, title=data.title, content=data.content, position=data.position)
    for question_data in data.questions:
        _add_question(form, page, question_data)
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


@router.post("/{form_id}/pages/{page_id}/questions", response_model=QuestionRead, status_code=status.HTTP_201_CREATED)
def create_question(
    form_id: str,
    page_id: str,
    data: QuestionCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Question:
    _cleanup_expired_temporary_questions(db)
    form = _owned_form(db, form_id, _user_id(payload))
    page = db.query(Page).filter(
        Page.page_id == page_id,
        Page.form_id == form_id,
        Page.is_delete.is_(False),
    ).first()
    if page is None:
        raise APIException(404, "20002", "Page not found")
    question = _add_question(form, page, data, is_temp=True)
    db.add(question)
    db.commit()
    db.refresh(question)
    return question


@router.patch("/questions/{question_id}", response_model=QuestionRead)
def update_question(
    question_id: str,
    data: QuestionUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Question:
    question = db.query(Question).options(selectinload(Question.options)).join(Form).filter(
        Question.question_id == question_id,
        Question.is_delete.is_(False),
        Form.author_id == _user_id(payload),
        Form.is_delete.is_(False),
    ).first()
    if question is None:
        raise APIException(404, "20003", "Question not found")

    changes = data.model_dump(exclude_unset=True)
    option_data = changes.pop("options", None)
    for field, value in changes.items():
        setattr(question, field, value)
    if question.question_type == QuestionType.DS:
        question.is_required = False
    if question.question_type == QuestionType.SC:
        if question.scale_begin is None or question.scale_end is None:
            raise APIException(400, "20016", "Scale question requires scale_begin and scale_end")
        if question.scale_begin >= question.scale_end:
            raise APIException(400, "20017", "scale_begin must be smaller than scale_end")
    if question.question_type != QuestionType.CQ:
        for option in question.options:
            option.is_delete = True
        question.is_multiple = False
    if option_data is not None and question.question_type == QuestionType.CQ:
        existing_options = {option.option_id: option for option in question.options}
        retained_ids: set[str] = set()
        for index, option in enumerate(option_data):
            option_id = option.get("option_id")
            existing = existing_options.get(option_id) if option_id else None
            if existing:
                existing.label = option["label"]
                existing.value = option.get("value") or option["label"]
                existing.position = option.get("position") if option.get("position") is not None else index
                existing.is_delete = False
                retained_ids.add(existing.option_id)
            else:
                question.options.append(QuestionOption(
                    label=option["label"],
                    value=option.get("value") or option["label"],
                    position=option.get("position") if option.get("position") is not None else index,
                ))
        for option_id, existing in existing_options.items():
            if option_id not in retained_ids:
                existing.is_delete = True
    active_option_count = sum(not option.is_delete for option in question.options)
    if question.question_type == QuestionType.CQ and active_option_count < 1:
        raise APIException(400, "20018", "Choice question requires at least one option")
    db.commit()
    db.refresh(question)
    return question


@router.delete("/questions/{question_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_question(
    question_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> None:
    question = db.query(Question).join(Form).filter(
        Question.question_id == question_id,
        Form.author_id == _user_id(payload),
        Question.is_delete.is_(False),
    ).first()
    if question is None:
        raise APIException(404, "20003", "Question not found")
    question.is_delete = True
    db.commit()


def _has_answer(answer, question: Question) -> bool:
    if question.question_type == QuestionType.OQ:
        return bool(answer.text_value and answer.text_value.strip())
    if question.question_type == QuestionType.SC:
        return answer.number_value is not None
    if question.question_type == QuestionType.DT:
        return answer.date_value is not None
    if question.question_type == QuestionType.CQ:
        return bool(answer.option_ids)
    return False


def _serialize_response(response: FormResponse) -> FormResponseRead:
    return FormResponseRead(
        response_id=response.response_id,
        form_id=response.form_id,
        respondent_email=response.respondent_email,
        status=response.status,
        started_at=response.started_at,
        submitted_at=response.submitted_at,
        answers=[AnswerRead(
            answer_id=answer.answer_id,
            question_id=answer.question_id,
            content=answer.content,
            number_value=answer.number_value,
            date_value=answer.date_value,
            option_ids=[choice.option_id for choice in answer.selected_options],
        ) for answer in response.answers],
    )


@router.post("/{form_id}/responses", response_model=FormResponseRead, status_code=status.HTTP_201_CREATED)
def submit_response(
    form_id: str,
    data: FormResponseCreate,
    db: Session = Depends(get_db),
) -> FormResponseRead:
    form = db.query(Form).options(
        selectinload(Form.questions).selectinload(Question.options)
    ).filter(
        Form.form_id == form_id,
        Form.status == FormStatus.PUBLISHED,
        Form.is_delete.is_(False),
    ).first()
    if form is None:
        raise APIException(404, "20001", "Published form not found")

    submitted = {item.question_id: item for item in data.answers}
    if len(submitted) != len(data.answers):
        raise APIException(400, "20010", "Duplicate question answer")

    questions = {
        question.question_id: question
        for question in form.questions
        if not question.is_delete and not question.is_temp and question.question_type != QuestionType.DS
    }
    unknown_ids = set(submitted) - set(questions)
    if unknown_ids:
        raise APIException(400, "20011", "Answer contains a question outside this form")

    for question in questions.values():
        answer = submitted.get(question.question_id)
        if question.is_required and (answer is None or not _has_answer(answer, question)):
            raise APIException(400, "20012", f"Required question is missing: {question.question_id}")
        if answer is None:
            continue
        if question.question_type == QuestionType.SC and answer.number_value is not None:
            if not question.scale_begin <= answer.number_value <= question.scale_end:
                raise APIException(400, "20013", "Scale answer is outside the allowed range")
        if question.question_type == QuestionType.CQ:
            allowed = {option.option_id for option in question.options if not option.is_delete}
            if not set(answer.option_ids).issubset(allowed):
                raise APIException(400, "20014", "Invalid choice option")
            if not question.is_multiple and len(answer.option_ids) > 1:
                raise APIException(400, "20015", "This question only allows one option")

    response = FormResponse(
        form=form,
        respondent_email=str(data.respondent_email) if data.respondent_email else None,
        status=ResponseStatus.SUBMITTED,
        submitted_at=datetime.now(timezone.utc),
    )
    for question_id, submitted_answer in submitted.items():
        question = questions[question_id]
        answer = Answer(
            form=form,
            response=response,
            form_id=form.form_id,
            page_id=question.page_id,
            question=question,
            content=submitted_answer.text_value if question.question_type == QuestionType.OQ else None,
            number_value=submitted_answer.number_value if question.question_type == QuestionType.SC else None,
            date_value=submitted_answer.date_value if question.question_type == QuestionType.DT else None,
            email=response.respondent_email,
        )
        for option_id in submitted_answer.option_ids:
            answer.selected_options.append(AnswerChoice(option_id=option_id))
        response.answers.append(answer)

    db.add(response)
    db.commit()
    response = db.query(FormResponse).options(
        selectinload(FormResponse.answers).selectinload(Answer.selected_options)
    ).filter(FormResponse.response_id == response.response_id).one()
    return _serialize_response(response)


@router.get("/{form_id}/responses", response_model=list[FormResponseRead])
def list_responses(
    form_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[FormResponseRead]:
    _owned_form(db, form_id, _user_id(payload))
    responses = db.query(FormResponse).options(
        selectinload(FormResponse.answers).selectinload(Answer.selected_options)
    ).filter(FormResponse.form_id == form_id).order_by(FormResponse.submitted_at.desc()).all()
    return [_serialize_response(response) for response in responses]
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
