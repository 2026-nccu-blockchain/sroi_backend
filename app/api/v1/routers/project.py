import io
from pathlib import Path
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload, with_loader_criteria
from starlette.concurrency import run_in_threadpool

from app.core.deps import return_payload
from app.core.exceptions import APIException
from app.db.session import get_db
from app.models.model import Form, FormStatus, Page, Project, ProjectInterviewFile, ProjectOutcome, ProjectStakeholder
from app.schemas.project import InterviewFileRead, OutcomeInput, ProjectCreate, ProjectRead, ProjectUpdate, StakeholderInput


router = APIRouter()
INTERVIEW_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "interview_guides"
INTERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_INTERVIEW_FILE_SIZE = 10 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024


def _user_id(payload: dict) -> str:
    user_id = payload.get("user_id")
    if not user_id:
        raise APIException(401, "10005", "Invalid token payload")
    return str(user_id)


def _project_query(db: Session):
    return db.query(Project).options(
        selectinload(Project.stakeholders),
        selectinload(Project.outcomes),
        selectinload(Project.interview_files),
        selectinload(Project.linked_form),
        selectinload(Project.forms),
        with_loader_criteria(Form, Form.is_delete.is_(False)),
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


def _validate_linked_form(db: Session, form_id: str | None, owner_id: str) -> None:
    if form_id is None:
        return
    exists = db.query(Form.form_id).filter(
        Form.form_id == form_id,
        Form.author_id == owner_id,
        Form.is_delete.is_(False),
    ).first()
    if exists is None:
        raise APIException(400, "30002", "Linked form does not belong to this user")


def _replace_stakeholders(project: Project, items: list[StakeholderInput]) -> None:
    project.stakeholders.clear()
    for position, item in enumerate(items):
        project.stakeholders.append(ProjectStakeholder(
            name=item.name,
            role=item.role,
            email=str(item.email) if item.email else None,
            notes=item.notes,
            position=position,
        ))


def _replace_outcomes(project: Project, items: list[OutcomeInput]) -> None:
    existing = {outcome.outcome_id: outcome for outcome in project.outcomes}
    ordered: list[ProjectOutcome] = []
    for position, item in enumerate(items):
        outcome = existing.pop(item.outcome_id, None) if item.outcome_id else None
        if outcome is None:
            outcome = ProjectOutcome()
        outcome.name = item.name.strip()
        outcome.position = position
        ordered.append(outcome)
    project.outcomes = ordered


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

        ordered_outcome_pages: list[Page] = []
        for outcome in project.outcomes:
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

        custom_pages = [page for page in pages if page not in ordered_outcome_pages]
        for position, page in enumerate([*ordered_outcome_pages, *custom_pages]):
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
    _validate_linked_form(db, data.linked_form_id, owner_id)
    project = Project(
        owner_id=owner_id,
        name=data.name,
        organization=data.organization,
        description=data.description,
        actual_input_cost=data.actual_input_cost,
        year=data.year,
        status=data.status,
        linked_form_id=data.linked_form_id,
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
    if "linked_form_id" in changes:
        _validate_linked_form(db, changes["linked_form_id"], owner_id)
    for field, value in changes.items():
        setattr(project, field, value)
    if stakeholders is not None:
        _replace_stakeholders(project, [StakeholderInput(**item) for item in stakeholders])
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
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> ProjectInterviewFile:
    project = _owned_project(db, project_id, _user_id(payload))
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
    ).first()
    if record is None:
        raise APIException(404, "30006", "訪綱檔案不存在")
    path = (INTERVIEW_UPLOAD_DIR / record.stored_name).resolve()
    db.delete(record)
    db.commit()
    if path.parent == INTERVIEW_UPLOAD_DIR.resolve() and path.is_file():
        path.unlink()
