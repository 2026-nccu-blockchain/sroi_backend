import io
import shutil
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal, Optional
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session, selectinload, with_loader_criteria
from starlette.concurrency import run_in_threadpool

from app.api.services.interview_files import (
    INTERVIEW_UPLOAD_DIR,
    discard_temp_interview_file,
    load_temp_interview_file,
    move_interview_file_to_deleted,
    promote_temp_interview_file,
    save_temp_interview_file,
)
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
from app.models.model import (
    Answer,
    Form,
    FormResponse,
    FormStatus,
    GroupRole,
    Page,
    Project,
    ProjectCost,
    ProjectInterviewFile,
    ProjectOutcome,
    ProjectOutcomeValuation,
    ProjectStakeholder,
    Question,
    QuestionType,
    ResponseStatus,
)
from app.schemas.project import (
    CostInput,
    OutcomeInput,
    ProjectCostsRead,
    ProjectCreate,
    ProjectRead,
    ProjectSROIRead,
    ProjectSROIUpdate,
    ProjectUpdate,
    StakeholderInput,
    StakeholderUpdateInput,
    TempInterviewFileRead,
)


router = APIRouter()
MAX_INTERVIEW_FILE_SIZE = 10 * 1024 * 1024
READ_CHUNK_SIZE = 1024 * 1024
NON_NULLABLE_PROJECT_FIELDS = {"name", "organization", "description", "begin", "end", "status"}
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
        selectinload(Project.costs),
        selectinload(Project.interview_files),
        selectinload(Project.forms),
        with_loader_criteria(Form, Form.is_delete.is_(False)),
        with_loader_criteria(ProjectStakeholder, ProjectStakeholder.is_delete.is_(False)),
        with_loader_criteria(ProjectOutcome, ProjectOutcome.is_delete.is_(False)),
        with_loader_criteria(ProjectCost, ProjectCost.is_delete.is_(False)),
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
    form_ids: set[str] | None = None,
) -> dict[str, tuple[float, int]]:
    if not outcome_ids:
        return {}
    query = db.query(
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
    )
    if form_ids is not None:
        if not form_ids:
            return {}
        query = query.filter(Form.form_id.in_(form_ids))
    rows = query.all()

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
    stakeholders = sorted(
        (stakeholder for stakeholder in project.stakeholders if not stakeholder.is_delete),
        key=lambda stakeholder: stakeholder.position,
    )
    outcome_ids = {outcome.outcome_id for outcome in outcomes}
    valuations = {
        (valuation.stakeholder_id, valuation.outcome_id): valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project.project_id,
            ProjectOutcomeValuation.outcome_id.in_(outcome_ids) if outcome_ids else False,
            ProjectOutcomeValuation.is_delete.is_(False),
        ).all()
    }
    actual_input_cost = _decimal(project.actual_input_cost).quantize(
        MONEY_QUANTUM,
        rounding=ROUND_HALF_UP,
    )

    discount_rate = _decimal(project.sroi_discount_rate, "0.035")
    serialized_stakeholders: list[dict] = []
    total_social_value = Decimal("0")
    project_has_missing_proxy = False
    stakeholder_ratios: list[Decimal] = []

    for stakeholder in stakeholders:
        linked_form_ids = {
            form_id for form_id in (stakeholder.pre_form_id, stakeholder.post_form_id) if form_id
        }
        scale_metrics = _outcome_scale_metrics(
            db,
            project.project_id,
            outcome_ids,
            linked_form_ids,
        )
        serialized_outcomes: list[dict] = []
        stakeholder_social_value = Decimal("0")
        stakeholder_has_missing_proxy = False

        for outcome in outcomes:
            valuation = valuations.get((stakeholder.stakeholder_id, outcome.outcome_id))
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
            stakeholder_social_value += calculated_value
            if is_included and financial_proxy_value <= 0:
                stakeholder_has_missing_proxy = True
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

        stakeholder_social_value = stakeholder_social_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
        stakeholder_ratio = None
        if actual_input_cost > 0 and not stakeholder_has_missing_proxy:
            stakeholder_ratio = (stakeholder_social_value / actual_input_cost).quantize(
                RATIO_QUANTUM,
                rounding=ROUND_HALF_UP,
            )
            stakeholder_ratios.append(stakeholder_ratio)
        project_has_missing_proxy = project_has_missing_proxy or stakeholder_has_missing_proxy
        total_social_value += stakeholder_social_value
        serialized_stakeholders.append({
            "stakeholder_id": stakeholder.stakeholder_id,
            "stakeholder_name": stakeholder.name,
            "stakeholder_role": stakeholder.role,
            "position": stakeholder.position,
            "outcomes": serialized_outcomes,
            "total_social_value": stakeholder_social_value,
            "sroi_ratio": stakeholder_ratio,
        })

    total_social_value = total_social_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    sroi_ratio = None
    if actual_input_cost > 0 and stakeholders and not project_has_missing_proxy:
        sroi_ratio = sum(stakeholder_ratios, Decimal("0")).quantize(RATIO_QUANTUM, rounding=ROUND_HALF_UP)
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "actual_input_cost": actual_input_cost,
        "discount_rate": discount_rate,
        "stakeholders": serialized_stakeholders,
        "total_social_value": total_social_value,
        "sroi_ratio": sroi_ratio,
    }


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


