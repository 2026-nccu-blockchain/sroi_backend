"""add dedicated stakeholder forms

Revision ID: 6f2d9a4c83b1
Revises: 39b54df7c261
"""

from alembic import op
import sqlalchemy as sa


revision = "6f2d9a4c83b1"
down_revision = "39b54df7c261"
branch_labels = None
depends_on = None


DEFAULT_TITLE = "USR計畫參與同意書與資料授權書"
DEFAULT_ORGANIZATION = "政治大學「多元共容・文山共好」USR計畫團隊"
DEFAULT_CONTENT = (
    "您好，我們需要您參與本問卷調查之資料，作為檔案紀錄，並授權給計畫辦公室與計畫主持人"
    "製作計畫成果報告書，以及作為教育目的之簡報與研究成果。參與完全出於自願，您可以選擇不參與。"
)
DEFAULT_SECONDARY_USE = (
    "若有非本計畫之老師、助理或學生欲將本課程、活動或工作坊所產生的資料作為教學或研究使用，"
    "計畫辦公室將審核其研究計畫，僅在能保護個人隱私並與計畫維持互惠關係時提供去識別化資料。"
)
DEFAULT_WITHDRAWAL = "如欲撤回同意，請透過下方聯絡方式與計畫辦公室聯繫。"
DEFAULT_CONTACT_NAME = "政大「多元共容・文山共好」USR計畫辦公室"
DEFAULT_CONTACT_EMAIL = "nccuusr@gmail.com"
DEFAULT_CONTACT_PHONE = "02-29393091 分機 51479"
RESPONDENT_INFO_CONTENT = "請填寫以下基本資料，電子郵件將用於確認每人只填寫一次。"


def upgrade() -> None:
    op.add_column("forms", sa.Column("stakeholder_id", sa.String(36), nullable=True))
    op.create_foreign_key(
        "fk_forms_stakeholder_id", "forms", "project_stakeholders",
        ["stakeholder_id"], ["stakeholder_id"], ondelete="SET NULL",
    )
    op.create_index(
        "uq_forms_active_stakeholder", "forms", ["stakeholder_id"], unique=True,
        postgresql_where=sa.text("stakeholder_id IS NOT NULL AND is_delete = false"),
    )
    op.execute("""
        INSERT INTO forms (form_id, author_id, project_id, stakeholder_id, title, content, status, is_delete)
        SELECT gen_random_uuid()::text, project.created_by, project.project_id,
               stakeholder.stakeholder_id, left(stakeholder.name, 250) || '｜成果問卷', '', 'DRAFT', false
        FROM project_stakeholders AS stakeholder
        JOIN projects AS project ON project.project_id = stakeholder.project_id
        WHERE NOT stakeholder.is_delete AND NOT project.is_delete
    """)
    op.execute(sa.text("""
        INSERT INTO pages (page_id, form_id, is_respondent_info, title, content, position, is_delete)
        SELECT gen_random_uuid()::text, form_id, true, '基本資料', :content, 0, false
        FROM forms
        WHERE stakeholder_id IS NOT NULL
    """).bindparams(content=RESPONDENT_INFO_CONTENT))
    op.execute("""
        INSERT INTO pages (
            page_id, form_id, project_outcome_id, is_respondent_info, title, content, position, is_delete
        )
        SELECT gen_random_uuid()::text, form.form_id, outcome.outcome_id, false, outcome.name, '',
               ROW_NUMBER() OVER (PARTITION BY form.form_id ORDER BY outcome.position, outcome.outcome_id),
               false
        FROM forms AS form
        JOIN project_outcomes AS outcome ON outcome.stakeholder_id = form.stakeholder_id
        WHERE outcome.project_id = form.project_id AND NOT outcome.is_delete
    """)
    op.execute(sa.text("""
        INSERT INTO form_consents (
            consent_id, form_id, version, is_published, title, organization_name, content,
            secondary_use_description, withdrawal_method, contact_name, contact_email, contact_phone
        )
        SELECT gen_random_uuid()::text, form_id, 0, false, :title, :organization, :content,
               :secondary_use, :withdrawal, :contact_name, :email, :phone
        FROM forms
        WHERE stakeholder_id IS NOT NULL
    """).bindparams(
        title=DEFAULT_TITLE, organization=DEFAULT_ORGANIZATION, content=DEFAULT_CONTENT,
        secondary_use=DEFAULT_SECONDARY_USE, withdrawal=DEFAULT_WITHDRAWAL,
        contact_name=DEFAULT_CONTACT_NAME, email=DEFAULT_CONTACT_EMAIL, phone=DEFAULT_CONTACT_PHONE,
    ))


def downgrade() -> None:
    # 保留已建立、可能已有題目或回覆的表單，回到一般專案表單。
    op.drop_index("uq_forms_active_stakeholder", table_name="forms")
    op.drop_constraint("fk_forms_stakeholder_id", "forms", type_="foreignkey")
    op.drop_column("forms", "stakeholder_id")
