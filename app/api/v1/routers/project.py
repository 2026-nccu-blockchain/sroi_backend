import io
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form as FormField, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload, with_loader_criteria
from starlette.concurrency import run_in_threadpool

from app.core.deps import return_payload
from app.core.exceptions import APIException
from app.db.session import get_db
from app.models.model import (
    Answer,
    Form,
    FormResponse,
    FormStatus,
    Page,
    Project,
    ProjectInterviewFile,
    ProjectOutcome,
    ProjectOutcomeValuation,
    ProjectStakeholder,
    Question,
    QuestionType,
    ResponseStatus,
)
from app.schemas.project import (
    InterviewFileRead,
    OutcomeInput,
    ProjectCreate,
    ProjectRead,
    ProjectSROIRead,
    ProjectSROIUpdate,
    ProjectUpdate,
    StakeholderInput,
)


router = APIRouter()
INTERVIEW_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "interview_guides"
INTERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_INTERVIEW_FILE_SIZE = 10 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024
MONEY_QUANTUM = Decimal("0.01")
RATIO_QUANTUM = Decimal("0.0001")
OUTCOME_ELIGIBILITY_THRESHOLD = Decimal("0.5")


def _user_id(payload: dict) -> str:
    user_id = payload.get("user_id")
    if not user_id:
        raise APIException(401, "10005", "Invalid token payload")
    return str(user_id)


def _project_query(db: Session):
    return db.query(Project).options(
        selectinload(Project.stakeholders).selectinload(ProjectStakeholder.pre_form),
        selectinload(Project.stakeholders).selectinload(ProjectStakeholder.post_form),
        selectinload(Project.stakeholders).selectinload(ProjectStakeholder.interview_files),
        selectinload(Project.outcomes),
        selectinload(Project.interview_files),
        selectinload(Project.forms),
        with_loader_criteria(Form, Form.is_delete.is_(False)),
        with_loader_criteria(ProjectStakeholder, ProjectStakeholder.is_delete.is_(False)),
        with_loader_criteria(ProjectOutcome, ProjectOutcome.is_delete.is_(False)),
        with_loader_criteria(ProjectInterviewFile, ProjectInterviewFile.is_delete.is_(False)),
    )


def _owned_project(db: Session, project_id: str, owner_id: str) -> Project:
    project = _project_query(db).filter(
        Project.project_id == project_id,
        Project.owner_id == owner_id,
        Project.is_delete.is_(False),
    ).first()
    if project is None:
        raise APIException(404, "30001", "Project not found")
    return project


def _decimal(value: object, default: str = "0") -> Decimal:
    if value is None:
        return Decimal(default)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def _outcome_value(
    *,
    quantity: Decimal,
    financial_proxy_value: Decimal,
    deadweight_rate: Decimal,
    attribution_rate: Decimal,
    displacement_rate: Decimal,
    duration_years: int,
    dropoff_rate: Decimal,
    discount_rate: Decimal,
    is_included: bool,
) -> Decimal:
    if not is_included:
        return Decimal("0")
    one = Decimal("1")
    base = (
        quantity
        * financial_proxy_value
        * (one - deadweight_rate)
        * (one - attribution_rate)
        * (one - displacement_rate)
    )
    total = Decimal("0")
    for year in range(duration_years):
        total += base * ((one - dropoff_rate) ** year) / ((one + discount_rate) ** year)
    return total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _outcome_scale_metrics(
    db: Session,
    project_id: str,
    outcome_ids: set[str],
) -> dict[str, tuple[float, int]]:
    if not outcome_ids:
        return {}
    rows = db.query(
        Page.project_outcome_id,
        Answer.number_value,
        Question.scale_begin,
        Question.scale_end,
    ).join(
        Form,
        Form.form_id == Page.form_id,
    ).join(
        Question,
        Question.page_id == Page.page_id,
    ).join(
        Answer,
        Answer.question_id == Question.question_id,
    ).join(
        FormResponse,
        FormResponse.response_id == Answer.response_id,
    ).filter(
        Form.project_id == project_id,
        Form.is_delete.is_(False),
        Page.project_outcome_id.in_(outcome_ids),
        Page.is_delete.is_(False),
        Question.question_type == QuestionType.SC,
        Question.is_temp.is_(False),
        Question.is_delete.is_(False),
        Answer.number_value.is_not(None),
        Answer.is_delete.is_(False),
        FormResponse.status == ResponseStatus.SUBMITTED,
        FormResponse.is_duplicate_legacy.is_(False),
        FormResponse.is_delete.is_(False),
    ).all()

    scores: dict[str, list[Decimal]] = {outcome_id: [] for outcome_id in outcome_ids}
    for outcome_id, number_value, scale_begin, scale_end in rows:
        if outcome_id is None or scale_begin is None or scale_end is None or scale_end <= scale_begin:
            continue
        normalized = (Decimal(number_value) - Decimal(scale_begin)) / Decimal(scale_end - scale_begin)
        scores[outcome_id].append(max(Decimal("0"), min(Decimal("1"), normalized)))

    return {
        outcome_id: (float(sum(values, Decimal("0")) / len(values)), len(values))
        for outcome_id, values in scores.items()
        if values
    }


