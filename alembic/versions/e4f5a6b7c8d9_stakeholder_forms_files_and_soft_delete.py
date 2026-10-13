"""stakeholder pre/post forms, stakeholder files, project period and soft delete

Revision ID: e4f5a6b7c8d9
Revises: d3e4f5a6b7c8
"""

from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "e4f5a6b7c8d9"
down_revision: Union[str, None] = "d3e4f5a6b7c8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


SOFT_DELETE_TABLES = (
    "project_stakeholders",
    "project_outcomes",
    "project_interview_files",
    "form_responses",
    "project_outcome_valuations",
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. 移除不再使用的 results 表
    op.execute("DROP TABLE IF EXISTS results")

    # 2. financial_proxies 之前只有 model 沒有 migration
    if not _has_table("financial_proxies"):
        op.create_table(
            "financial_proxies",
            sa.Column("proxy_id", sa.String(length=36), nullable=False),
            sa.Column("name", sa.String(length=255), nullable=False),
            sa.Column("value", sa.Numeric(precision=18, scale=4), nullable=False),
            sa.Column("note", sa.Text(), nullable=False, server_default=""),
            sa.Column("created_by", sa.String(length=36), nullable=False),
            sa.Column("is_delete", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.ForeignKeyConstraint(["created_by"], ["accounts.user_id"]),
            sa.PrimaryKeyConstraint("proxy_id"),
        )
        op.create_index(op.f("ix_financial_proxies_created_by"), "financial_proxies", ["created_by"], unique=False)

    # 3. 所有子表補上軟刪除欄位
    for table in SOFT_DELETE_TABLES:
        op.add_column(table, sa.Column("is_delete", sa.Boolean(), nullable=False, server_default=sa.false()))

    # 4. projects：year -> begin / end，移除 linked_form_id
    op.add_column("projects", sa.Column("begin", sa.DateTime(timezone=True), nullable=True))
    op.add_column("projects", sa.Column("end", sa.DateTime(timezone=True), nullable=True))
    op.execute(
        """
        UPDATE projects
        SET begin = make_timestamptz(year, 1, 1, 0, 0, 0, 'Asia/Taipei'),
            "end" = make_timestamptz(year, 12, 31, 23, 59, 59, 'Asia/Taipei')
        """
    )
    op.alter_column("projects", "begin", nullable=False)
    op.alter_column("projects", "end", nullable=False)
    op.drop_column("projects", "year")
    op.drop_index(op.f("ix_projects_linked_form_id"), table_name="projects")
    op.drop_column("projects", "linked_form_id")

    # 5. project_stakeholders：移除 email，新增前測 / 後測表單
    op.drop_column("project_stakeholders", "email")
    for column in ("pre_form_id", "post_form_id"):
        op.add_column("project_stakeholders", sa.Column(column, sa.String(length=36), nullable=True))
        op.create_foreign_key(
            f"fk_project_stakeholders_{column}",
            "project_stakeholders",
            "forms",
            [column],
            ["form_id"],
            ondelete="SET NULL",
        )
        op.create_index(op.f(f"ix_project_stakeholders_{column}"), "project_stakeholders", [column], unique=False)

    # 6. project_interview_files：檔案改為掛在利害關係人底下
    op.add_column("project_interview_files", sa.Column("stakeholder_id", sa.String(length=36), nullable=True))
    # 既有檔案指派給該專案排序第一的利害關係人；專案沒有利害關係人時建立「未指定利害關係人」
    orphan_projects = bind.execute(sa.text(
        """
        SELECT DISTINCT f.project_id
        FROM project_interview_files f
        WHERE NOT EXISTS (
            SELECT 1 FROM project_stakeholders s
            WHERE s.project_id = f.project_id AND s.is_delete = false
        )
        """
    )).scalars().all()
    for project_id in orphan_projects:
        bind.execute(
            sa.text(
                """
                INSERT INTO project_stakeholders (stakeholder_id, project_id, name, role, notes, position)
                VALUES (:stakeholder_id, :project_id, '未指定利害關係人', '', '', 0)
                """
            ),
            {"stakeholder_id": str(uuid.uuid4()), "project_id": project_id},
        )
    op.execute(
        """
        UPDATE project_interview_files f
        SET stakeholder_id = (
            SELECT s.stakeholder_id
            FROM project_stakeholders s
            WHERE s.project_id = f.project_id AND s.is_delete = false
            ORDER BY s.position, s.create_time
            LIMIT 1
        )
        """
    )
    op.alter_column("project_interview_files", "stakeholder_id", nullable=False)
    op.create_foreign_key(
        "fk_project_interview_files_stakeholder_id",
        "project_interview_files",
        "project_stakeholders",
        ["stakeholder_id"],
        ["stakeholder_id"],
        ondelete="CASCADE",
    )
    op.create_index(
        op.f("ix_project_interview_files_stakeholder_id"),
        "project_interview_files",
        ["stakeholder_id"],
        unique=False,
    )

    # 7. 同一 email 的唯一限制排除已軟刪除的回覆
    op.drop_index("uq_form_response_email", table_name="form_responses")
    op.create_index(
        "uq_form_response_email",
        "form_responses",
        ["form_id", "respondent_email"],
        unique=True,
        postgresql_where=sa.text("is_duplicate_legacy = false AND is_delete = false"),
    )


def downgrade() -> None:
    op.drop_index("uq_form_response_email", table_name="form_responses")
    op.create_index(
        "uq_form_response_email",
        "form_responses",
        ["form_id", "respondent_email"],
        unique=True,
        postgresql_where=sa.text("is_duplicate_legacy = false"),
    )

    op.drop_index(op.f("ix_project_interview_files_stakeholder_id"), table_name="project_interview_files")
    op.drop_constraint("fk_project_interview_files_stakeholder_id", "project_interview_files", type_="foreignkey")
    op.drop_column("project_interview_files", "stakeholder_id")

    for column in ("pre_form_id", "post_form_id"):
        op.drop_index(op.f(f"ix_project_stakeholders_{column}"), table_name="project_stakeholders")
        op.drop_constraint(f"fk_project_stakeholders_{column}", "project_stakeholders", type_="foreignkey")
        op.drop_column("project_stakeholders", column)
    op.add_column("project_stakeholders", sa.Column("email", sa.String(length=255), nullable=True))

    op.add_column("projects", sa.Column("linked_form_id", sa.String(length=36), nullable=True))
    op.create_foreign_key(None, "projects", "forms", ["linked_form_id"], ["form_id"], ondelete="SET NULL")
    op.create_index(op.f("ix_projects_linked_form_id"), "projects", ["linked_form_id"], unique=False)
    op.add_column("projects", sa.Column("year", sa.Integer(), nullable=True))
    op.execute("UPDATE projects SET year = EXTRACT(YEAR FROM begin AT TIME ZONE 'Asia/Taipei')::int")
    op.alter_column("projects", "year", nullable=False)
    op.drop_column("projects", "end")
    op.drop_column("projects", "begin")

    for table in SOFT_DELETE_TABLES:
        op.drop_column(table, "is_delete")

    # financial_proxies 與 results 不在 downgrade 中還原，避免刪掉資料