def _active_costs(db: Session, project_id: str) -> list[ProjectCost]:
    return db.query(ProjectCost).filter(
        ProjectCost.project_id == project_id,
        ProjectCost.is_delete.is_(False),
    ).order_by(ProjectCost.position, ProjectCost.create_time).all()


def _sync_actual_input_cost(db: Session, project: Project) -> None:
    """總成本由成本明細（金額 × 個數）加總，存回 actual_input_cost 讓 SROI 計算沿用。"""
    db.flush()
    total = sum(
        (_decimal(cost.price) * cost.quantity for cost in _active_costs(db, project.project_id)),
        Decimal("0"),
    )
    project.actual_input_cost = total.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)


def _serialize_costs(db: Session, project: Project) -> dict:
    return {
        "project_id": project.project_id,
        "costs": _active_costs(db, project.project_id),
        "total_cost": _decimal(project.actual_input_cost),
    }


def _replace_stakeholders(project: Project, items: list[StakeholderInput]) -> list[ProjectStakeholder]:
    """回傳與 items 同順序的利害關係人，讓後續步驟對應新建立的項目。"""
    existing = {
        stakeholder.stakeholder_id: stakeholder
        for stakeholder in project.stakeholders
        if not stakeholder.is_delete
    }
    result: list[ProjectStakeholder] = []
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
        result.append(stakeholder)
    for stakeholder in existing.values():
        stakeholder.is_delete = True
        for record in stakeholder.interview_files:
            record.is_delete = True
    return result


def _replace_costs(project: Project, items: list[CostInput]) -> None:
    existing = {cost.cost_id: cost for cost in project.costs if not cost.is_delete}
    for position, item in enumerate(items):
        cost = existing.pop(item.cost_id, None) if item.cost_id else None
        if cost is None:
            cost = ProjectCost()
            project.costs.append(cost)
        cost.name = item.name.strip()
        cost.price = item.price
        cost.quantity = item.quantity
        cost.funding_source = item.funding_source.strip()
        cost.position = position
    for cost in existing.values():
        cost.is_delete = True


def _apply_interview_files(
    db: Session,
    project: Project,
    items: list[StakeholderUpdateInput],
    stakeholders: list[ProjectStakeholder],
) -> list[dict]:
    """刪除沒保留的訪綱、為暫存檔建立紀錄；回傳要搬到正式資料夾的暫存檔。"""
    promotions: list[dict] = []
    seen_temp_ids: set[str] = set()
    for item, stakeholder in zip(items, stakeholders):
        if item.interview_file_ids is not None:
            keep = set(item.interview_file_ids)
            active_ids = {record.file_id for record in stakeholder.interview_files if not record.is_delete}
            if keep - active_ids:
                raise APIException(400, "30006", "訪綱檔案不存在")
            for record in stakeholder.interview_files:
                if record.file_id not in keep:
                    record.is_delete = True
        for temp_file_id in item.temp_file_ids:
            # 同一個暫存檔只能存一次，重複送就略過
            if temp_file_id in seen_temp_ids:
                continue
            seen_temp_ids.add(temp_file_id)
            meta = load_temp_interview_file(project.project_id, temp_file_id)
            if meta is None:
                raise APIException(400, "30011", "暫存的訪綱檔案已過期，請重新上傳")
            stored_name = f"{project.project_id}_{temp_file_id}{meta['extension']}"
            db.add(ProjectInterviewFile(
                project=project,
                stakeholder=stakeholder,
                original_name=meta["original_name"],
                stored_name=stored_name,
                content_type=meta["content_type"],
                size_bytes=meta["size_bytes"],
            ))
            promotions.append({**meta, "stored_name": stored_name})
    return promotions


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


@router.get("/{project_id}/sroi", response_model=ProjectSROIRead)
def get_project_sroi(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    project = _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)
    return _serialize_project_sroi(db, project)