def _serialize_project_sroi(db: Session, project: Project) -> dict:
    outcomes = sorted(
        (outcome for outcome in project.outcomes if not outcome.is_delete),
        key=lambda outcome: outcome.position,
    )
    outcome_ids = {outcome.outcome_id for outcome in outcomes}
    valuations = {
        valuation.outcome_id: valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project.project_id,
            ProjectOutcomeValuation.outcome_id.in_(outcome_ids) if outcome_ids else False,
            ProjectOutcomeValuation.is_delete.is_(False),
        ).all()
    }
    scale_metrics = _outcome_scale_metrics(db, project.project_id, outcome_ids)
    discount_rate = _decimal(project.sroi_discount_rate, "0.035")
    serialized_outcomes: list[dict] = []
    total_social_value = Decimal("0")
    has_missing_proxy = False

    for outcome in outcomes:
        valuation = valuations.get(outcome.outcome_id)
        quantity = _decimal(valuation.quantity if valuation else None)
        financial_proxy_value = _decimal(valuation.financial_proxy_value if valuation else None)
        deadweight_rate = _decimal(valuation.deadweight_rate if valuation else None)
        attribution_rate = _decimal(valuation.attribution_rate if valuation else None)
        displacement_rate = _decimal(valuation.displacement_rate if valuation else None)
        duration_years = valuation.duration_years if valuation else 1
        dropoff_rate = _decimal(valuation.dropoff_rate if valuation else None)
        is_included = valuation.is_included if valuation else True
        calculated_value = _outcome_value(
            quantity=quantity,
            financial_proxy_value=financial_proxy_value,
            deadweight_rate=deadweight_rate,
            attribution_rate=attribution_rate,
            displacement_rate=displacement_rate,
            duration_years=duration_years,
            dropoff_rate=dropoff_rate,
            discount_rate=discount_rate,
            is_included=is_included,
        )
        total_social_value += calculated_value
        if is_included and financial_proxy_value <= 0:
            has_missing_proxy = True
        metric = scale_metrics.get(outcome.outcome_id)
        scale_score = metric[0] if metric else None
        answer_count = metric[1] if metric else 0
        serialized_outcomes.append({
            "outcome_id": outcome.outcome_id,
            "outcome_name": outcome.name,
            "position": outcome.position,
            "quantity": quantity,
            "financial_proxy_value": financial_proxy_value,
            "deadweight_rate": deadweight_rate,
            "attribution_rate": attribution_rate,
            "displacement_rate": displacement_rate,
            "duration_years": duration_years,
            "dropoff_rate": dropoff_rate,
            "is_included": is_included,
            "scale_score": scale_score,
            "scale_answer_count": answer_count,
            "suggested_eligible": scale_score > float(OUTCOME_ELIGIBILITY_THRESHOLD) if scale_score is not None else None,
            "calculated_value": calculated_value,
        })

    actual_input_cost = _decimal(project.actual_input_cost)
    total_social_value = total_social_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    sroi_ratio = None
    if actual_input_cost > 0 and not has_missing_proxy:
        sroi_ratio = (total_social_value / actual_input_cost).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "actual_input_cost": actual_input_cost,
        "discount_rate": discount_rate,
        "outcomes": serialized_outcomes,
        "total_social_value": total_social_value,
        "sroi_ratio": sroi_ratio,
    }


