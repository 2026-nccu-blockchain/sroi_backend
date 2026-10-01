from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session, selectinload

from app.core.deps import return_payload
from app.core.exceptions import APIException
from app.db.session import get_db
from app.models.model import Form, Project, ProjectStakeholder
from app.schemas.project import ProjectCreate, ProjectRead, ProjectUpdate, StakeholderInput


router = APIRouter()


def _user_id(payload: dict) -> str:
    user_id = payload.get("user_id")
    if not user_id:
        raise APIException(401, "10005", "Invalid token payload")
    return str(user_id)


def _project_query(db: Session):
    return db.query(Project).options(
        selectinload(Project.stakeholders),
        selectinload(Project.linked_form),
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
        year=data.year,
        status=data.status,
        linked_form_id=data.linked_form_id,
    )
    _replace_stakeholders(project, data.stakeholders)
    db.add(project)
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
    if "linked_form_id" in changes:
        _validate_linked_form(db, changes["linked_form_id"], owner_id)
    for field, value in changes.items():
        setattr(project, field, value)
    if stakeholders is not None:
        _replace_stakeholders(project, [StakeholderInput(**item) for item in stakeholders])
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
