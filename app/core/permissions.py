from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.exceptions import APIException
from app.models.model import Form, Group, GroupAccount, GroupRole, Project, Role


ROLE_LEVEL = {GroupRole.VIEWER: 1, GroupRole.EDITOR: 2, GroupRole.LEADER: 3}


def has_role(role: GroupRole | None, min_role: GroupRole) -> bool:
    return role is not None and ROLE_LEVEL[role] >= ROLE_LEVEL[min_role]


def _active_membership_query(db: Session, user_id: str):
    # 只有審核通過、未刪除的群組才算數
    return db.query(GroupAccount).join(Group, Group.group_id == GroupAccount.group_id).filter(
        GroupAccount.user_id == user_id,
        GroupAccount.is_delete.is_(False),
        Group.status == Role.VERIFIED,
        Group.is_delete.is_(False),
    )


def get_group_role(db: Session, group_id: str, user_id: str) -> GroupRole | None:
    membership = _active_membership_query(db, user_id).filter(GroupAccount.group_id == group_id).first()
    return membership.group_role if membership else None


def get_user_group_roles(db: Session, user_id: str) -> dict[str, GroupRole]:
    return {m.group_id: m.group_role for m in _active_membership_query(db, user_id).all()}


def get_project_role(db: Session, project: Project, user_id: str) -> GroupRole | None:
    # 個人專案的擁有者視同組長
    if project.is_personal:
        return GroupRole.LEADER if project.owner_id == user_id else None
    return get_group_role(db, project.group_id, user_id)


def require_project_role(db: Session, project: Project | None, user_id: str, min_role: GroupRole) -> GroupRole:
    role = get_project_role(db, project, user_id) if project is not None else None
    if role is None:
        # 非成員一律回 404，不透露專案是否存在
        raise APIException(404, "30001", "Project not found")
    if not has_role(role, min_role):
        raise APIException(403, "30007", "Insufficient project permission")
    return role


def accessible_project_filter(db: Session, user_id: str):
    """使用者看得到的專案：自己的個人專案 + 所在群組的專案"""
    group_ids = _active_membership_query(db, user_id).with_entities(GroupAccount.group_id)
    return or_(Project.owner_id == user_id, Project.group_id.in_(group_ids))


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
    return role