def _validate_stakeholder_forms(
    db: Session,
    items: list[StakeholderInput],
    owner_id: str,
    project_id: str | None = None,
) -> None:
    """前測、後測表單只能選這個專案底下、未刪除的表單；新建專案時還沒有表單可選。"""
    form_ids = {
        form_id
        for item in items
        for form_id in (item.pre_form_id, item.post_form_id)
        if form_id is not None
    }
    if not form_ids:
        return
    if project_id is None:
        raise APIException(400, "30002", "Linked form does not belong to this project")
    valid_ids = {
        form_id
        for (form_id,) in db.query(Form.form_id).filter(
            Form.form_id.in_(form_ids),
            Form.project_id == project_id,
            Form.author_id == owner_id,
            Form.is_delete.is_(False),
        ).all()
    }
    if valid_ids != form_ids:
        raise APIException(400, "30002", "Linked form does not belong to this project")


def _as_aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _owned_stakeholder(db: Session, project_id: str, stakeholder_id: str) -> ProjectStakeholder:
    stakeholder = db.query(ProjectStakeholder).filter(
        ProjectStakeholder.stakeholder_id == stakeholder_id,
        ProjectStakeholder.project_id == project_id,
        ProjectStakeholder.is_delete.is_(False),
    ).first()
    if stakeholder is None:
        raise APIException(404, "30007", "利害關係人不存在")
    return stakeholder


def _replace_stakeholders(project: Project, items: list[StakeholderInput]) -> None:
    existing = {
        stakeholder.stakeholder_id: stakeholder
        for stakeholder in project.stakeholders
        if not stakeholder.is_delete
    }
    for position, item in enumerate(items):
        stakeholder = existing.pop(item.stakeholder_id, None) if item.stakeholder_id else None
        if stakeholder is None:
            stakeholder = ProjectStakeholder()
            project.stakeholders.append(stakeholder)
        stakeholder.name = item.name
        stakeholder.role = item.role
        stakeholder.notes = item.notes
        stakeholder.pre_form_id = item.pre_form_id
        stakeholder.post_form_id = item.post_form_id
        stakeholder.position = position
    for stakeholder in existing.values():
        stakeholder.is_delete = True
        for record in stakeholder.interview_files:
            record.is_delete = True


def _replace_outcomes(project: Project, items: list[OutcomeInput]) -> None:
    existing = {
        outcome.outcome_id: outcome
        for outcome in project.outcomes
        if not outcome.is_delete
    }
    for position, item in enumerate(items):
        outcome = existing.pop(item.outcome_id, None) if item.outcome_id else None
        if outcome is None:
            outcome = ProjectOutcome()
            project.outcomes.append(outcome)
        outcome.name = item.name.strip()
        outcome.position = position
    for outcome in existing.values():
        outcome.is_delete = True


def _sync_outcomes_to_draft_forms(db: Session, project: Project) -> None:
    """Keep editable forms aligned while treating published forms as snapshots."""
    draft_forms = db.query(Form).filter(
        Form.project_id == project.project_id,
        Form.author_id == project.owner_id,
        Form.status == FormStatus.DRAFT,
        Form.is_delete.is_(False),
    ).all()

    for form in draft_forms:
        pages = db.query(Page).filter(
            Page.form_id == form.form_id,
            Page.is_delete.is_(False),
        ).order_by(Page.position).all()
        pages_by_outcome = {
            page.project_outcome_id: page
            for page in pages
            if page.project_outcome_id is not None
        }

        active_outcomes = sorted(
            (outcome for outcome in project.outcomes if not outcome.is_delete),
            key=lambda outcome: outcome.position,
        )
        ordered_outcome_pages: list[Page] = []
        for outcome in active_outcomes:
            page = pages_by_outcome.get(outcome.outcome_id)
            if page is None:
                page = Page(
                    form_id=form.form_id,
                    project_outcome_id=outcome.outcome_id,
                    title=outcome.name,
                    content="",
                )
                db.add(page)
                pages.append(page)
            else:
                page.title = outcome.name
            ordered_outcome_pages.append(page)

        respondent_pages = [page for page in pages if page.is_respondent_info]
        custom_pages = [
            page for page in pages
            if page not in respondent_pages and page not in ordered_outcome_pages
        ]
        for position, page in enumerate([*respondent_pages, *ordered_outcome_pages, *custom_pages]):
            page.position = position