@router.put("/{project_id}/sroi", response_model=ProjectSROIRead)
def save_project_sroi(
    project_id: str,
    data: ProjectSROIUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.EDITOR)
    active_stakeholder_ids = {
        stakeholder.stakeholder_id
        for stakeholder in project.stakeholders
        if not stakeholder.is_delete
    }
    active_outcome_ids = {
        outcome.outcome_id
        for outcome in project.outcomes
        if not outcome.is_delete
    }
    submitted_stakeholder_ids = {item.stakeholder_id for item in data.stakeholders}
    if not submitted_stakeholder_ids.issubset(active_stakeholder_ids):
        raise APIException(400, "30010", "SROI 利害關係人不屬於此專案")
    submitted_outcome_ids = {
        outcome.outcome_id
        for stakeholder in data.stakeholders
        for outcome in stakeholder.outcomes
    }
    if not submitted_outcome_ids.issubset(active_outcome_ids):
        raise APIException(400, "30009", "SROI 成果不屬於此專案")

    project.sroi_discount_rate = data.discount_rate

    project.actual_input_cost = data.actual_input_cost

    existing_valuations = {
        (valuation.stakeholder_id, valuation.outcome_id): valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project_id,
        ).all()
    }
    retained_valuation_ids: set[str] = set()
    for stakeholder_item in data.stakeholders:
        for item in stakeholder_item.outcomes:
            key = (stakeholder_item.stakeholder_id, item.outcome_id)
            valuation = existing_valuations.get(key)
            if valuation is None:
                valuation = ProjectOutcomeValuation(
                    project_id=project_id,
                    stakeholder_id=stakeholder_item.stakeholder_id,
                    outcome_id=item.outcome_id,
                )
                db.add(valuation)
                db.flush()
            valuation.quantity = item.quantity
            valuation.financial_proxy_value = item.financial_proxy_value
            valuation.deadweight_rate = item.deadweight_rate
            valuation.attribution_rate = item.attribution_rate
            valuation.displacement_rate = item.displacement_rate
            valuation.duration_years = item.duration_years
            valuation.dropoff_rate = item.dropoff_rate
            valuation.is_included = item.is_included
            valuation.is_delete = False
            retained_valuation_ids.add(valuation.valuation_id)
    for valuation in existing_valuations.values():
        if valuation.valuation_id not in retained_valuation_ids:
            valuation.is_delete = True

    db.commit()
    project = _get_project(db, project_id, user_id, GroupRole.VIEWER)
    return _serialize_project_sroi(db, project)


@router.get("/{project_id}/costs", response_model=ProjectCostsRead)
def list_project_costs(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    project = _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)
    return _serialize_costs(db, project)


@router.patch("/{project_id}", response_model=ProjectRead)
def update_project(
    project_id: str,
    data: ProjectUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    """專案所有內容（含成本、訪綱）都在這裡一次儲存。"""
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.EDITOR)
    changes = data.model_dump(exclude_unset=True)
    stakeholders = changes.pop("stakeholders", None)
    outcomes = changes.pop("outcomes", None)
    costs = changes.pop("costs", None)
    # exclude_unset 不會排除明確送 null 的欄位，NOT NULL 欄位要先擋掉
    for field in NON_NULLABLE_PROJECT_FIELDS & changes.keys():
        if changes[field] is None:
            raise APIException(400, "30008", f"{field} cannot be null")
    for field, value in changes.items():
        setattr(project, field, value)
    if _as_aware(project.end) < _as_aware(project.begin):
        raise APIException(400, "30008", "結束時間不可早於開始時間")
    promotions: list[dict] = []
    # 移除檔案或整個利害關係人都會讓訪綱變成刪除，記下原本有效的檔案來比對
    active_file_ids = {record.file_id for record in project.interview_files if not record.is_delete}
    if stakeholders is not None:
        stakeholder_items = [StakeholderUpdateInput(**item) for item in stakeholders]
        _validate_stakeholder_forms(db, stakeholder_items, project_id)
        saved_stakeholders = _replace_stakeholders(project, stakeholder_items)
        promotions = _apply_interview_files(db, project, stakeholder_items, saved_stakeholders)
    if outcomes is not None:
        _replace_outcomes(
            project,
            [OutcomeInput(**item) for item in outcomes],
        )
    if costs is not None:
        _replace_costs(project, [CostInput(**item) for item in costs])
        _sync_actual_input_cost(db, project)
    db.flush()
    if outcomes is not None:
        _sync_outcomes_to_draft_forms(db, project)

    deleted_files = [
        record for record in project.interview_files
        if record.is_delete and record.file_id in active_file_ids
    ]

    # 檔案先處理再提交：暫存檔複製到正式資料夾、刪除的檔案移到刪除資料夾；失敗就全部還原
    promoted: list[Path] = []
    moved: list[tuple[Path, Path]] = []
    try:
        for meta in promotions:
            promoted.append(promote_temp_interview_file(meta, meta["stored_name"]))
        for record in deleted_files:
            if result := move_interview_file_to_deleted(record.stored_name):
                moved.append(result)
        db.commit()
    except Exception:
        db.rollback()
        for target in promoted:
            target.unlink(missing_ok=True)
        for source, target in moved:
            shutil.move(target, source)
        raise
    for meta in promotions:
        discard_temp_interview_file(meta)
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


@router.post(
    "/{project_id}/interview-files/temp",
    response_model=TempInterviewFileRead,
    status_code=status.HTTP_201_CREATED,
)
async def upload_temp_interview_file(
    project_id: str,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    """先存到暫存資料夾，儲存專案時才寫入資料庫並搬到正式資料夾。"""
    project = _get_project(db, project_id, _user_id(payload), GroupRole.EDITOR)
    data = await _read_interview_file(file)
    detected = _detect_interview_type(data)
    if detected is None:
        raise APIException(400, "30004", "只接受 PDF、DOC 或 DOCX 訪綱檔案")
    extension, content_type = detected
    original_name = Path(file.filename or f"interview-guide{extension}").name[:255]
    return await run_in_threadpool(
        save_temp_interview_file,
        project.project_id,
        data,
        original_name,
        extension,
        content_type,
    )


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
