from sqlalchemy import and_, or_
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.model import Account, Form, Group, GroupAccount, GroupRole, GroupStatus, Project, Role


ROLE_LEVEL = {GroupRole.VIEWER: 1, GroupRole.EDITOR: 2, GroupRole.LEADER: 3}


def has_role(role: GroupRole | None, min_role: GroupRole) -> bool:
    return role is not None and ROLE_LEVEL[role] >= ROLE_LEVEL[min_role]


def _active_membership_query(db: Session, user_id: str):
    # 只有審核通過、未刪除的群組才算數
    return db.query(GroupAccount).join(Group, Group.group_id == GroupAccount.group_id).filter(
        GroupAccount.user_id == user_id,
        GroupAccount.is_delete.is_(False),
        Group.status == GroupStatus.VERIFIED,
        Group.is_delete.is_(False),
    )


def get_group_role(db: Session, group_id: str, user_id: str) -> GroupRole | None:
    membership = _active_membership_query(db, user_id).filter(GroupAccount.group_id == group_id).first()
    return membership.group_role if membership else None


def get_group_members(db: Session, group_id: str) -> tuple[list[dict], list[dict]]:
    """群組成員名單，回傳 (組長, 其他成員)；不看群組審核狀態"""
    rows = db.query(Account, GroupAccount.group_role).join(
        GroupAccount, GroupAccount.user_id == Account.user_id
    ).filter(
        GroupAccount.group_id == group_id,
        GroupAccount.is_delete.is_(False),
        Account.is_delete.is_(False),
    ).order_by(GroupAccount.create_time).all()
    leaders = [
        {"user_id": a.user_id, "campus_id": a.campus_id, "name": a.name}
        for a, role in rows if role == GroupRole.LEADER
    ]
    members = [
        {"user_id": a.user_id, "campus_id": a.campus_id, "name": a.name, "group_role": role.value}
        for a, role in rows if role != GroupRole.LEADER
    ]
    return leaders, members


def count_group_leaders(db: Session, group_id: str) -> int:
    return db.query(GroupAccount).filter(
        GroupAccount.group_id == group_id,
        GroupAccount.group_role == GroupRole.LEADER,
        GroupAccount.is_delete.is_(False),
    ).count()


def get_user_group_roles(db: Session, user_id: str) -> dict[str, GroupRole]:
    return {m.group_id: m.group_role for m in _active_membership_query(db, user_id).all()}


def get_member_project_role(db: Session, project: Project, user_id: str) -> GroupRole | None:
    """使用者在專案裡真正的角色；不是成員就是 None"""
    # 個人專案的擁有者視同組長
    if project.is_personal:
        return GroupRole.LEADER if project.owner_id == user_id else None
    role = get_group_role(db, project.group_id, user_id)
    # 群組草稿只有建立者看得到；建立者（仍是組員）對自己的草稿有完整權限
    if project.is_draft:
        return GroupRole.LEADER if role is not None and project.created_by == user_id else None
    return role


def can_review_projects(db: Session, user_id: str) -> bool:
    """資料庫編輯者與管理員能審核專案"""
    return db.query(Account).filter(
        Account.user_id == user_id,
        Account.role.in_([Role.DB_EDITOR, Role.ADMIN]),
        Account.is_delete.is_(False),
    ).first() is not None


def is_admin(db: Session, user_id: str) -> bool:
    return db.query(Account).filter(
        Account.user_id == user_id,
        Account.role == Role.ADMIN,
        Account.is_delete.is_(False),
    ).first() is not None


def is_project_reviewing(project: Project) -> bool:
    """已結案、已送審、還沒發布"""
    return project.closed_at is not None and project.review_requested_at is not None and project.published_at is None


def get_project_role(db: Session, project: Project, user_id: str) -> GroupRole | None:
    role = get_member_project_role(db, project, user_id)
    if role is not None:
        return role
    # 已發布至資料庫的專案公開給所有登入使用者檢視（含專案表單）；已發布一定已結案，所以不會被拿來修改
    if project.published_at is not None:
        return GroupRole.VIEWER
    # 審核中的專案讓資料庫編輯者、管理員以檢視者身分查看；審核中一定已結案
    if is_project_reviewing(project) and can_review_projects(db, user_id):
        return GroupRole.VIEWER
    # 管理員可以檢視所有專案（所有專案頁）；群組草稿除外，只給檢視者，不能修改
    if is_admin(db, user_id) and not project.is_draft:
        return GroupRole.VIEWER
    return None


def ensure_project_open(project: Project | None) -> None:
    """已結案的專案不能再修改（含利害關係人、SROI、訪綱與專案表單）"""
    if project is not None and project.closed_at is not None:
        raise APIException(409, "30014", "專案已結案，無法再修改")


def require_project_role(
    db: Session,
    project: Project | None,
    user_id: str,
    min_role: GroupRole,
    allow_closed: bool = False,
) -> GroupRole:
    role = get_project_role(db, project, user_id) if project is not None else None
    if role is None:
        # 非成員一律回 404，不透露專案是否存在
        raise APIException(404, "30001", "Project not found")
    if not has_role(role, min_role):
        raise APIException(403, "30007", "Insufficient project permission")
    # 需要編輯權限的操作都是修改，結案後一律擋下；結案、發布、刪除自己帶 allow_closed
    if min_role != GroupRole.VIEWER and not allow_closed:
        ensure_project_open(project)
    return role


def accessible_project_filter(db: Session, user_id: str):
    """使用者看得到的專案：自己的個人專案 + 所在群組的公開專案 + 自己建立的群組草稿"""
    group_ids = _active_membership_query(db, user_id).with_entities(GroupAccount.group_id)
    return or_(
        Project.owner_id == user_id,
        and_(
            Project.group_id.in_(group_ids),
            or_(Project.is_draft.is_(False), Project.created_by == user_id),
        ),
    )


def get_form_role(db: Session, form: Form, user_id: str) -> GroupRole | None:
    # 掛在專案下的表單沿用專案權限；沒有專案的表單只有作者能存取
    if form.project_id is not None:
        project = db.query(Project).filter(
            Project.project_id == form.project_id,
            Project.is_delete.is_(False),
        ).first()
        return get_project_role(db, project, user_id) if project else None
    return GroupRole.LEADER if form.author_id == user_id else None


def require_form_role(db: Session, form: Form | None, user_id: str, min_role: GroupRole) -> GroupRole:
    role = get_form_role(db, form, user_id) if form is not None else None
    if role is None:
        raise APIException(404, "20001", "Form not found")
    if not has_role(role, min_role):
        raise APIException(403, "20035", "Insufficient form permission")
    # 專案結案後，掛在底下的表單也不能再修改
    if min_role != GroupRole.VIEWER and form.project_id is not None:
        ensure_project_open(form.project)
    return role
