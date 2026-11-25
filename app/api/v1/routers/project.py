import io
import shutil
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Literal, Optional
from zipfile import BadZipFile, ZipFile

from fastapi import APIRouter, Depends, File, Query, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import and_, case, exists, func, or_
from sqlalchemy.orm import Session, aliased, selectinload, with_loader_criteria
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
    get_member_project_role,
    get_user_group_roles,
    has_role,
    is_admin,
    can_review_projects,
    is_project_reviewing,
    require_project_role,
)
from app.db.session import get_db
from app.models.model import (
    Account,
    Answer,
    Form,
    FormResponse,
    FinancialProxy,
    FormStatus,
    Group,
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
    AdminProjectListItem,
    AdminProjectPage,
    CostInput,
    OutcomeInput,
    ProjectCostsRead,
    ProjectCreate,
    ProjectRead,
    ProjectReviewDecision,
    StakeholderSROIRead,
    StakeholderSROIUpdate,
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


def _get_project(
    db: Session,
    project_id: str,
    user_id: str,
    min_role: GroupRole,
    allow_closed: bool = False,
) -> Project:
    project = _project_query(db).filter(
        Project.project_id == project_id,
        Project.is_delete.is_(False),
    ).first()
    role = require_project_role(db, project, user_id, min_role, allow_closed=allow_closed)
    project.my_role = role.value
    # 從共用資料庫打開別人的已發布專案時是 False，前端據此決定返回哪裡
    project.is_member = get_member_project_role(db, project, user_id) is not None
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


def _active_stakeholders(project: Project) -> list[ProjectStakeholder]:
    return sorted(
        (stakeholder for stakeholder in project.stakeholders if not stakeholder.is_delete),
        key=lambda stakeholder: stakeholder.position,
    )


def _ordered_outcomes(project: Project) -> list[ProjectOutcome]:
    """依「利害關係人順序 → 成果順序」排列；沒有指定利害關係人的舊成果排最前面。"""
    stakeholder_positions = {
        stakeholder.stakeholder_id: stakeholder.position
        for stakeholder in _active_stakeholders(project)
    }
    return sorted(
        (
            outcome for outcome in project.outcomes
            if not outcome.is_delete
            and (outcome.stakeholder_id is None or outcome.stakeholder_id in stakeholder_positions)
        ),
        key=lambda outcome: (
            -1 if outcome.stakeholder_id is None else stakeholder_positions[outcome.stakeholder_id],
            outcome.position,
        ),
    )


def _outcomes_of(outcomes: list[ProjectOutcome], stakeholder_id: str) -> list[ProjectOutcome]:
    """利害關係人自己的成果，加上沒有指定利害關係人的舊成果（視為共用）。"""
    return [
        outcome for outcome in outcomes
        if outcome.stakeholder_id is None or outcome.stakeholder_id == stakeholder_id
    ]


def _get_active_stakeholder(project: Project, stakeholder_id: str) -> ProjectStakeholder:
    stakeholder = next(
        (
            item for item in project.stakeholders
            if item.stakeholder_id == stakeholder_id and not item.is_delete
        ),
        None,
    )
    if stakeholder is None:
        raise APIException(404, "30012", "利害關係人不屬於此專案")
    return stakeholder


def _serialize_stakeholder_sroi(
    db: Session,
    project: Project,
    stakeholder: ProjectStakeholder,
) -> dict:
    outcomes = _ordered_outcomes(project)
    stakeholder_outcomes = _outcomes_of(outcomes, stakeholder.stakeholder_id)
    outcome_ids = {outcome.outcome_id for outcome in stakeholder_outcomes}
    valuations = {
        valuation.outcome_id: valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project.project_id,
            ProjectOutcomeValuation.stakeholder_id == stakeholder.stakeholder_id,
            ProjectOutcomeValuation.outcome_id.in_(outcome_ids) if outcome_ids else False,
            ProjectOutcomeValuation.is_delete.is_(False),
        ).all()
    }
    input_cost = sum(
        (
            _decimal(cost.price) * cost.quantity
            for cost in project.costs
            if not cost.is_delete and cost.stakeholder_id == stakeholder.stakeholder_id
        ),
        Decimal("0"),
    ).quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    discount_rate = _decimal(stakeholder.sroi_discount_rate, "0.035")
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
    total_social_value = Decimal("0")
    has_missing_proxy = False

    for outcome in stakeholder_outcomes:
        valuation = valuations.get(outcome.outcome_id)
        proxy = valuation.financial_proxy if valuation else None
        if proxy is not None and proxy.is_delete:
            proxy = None
        quantity = _decimal(valuation.quantity if valuation else None)
        financial_proxy_value = _decimal(proxy.value if proxy else None)
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
        if is_included and proxy is None:
            has_missing_proxy = True
        metric = scale_metrics.get(outcome.outcome_id)
        scale_score = metric[0] if metric else None
        answer_count = metric[1] if metric else 0
        serialized_outcomes.append({
            "outcome_id": outcome.outcome_id,
            "outcome_name": outcome.name,
            "position": outcome.position,
            "quantity": quantity,
            "financial_proxy_id": proxy.proxy_id if proxy else None,
            "financial_proxy_name": proxy.name if proxy else None,
            "financial_proxy_note": proxy.note if proxy else None,
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

    total_social_value = total_social_value.quantize(MONEY_QUANTUM, rounding=ROUND_HALF_UP)
    sroi_ratio = None
    if input_cost > 0 and not has_missing_proxy:
        sroi_ratio = (total_social_value / input_cost).quantize(
            RATIO_QUANTUM,
            rounding=ROUND_HALF_UP,
        )
    return {
        "project_id": project.project_id,
        "project_name": project.name,
        "stakeholder_id": stakeholder.stakeholder_id,
        "stakeholder_name": stakeholder.name,
        "stakeholder_role": stakeholder.stakeholder_type,
        "position": stakeholder.position,
        "input_cost": input_cost,
        "discount_rate": discount_rate,
        "outcomes": serialized_outcomes,
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
    """回傳與 items 同順序的利害關係人，讓後續步驟對應新建立的項目。
    被移除的利害關係人，他的訪綱、成果、成本一起標記刪除。"""
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
        stakeholder.relation = item.relation.strip()
        stakeholder.stakeholder_type = item.stakeholder_type.strip()
        stakeholder.notes = item.notes
        stakeholder.pre_form_id = item.pre_form_id
        stakeholder.post_form_id = item.post_form_id
        stakeholder.position = position
        result.append(stakeholder)
    for stakeholder in existing.values():
        stakeholder.is_delete = True
        for record in stakeholder.interview_files:
            record.is_delete = True
        for outcome in stakeholder.outcomes:
            outcome.is_delete = True
        for cost in stakeholder.costs:
            cost.is_delete = True
    return result


def _apply_stakeholder_children(
    project: Project,
    items: list[StakeholderInput],
    stakeholders: list[ProjectStakeholder],
) -> tuple[bool, bool]:
    """依各利害關係人底下的 outcomes / costs 取代他的成果與成本；回傳（成果有沒有送、成本有沒有送）。"""
    outcomes_sent = costs_sent = False
    for item, stakeholder in zip(items, stakeholders):
        if item.outcomes is not None:
            outcomes_sent = True
            _replace_outcomes(project, stakeholder, item.outcomes)
        if item.costs is not None:
            costs_sent = True
            _replace_costs(project, stakeholder, item.costs)
    return outcomes_sent, costs_sent


def _replace_costs(project: Project, stakeholder: ProjectStakeholder, items: list[CostInput]) -> None:
    # 只動這位利害關係人的成本；沒有指定利害關係人的舊成本也可以被認領
    existing = {
        cost.cost_id: cost
        for cost in project.costs
        if not cost.is_delete and (cost.stakeholder is stakeholder or (cost.stakeholder is None and cost.stakeholder_id is None))
    }
    owned = {cost_id for cost_id, cost in existing.items() if cost.stakeholder is stakeholder}
    for position, item in enumerate(items):
        cost = existing.pop(item.cost_id, None) if item.cost_id else None
        if cost is None:
            cost = ProjectCost()
            project.costs.append(cost)
        cost.stakeholder = stakeholder
        cost.name = item.name.strip()
        cost.price = item.price
        cost.quantity = item.quantity
        cost.funding_source = item.funding_source.strip()
        cost.position = position
    for cost_id, cost in existing.items():
        if cost_id in owned:
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


def _replace_outcomes(project: Project, stakeholder: ProjectStakeholder, items: list[OutcomeInput]) -> None:
    # 只動這位利害關係人的成果；沒有指定利害關係人的舊成果也可以被認領
    existing = {
        outcome.outcome_id: outcome
        for outcome in project.outcomes
        if not outcome.is_delete and (outcome.stakeholder is stakeholder or (outcome.stakeholder is None and outcome.stakeholder_id is None))
    }
    owned = {outcome_id for outcome_id, outcome in existing.items() if outcome.stakeholder is stakeholder}
    for position, item in enumerate(items):
        outcome = existing.pop(item.outcome_id, None) if item.outcome_id else None
        if outcome is None:
            project.outcome_sync_sequence = (project.outcome_sync_sequence or 0) + 1
            outcome = ProjectOutcome(sync_index=project.outcome_sync_sequence)
            project.outcomes.append(outcome)
        outcome.stakeholder = stakeholder
        outcome.name = item.name.strip()
        outcome.position = position
    for outcome_id, outcome in existing.items():
        if outcome_id in owned:
            outcome.is_delete = True


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
    # 管理員看指定群組的專案時不限成員（管理員的群組頁）；權限仍是檢視者，由 get_project_role 決定；別人的草稿不顯示
    visible = (
        and_(
            Project.group_id == group_id,
            or_(Project.is_draft.is_(False), Project.created_by == user_id),
        )
        if group_id is not None and is_admin(db, user_id)
        else accessible_project_filter(db, user_id)
    )
    query = _project_query(db).filter(
        visible,
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
        if project.is_personal:
            role = GroupRole.LEADER
        elif project.is_draft:
            # 篩選條件保證草稿一定是自己建立的；建立者對自己的草稿視同組長
            role = GroupRole.LEADER if project.group_id in group_roles else None
        else:
            role = group_roles.get(project.group_id)
        # 只有管理員看非成員群組時會是 None
        project.is_member = role is not None
        project.my_role = (role or GroupRole.VIEWER).value
    return projects


# 要放在 /{project_id} 之前，不然 "published" 會被當成專案 id
@router.get("/published", response_model=list[ProjectRead])
def list_published_projects(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[Project]:
    """共用資料庫：所有登入使用者都看得到已發布至資料庫的專案。"""
    user_id = _user_id(payload)
    projects = _project_query(db).options(selectinload(Project.creator)).filter(
        Project.published_at.isnot(None),
        Project.is_delete.is_(False),
    ).order_by(Project.published_at.desc()).all()

    # 不是成員的人也能以檢視者身分打開，跟 get_project_role 的規則一致
    group_roles = get_user_group_roles(db, user_id)
    for project in projects:
        if project.is_personal:
            role = GroupRole.LEADER if project.owner_id == user_id else None
        else:
            role = group_roles.get(project.group_id)
        project.is_member = role is not None
        project.my_role = (role or GroupRole.VIEWER).value
        # 作者：建立專案的人
        project.creator_name = project.creator.name if project.creator else None
    return projects


def _require_reviewer(db: Session, user_id: str) -> None:
    if not can_review_projects(db, user_id):
        raise APIException(403, "30019", "只有資料庫編輯者或管理員能審核專案")


# 同樣要放在 /{project_id} 之前
@router.get("/reviewing", response_model=list[ProjectRead])
def list_reviewing_projects(
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> list[Project]:
    """審核專案：資料庫編輯者、管理員看得到所有審核中的專案，依送審時間排序。"""
    user_id = _user_id(payload)
    _require_reviewer(db, user_id)
    projects = _project_query(db).options(selectinload(Project.creator)).filter(
        Project.closed_at.isnot(None),
        Project.review_requested_at.isnot(None),
        Project.published_at.is_(None),
        Project.is_delete.is_(False),
    ).order_by(Project.review_requested_at.asc()).all()

    group_roles = get_user_group_roles(db, user_id)
    for project in projects:
        if project.is_personal:
            role = GroupRole.LEADER if project.owner_id == user_id else None
        else:
            role = group_roles.get(project.group_id)
        project.is_member = role is not None
        project.my_role = (role or GroupRole.VIEWER).value
        project.creator_name = project.creator.name if project.creator else None
    return projects


PROJECT_PHASES = ("not_started", "in_progress", "pending_close", "closed", "reviewing", "published")


def _phase_expr():
    """和前端 getProjectPhase 相同的規則，改在資料庫算；時間用資料庫的 now()"""
    now = func.now()
    return case(
        (Project.published_at.isnot(None), "published"),
        (and_(Project.closed_at.isnot(None), Project.review_requested_at.isnot(None)), "reviewing"),
        (Project.closed_at.isnot(None), "closed"),
        (Project.begin > now, "not_started"),
        (Project.end >= now, "in_progress"),
        else_="pending_close",
    )


# 用 ! 當跳脫字元，不受資料庫 standard_conforming_strings 對反斜線的影響
def _escape_like(keyword: str) -> str:
    return keyword.replace("!", "!!").replace("%", "!%").replace("_", "!_")


# 同樣要放在 /{project_id} 之前
@router.get("/all", response_model=AdminProjectPage)
def list_all_projects(
    scope: Literal["all", "personal", "group"] = "all",
    phase: Literal["all", "not_started", "in_progress", "pending_close", "closed", "reviewing", "published"] = "all",
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    """管理員：所有人的個人專案與所有群組專案；篩選、搜尋、計數、分頁都在資料庫做。"""
    user_id = _user_id(payload)
    if not is_admin(db, user_id):
        raise APIException(403, "10008", "permission denied")

    creator = aliased(Account)
    phase_col = _phase_expr()
    is_group = Project.group_id.isnot(None)
    keyword = q.strip()

    # 共用的 FROM + 基本條件：未刪除 + 搜尋（名稱、單位、建立者、群組名）
    def base(*columns):
        query = db.query(*columns).select_from(Project).outerjoin(
            creator, creator.user_id == Project.created_by
        ).outerjoin(
            Group, Group.group_id == Project.group_id
        ).filter(
            Project.is_delete.is_(False),
            # 群組草稿只有建立者看得到，管理員也看不到
            or_(Project.is_draft.is_(False), Project.created_by == user_id),
        )
        if keyword:
            pattern = f"%{_escape_like(keyword)}%"
            query = query.filter(or_(
                Project.name.ilike(pattern, escape="!"),
                Project.organization.ilike(pattern, escape="!"),
                creator.name.ilike(pattern, escape="!"),
                Group.title.ilike(pattern, escape="!"),
            ))
        return query

    # 一次拿到 (個人/群組) × 狀態 的數量，兩層分頁的數字都從這裡算
    # 先包成子查詢再 GROUP BY，避免 CASE 裡的字串參數在 SELECT 和 GROUP BY 被當成不同運算式
    counted = base(is_group.label("is_group"), phase_col.label("phase")).subquery()
    scope_counts = {"all": 0, "personal": 0, "group": 0}
    phase_counts = {key: 0 for key in ("all", *PROJECT_PHASES)}
    for grouped, phase_value, count in db.query(
        counted.c.is_group, counted.c.phase, func.count()
    ).group_by(counted.c.is_group, counted.c.phase).all():
        scope_key = "group" if grouped else "personal"
        scope_counts["all"] += count
        scope_counts[scope_key] += count
        if scope in ("all", scope_key):
            phase_counts["all"] += count
            phase_counts[phase_value] += count

    has_published_form = exists().where(
        Form.project_id == Project.project_id,
        Form.is_delete.is_(False),
        Form.status == FormStatus.PUBLISHED,
    )
    items_query = base(
        Project.project_id,
        Project.owner_id,
        Project.group_id,
        Project.name,
        Project.organization,
        Project.begin,
        Project.end,
        Project.status,
        Project.closed_at,
        Project.review_requested_at,
        Project.published_at,
        creator.name.label("creator_name"),
        Group.title.label("group_title"),
        has_published_form.label("has_published_form"),
    )
    if scope == "personal":
        items_query = items_query.filter(Project.group_id.is_(None))
    elif scope == "group":
        items_query = items_query.filter(Project.group_id.isnot(None))
    if phase != "all":
        items_query = items_query.filter(phase_col == phase)

    rows = items_query.order_by(
        Project.update_time.desc().nullslast(),
        Project.create_time.desc(),
        # 排序要穩定，翻頁才不會重複或漏掉
        Project.project_id,
    ).offset((page - 1) * page_size).limit(page_size).all()

    return {
        "items": [AdminProjectListItem.model_validate(dict(row._mapping)) for row in rows],
        "total": phase_counts[phase],
        "page": page,
        "page_size": page_size,
        "scope_counts": scope_counts,
        "phase_counts": phase_counts,
    }


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
        # 群組專案建立後先是草稿，只有建立者看得到
        is_draft=data.group_id is not None,
    )
    saved_stakeholders = _replace_stakeholders(project, data.stakeholders)
    _, costs_sent = _apply_stakeholder_children(project, data.stakeholders, saved_stakeholders)
    db.add(project)
    db.flush()
    if costs_sent:
        _sync_actual_input_cost(db, project)
    db.commit()
    return _get_project(db, project.project_id, user_id, GroupRole.VIEWER)


@router.get("/{project_id}", response_model=ProjectRead)
def get_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    return _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)


@router.get(
    "/{project_id}/stakeholders/{stakeholder_id}/sroi",
    response_model=StakeholderSROIRead,
)
def get_stakeholder_sroi(
    project_id: str,
    stakeholder_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    project = _get_project(db, project_id, _user_id(payload), GroupRole.VIEWER)
    stakeholder = _get_active_stakeholder(project, stakeholder_id)
    return _serialize_stakeholder_sroi(db, project, stakeholder)


@router.put(
    "/{project_id}/stakeholders/{stakeholder_id}/sroi",
    response_model=StakeholderSROIRead,
)
def save_stakeholder_sroi(
    project_id: str,
    stakeholder_id: str,
    data: StakeholderSROIUpdate,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> dict:
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.EDITOR)
    stakeholder = _get_active_stakeholder(project, stakeholder_id)
    outcomes = _ordered_outcomes(project)
    allowed_ids = {
        outcome.outcome_id for outcome in _outcomes_of(outcomes, stakeholder_id)
    }
    if not {item.outcome_id for item in data.outcomes}.issubset(allowed_ids):
        raise APIException(400, "30009", "SROI 成果不屬於此利害關係人")

    proxy_ids = {
        item.financial_proxy_id
        for item in data.outcomes
        if item.financial_proxy_id is not None
    }
    proxies = {
        proxy.proxy_id: proxy
        for proxy in db.query(FinancialProxy).filter(
            FinancialProxy.proxy_id.in_(proxy_ids) if proxy_ids else False,
            FinancialProxy.is_delete.is_(False),
        ).all()
    }
    if set(proxies) != proxy_ids:
        raise APIException(400, "30013", "財務代理變數不存在或已刪除")

    stakeholder.sroi_discount_rate = data.discount_rate

    existing_valuations = {
        valuation.outcome_id: valuation
        for valuation in db.query(ProjectOutcomeValuation).filter(
            ProjectOutcomeValuation.project_id == project_id,
            ProjectOutcomeValuation.stakeholder_id == stakeholder_id,
        ).all()
    }
    retained_valuation_ids: set[str] = set()
    for item in data.outcomes:
        valuation = existing_valuations.get(item.outcome_id)
        if valuation is None:
            valuation = ProjectOutcomeValuation(
                project_id=project_id,
                stakeholder_id=stakeholder_id,
                outcome_id=item.outcome_id,
            )
            db.add(valuation)
            db.flush()
        proxy = proxies.get(item.financial_proxy_id)
        valuation.quantity = item.quantity
        valuation.financial_proxy_id = item.financial_proxy_id
        # 保留一份儲存當下的金額快照；讀取計算時以代理變數資料庫的現值為準。
        valuation.financial_proxy_value = proxy.value if proxy else Decimal("0")
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
    stakeholder = _get_active_stakeholder(project, stakeholder_id)
    return _serialize_stakeholder_sroi(db, project, stakeholder)


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
        _apply_stakeholder_children(project, stakeholder_items, saved_stakeholders)
        # 移除利害關係人也會刪掉他的成果與成本，所以只要送了利害關係人就重新整理
        db.flush()
        _sync_actual_input_cost(db, project)
    db.flush()

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
    project = _get_project(db, project_id, _user_id(payload), GroupRole.LEADER, allow_closed=True)
    project.is_delete = True
    db.commit()


@router.post("/{project_id}/make-public", response_model=ProjectRead)
def make_project_public(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    """群組草稿公開給組員：草稿只有建立者看得到，所以只有建立者能做；公開後不能改回草稿。"""
    user_id = _user_id(payload)
    # 別人的草稿在 get_project_role 會是 None，這裡直接回 404
    project = _get_project(db, project_id, user_id, GroupRole.EDITOR)
    if project.is_personal:
        raise APIException(400, "30022", "個人專案沒有草稿模式")
    if not project.is_draft:
        raise APIException(409, "30023", "專案已經公開")
    project.is_draft = False
    db.commit()
    return _get_project(db, project_id, user_id, GroupRole.VIEWER)


@router.post("/{project_id}/close", response_model=ProjectRead)
def close_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    """結案：只有組長能做，且專案期間結束後（待結案）才能結案；結案後無法復原。"""
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.LEADER, allow_closed=True)
    if project.closed_at is not None:
        raise APIException(409, "30014", "專案已結案")
    if project.is_draft:
        raise APIException(409, "30021", "草稿需要先公開給群組才能結案")
    if datetime.now(timezone.utc) <= _as_aware(project.end):
        raise APIException(400, "30015", "專案期間尚未結束，還不能結案")
    project.closed_at = datetime.now(timezone.utc)
    db.commit()
    return _get_project(db, project_id, user_id, GroupRole.VIEWER)


@router.post("/{project_id}/publish", response_model=ProjectRead)
def publish_project(
    project_id: str,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    """發布至資料庫：只有組長能做，且必須先結案；送出後進入審核，資料庫編輯者同意後才會發布。"""
    user_id = _user_id(payload)
    project = _get_project(db, project_id, user_id, GroupRole.LEADER, allow_closed=True)
    if project.closed_at is None:
        raise APIException(400, "30016", "專案結案後才能發布至資料庫")
    if project.published_at is not None:
        raise APIException(409, "30017", "專案已發布至資料庫")
    if project.review_requested_at is not None:
        raise APIException(409, "30018", "專案審核中")
    project.review_requested_at = datetime.now(timezone.utc)
    db.commit()
    return _get_project(db, project_id, user_id, GroupRole.VIEWER)


@router.post("/{project_id}/review", response_model=ProjectRead)
def review_project(
    project_id: str,
    data: ProjectReviewDecision,
    db: Session = Depends(get_db),
    payload: dict = Depends(return_payload),
) -> Project:
    """審核專案：只有資料庫編輯者、管理員能做。同意則發布至資料庫；不同意則退回已結案，不會出現在共用資料庫。"""
    user_id = _user_id(payload)
    _require_reviewer(db, user_id)
    project = _project_query(db).filter(
        Project.project_id == project_id,
        Project.is_delete.is_(False),
    ).first()
    if project is None:
        raise APIException(404, "30001", "Project not found")
    if not is_project_reviewing(project):
        raise APIException(409, "30020", "專案不在審核中")
    if data.approved:
        project.published_at = datetime.now(timezone.utc)
    else:
        project.review_requested_at = None
    db.commit()

    # 不同意後資料庫編輯者就看不到這個專案了，所以不走 _get_project 的權限檢查
    project = _project_query(db).filter(Project.project_id == project_id).first()
    member_role = get_member_project_role(db, project, user_id)
    project.is_member = member_role is not None
    project.my_role = (member_role or GroupRole.VIEWER).value
    return project


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
