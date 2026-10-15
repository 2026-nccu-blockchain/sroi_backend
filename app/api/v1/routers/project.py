import io
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Optional
from uuid import uuid4
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Form as FormField, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload, with_loader_criteria
from starlette.concurrency import run_in_threadpool

from app.core.deps import return_payload
from app.core.exceptions import APIException
from app.core.permissions import (
    accessible_project_filter,
    get_group_role,
    get_user_group_roles,
    has_role,
    require_project_role,
)
from app.db.session import get_db
from app.models.model import Form, FormStatus, GroupRole, Page, Project, ProjectInterviewFile, ProjectOutcome, ProjectStakeholder
from app.schemas.project import InterviewFileRead, OutcomeInput, ProjectCreate, ProjectRead, ProjectUpdate, StakeholderInput


router = APIRouter()
INTERVIEW_UPLOAD_DIR = Path(__file__).resolve().parents[3] / "uploads" / "interview_guides"
INTERVIEW_UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
MAX_INTERVIEW_FILE_SIZE = 10 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024
NON_NULLABLE_PROJECT_FIELDS = {"name", "organization", "description", "actual_input_cost", "begin", "end", "status"}


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


def _get_project(db: Session, project_id: str, user_id: str, min_role: GroupRole) -> Project:
    project = _project_query(db).filter(
        Project.project_id == project_id,
        Project.is_delete.is_(False),
    ).first()
    role = require_project_role(db, project, user_id, min_role)
    project.my_role = role.value
    return project


def _validate_stakeholder_forms(
    db: Session,
    items: list[StakeholderInput],
    project_id: str | None = None,
) -> None:
    """前測、後測表單只能選這個專案底下、未刪除的表單；新建專案時還沒有表單可選。
    群組專案的表單可能是其他成員建立的，所以不限作者，權限由專案角色控管。"""
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
        raise APIException(404, "30009", "利害關係人不存在")
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
    scope: Literal["all", "personal", "group"] = "all",
    group_id: Optional[str] = Query(default=None),
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[Project]:
    user_id = _user_id(payload)
    query = _project_query(db).filter(
        accessible_project_filter(db, user_id),
        Project.is_delete.is_(False),
    )
    if scope == "personal":
        query = query.filter(Project.group_id.is_(None))
    elif scope == "group":
        query = query.filter(Project.group_id.isnot(None))
    if group_id is not None:
        query = query.filter(Project.group_id == group_id)
    projects = query.order_by(Project.update_time.desc().nullslast(), Project.create_time.desc()).all()

    group_roles = get_user_group_roles(db, user_id)
    for project in projects:
        role = GroupRole.LEADER if project.is_personal else group_roles[project.group_id]
        project.my_role = role.value
    return projects


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
def create_project(
    data: ProjectCreate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    user_id = _user_id(payload)
    if data.group_id is not None:
        if not has_role(get_group_role(db, data.group_id, user_id), GroupRole.EDITOR):
            raise APIException(403, "30007", "Insufficient project permission")
    _validate_stakeholder_forms(db, data.stakeholders)
    project = Project(
        owner_id=user_id if data.group_id is None else None,
        group_id=data.group_id,
        created_by=user_id,
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
    return _get_project(db, project.project_id, user_id, GroupRole.VIEWER)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    return _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.EDITOR)
    changes = data.model_dump(exclude_unset=True)
    stakeholders = changes.pop("stakeholders", None)
    outcomes = changes.pop("outcomes", None)
    # exclude_unset 不會排除明確送 null 的欄位，NOT NULL 欄位要先擋掉
    for field in NON_NULLABLE_PROJECT_FIELDS & changes.keys():
        if changes[field] is None:
            raise APIException(400, "30008", f"{field} cannot be null")
    for field, value in changes.items():
        setattr(project, field, value)
    if _as_aware(project.end) < _as_aware(project.begin):
        raise APIException(400, "30008", "結束時間不可早於開始時間")
    if stakeholders is not None:
        stakeholder_items = [StakeholderInput(**item) for item in stakeholders]
        _validate_stakeholder_forms(db, stakeholder_items, project_id)
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
    return _get_project(db, project_id, user_id, GroupRole.VIEWER)


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> None:
    project = _get_project(db, project_id, _user_id(payload), GroupRole.LEADER)
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
    project = _get_project(db, project_id, _user_id(payload), GroupRole.EDITOR)
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
    _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)
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
    _get_project(db, project_id, _user_id(payload), GroupRole.EDITOR)
    record = db.query(ProjectInterviewFile).filter(
        ProjectInterviewFile.file_id == file_id,
        ProjectInterviewFile.project_id == project_id,
        ProjectInterviewFile.is_delete.is_(False),
    ).first()
    if record is None:
        raise APIException(404, "30006", "訪綱檔案不存在")
    record.is_delete = True
    db.commit()