async def _read_interview_file(upload: UploadFile) -> bytes:
    data = bytearray()
    while chunk := await upload.read(READ_CHUNK_SIZE):
        data += chunk
        if len(data) > MAX_INTERVIEW_FILE_SIZE:
            raise APIException(400, "30005", "訪綱檔案不可超過 10 MB")
    return bytes(data)


def _detect_interview_type(data: bytes) -> tuple[str, str] | None:
    if data.startswith(b"%PDF-"):
        return ".pdf", "application/pdf"
    if data.startswith(b"\xd0\xcf\x11\xe0\xa1\xb1\x1a\xe1"):
        return ".doc", "application/msword"
    if data.startswith(b"PK\x03\x04"):
        try:
            with ZipFile(io.BytesIO(data)) as archive:
                names = set(archive.namelist())
                if "[Content_Types].xml" in names and any(name.startswith("word/") for name in names):
                    return ".docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        except BadZipFile:
            return None
    return None


@router.get("", response_model=list[ProjectRead])
def list_projects(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[Project]:
    return _project_query(db).filter(
        Project.owner_id == _user_id(payload),
        Project.is_delete.is_(False),
    ).order_by(Project.update_time.desc().nullslast(), Project.create_time.desc()).all()


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    owner_id = _user_id(payload)
    _validate_stakeholder_forms(db, data.stakeholders, owner_id)
    project = Project(
        owner_id=owner_id,
        name=data.name,
        organization=data.organization,
        description=data.description,
        actual_input_cost=data.actual_input_cost,
        begin=data.begin,
        end=data.end,
        status=data.status,
    )
    _replace_stakeholders(project, data.stakeholders)
    _replace_outcomes(project, data.outcomes)
    db.add(project)
    db.flush()
    db.commit()
    return _owned_project(db, project.project_id, owner_id)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    return _owned_project(db, project_id, _user_id(payload))


@router.get("/{project_id}/sroi", response_model=ProjectSROIRead)
def get_project_sroi(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    project = _owned_project(db, project_id, _user_id(payload))
    return _serialize_project_sroi(db, project)


@router.put("/{project_id}/sroi", response_model=ProjectSROIRead)
def save_project_sroi(
    project_id: str,
    data: ProjectSROIUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    project = _owned_project(db, project_id, _user_id(payload))
    active_outcome_ids = {
        outcome.outcome_id
        for outcome in project.outcomes
        if not outcome.is_delete
    }
    submitted_outcome_ids = {item.outcome_id for item in data.outcomes}
    if not submitted_outcome_ids.issubset(active_outcome_ids):
        raise APIException(400, "30009", "SROI 成果不屬於此專案")

    project.actual_input_cost = data.actual_input_cost
    project.sroi_discount_rate = data.discount_rate
    existing = {
        valuation.outcome_id: valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project_id,
            ProjectOutcomeValuation.outcome_id.in_(submitted_outcome_ids) if submitted_outcome_ids else False,
        ).all()
    }
    for item in data.outcomes:
        valuation = existing.get(item.outcome_id)
        if valuation is None:
            valuation = ProjectOutcomeValuation(
                project_id=project_id,
                outcome_id=item.outcome_id,
            )
            db.add(valuation)
        valuation.quantity = item.quantity
        valuation.financial_proxy_value = item.financial_proxy_value
        valuation.deadweight_rate = item.deadweight_rate
        valuation.attribution_rate = item.attribution_rate
        valuation.displacement_rate = item.displacement_rate
        valuation.duration_years = item.duration_years
        valuation.dropoff_rate = item.dropoff_rate
        valuation.is_included = item.is_included
        valuation.is_delete = False

    db.commit()
    project = _owned_project(db, project_id, _user_id(payload))
    return _serialize_project_sroi(db, project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    owner_id = _user_id(payload)
    project = _owned_project(db, project_id, owner_id)
    changes = data.model_dump(exclude_unset=True)
    stakeholders = changes.pop("stakeholders", None)
    outcomes = changes.pop("outcomes", None)
    for field, value in changes.items():
        setattr(project, field, value)
    if _as_aware(project.end) < _as_aware(project.begin):
        raise APIException(400, "30008", "結束時間不可早於開始時間")
    if stakeholders is not None:
        stakeholder_items = [StakeholderInput(**item) for item in stakeholders]
        _validate_stakeholder_forms(db, stakeholder_items, owner_id, project_id)
        _replace_stakeholders(project, stakeholder_items)
    if outcomes is not None:
        _replace_outcomes(
            project,
            [OutcomeInput(**item) for item in outcomes],
        )
    db.flush()
    if outcomes is not None:
        _sync_outcomes_to_draft_forms(db, project)
    db.commit()
    return _owned_project(db, project_id, owner_id)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> None:
    project = _owned_project(db, project_id, _user_id(payload))
    project.is_delete = True
    db.commit()


@router.post("/{project_id}/interview-files", response_model=InterviewFileRead, status_code=status.HTTP_201_CREATED)
async def upload_interview_file(
    project_id: str,
    stakeholder_id: str = FormField(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> ProjectInterviewFile:
    project = _owned_project(db, project_id, _user_id(payload))
    stakeholder = _owned_stakeholder(db, project_id, stakeholder_id)
    data = await _read_interview_file(file)
    detected = _detect_interview_type(data)
    if detected is None:
        raise APIException(400, "30004", "只接受 PDF、DOC 或 DOCX 訪綱檔案")
    extension, content_type = detected
    original_name = Path(file.filename or f"interview-guide{extension}").name[:255]
    stored_name = f"{project.project_id}_{uuid4().hex}{extension}"
    await run_in_threadpool((INTERVIEW_UPLOAD_DIR / stored_name).write_bytes, data)
    record = ProjectInterviewFile(
        project=project,
        stakeholder=stakeholder,
        original_name=original_name,
        stored_name=stored_name,
        content_type=content_type,
        size_bytes=len(data),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


@router.get("/{project_id}/interview-files/{file_id}")
def download_interview_file(
    project_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> FileResponse:
    _owned_project(db, project_id, _user_id(payload))
    record = db.query(ProjectInterviewFile).filter(
        ProjectInterviewFile.file_id == file_id,
        ProjectInterviewFile.project_id == project_id,
        ProjectInterviewFile.is_delete.is_(False),
    ).first()
    if record is None:
        raise APIException(404, "30006", "訪綱檔案不存在")
    path = (INTERVIEW_UPLOAD_DIR / record.stored_name).resolve()
    if path.parent != INTERVIEW_UPLOAD_DIR.resolve() or not path.is_file():
        raise APIException(404, "30006", "訪綱檔案不存在")
    return FileResponse(path, media_type=record.content_type, filename=record.original_name)


@router.delete("/{project_id}/interview-files/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_interview_file(
    project_id: str,
    file_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> None:
    _owned_project(db, project_id, _user_id(payload))
    record = db.query(ProjectInterviewFile).filter(
        ProjectInterviewFile.file_id == file_id,
        ProjectInterviewFile.project_id == project_id,
        ProjectInterviewFile.is_delete.is_(False),
    ).first()
    if record is None:
        raise APIException(404, "30006", "訪綱檔案不存在")
    record.is_delete = True
    db.commit()
