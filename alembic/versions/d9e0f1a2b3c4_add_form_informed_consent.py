"""add form informed consent

Revision ID: d9e0f1a2b3c4
Revises: 6763c028447d
Create Date: 2026-11-19
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, None] = "6763c028447d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


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


def _consent_id(seed: str) -> str:
    return (
        "concat("
        f"substr(md5(forms.form_id || '{seed}'), 1, 8), '-', "
        f"substr(md5(forms.form_id || '{seed}'), 9, 4), '-', "
        f"substr(md5(forms.form_id || '{seed}'), 13, 4), '-', "
        f"substr(md5(forms.form_id || '{seed}'), 17, 4), '-', "
        f"substr(md5(forms.form_id || '{seed}'), 21, 12)"
        ")"
    )


def upgrade() -> None:
    op.create_table(
        "form_consents",
        sa.Column("consent_id", sa.String(length=36), nullable=False),
        sa.Column("form_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("is_published", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("organization_name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("secondary_use_description", sa.Text(), nullable=False),
        sa.Column("withdrawal_method", sa.Text(), nullable=False),
        sa.Column("contact_name", sa.String(length=255), nullable=False),
        sa.Column("contact_email", sa.String(length=255), nullable=False),
        sa.Column("contact_phone", sa.String(length=100), nullable=False),
        sa.Column("requires_guardian", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("secondary_use_enabled", sa.Boolean(), server_default="true", nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_delete", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=True),
        sa.Column("update_time", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["form_id"], ["forms.form_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("consent_id"),
        sa.UniqueConstraint("form_id", "version", name="uq_form_consent_version"),
    )
    op.create_index("ix_form_consents_consent_id", "form_consents", ["consent_id"], unique=False)
    op.create_index("ix_form_consents_form_id", "form_consents", ["form_id"], unique=False)
    op.create_index(
        "uq_form_consent_draft",
        "form_consents",
        ["form_id"],
        unique=True,
        postgresql_where=sa.text("is_published = false AND is_delete = false"),
    )

    op.add_column("forms", sa.Column("published_consent_id", sa.String(length=36), nullable=True))

    op.create_table(
        "consent_records",
        sa.Column("consent_record_id", sa.String(length=36), nullable=False),
        sa.Column("response_id", sa.String(length=36), nullable=False),
        sa.Column("consent_id", sa.String(length=36), nullable=False),
        sa.Column("respondent_email", sa.String(length=255), nullable=False),
        sa.Column("participant_name", sa.String(length=255), nullable=False),
        sa.Column("participant_agreed", sa.Boolean(), nullable=False),
        sa.Column("secondary_use_agreed", sa.Boolean(), server_default="false", nullable=False),
        sa.Column("is_adult", sa.Boolean(), nullable=False),
        sa.Column("guardian_name", sa.String(length=255), nullable=True),
        sa.Column("guardian_relationship", sa.String(length=100), nullable=True),
        sa.Column("guardian_agreed", sa.Boolean(), nullable=True),
        sa.Column("consented_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["consent_id"], ["form_consents.consent_id"]),
        sa.ForeignKeyConstraint(["response_id"], ["form_responses.response_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("consent_record_id"),
        sa.UniqueConstraint("response_id"),
    )
    op.create_index("ix_consent_records_consent_id", "consent_records", ["consent_id"], unique=False)
    op.create_index("ix_consent_records_consent_record_id", "consent_records", ["consent_record_id"], unique=False)
    op.create_index("ix_consent_records_response_id", "consent_records", ["response_id"], unique=True)

    draft_id = _consent_id(":consent:draft")
    published_id = _consent_id(":consent:published:1")
    values = {
        "title": DEFAULT_TITLE,
        "organization": DEFAULT_ORGANIZATION,
        "content": DEFAULT_CONTENT,
        "secondary_use": DEFAULT_SECONDARY_USE,
        "withdrawal": DEFAULT_WITHDRAWAL,
        "contact_name": DEFAULT_CONTACT_NAME,
        "contact_email": DEFAULT_CONTACT_EMAIL,
        "contact_phone": DEFAULT_CONTACT_PHONE,
    }
    op.execute(sa.text(f"""
        INSERT INTO form_consents (
            consent_id, form_id, version, is_published, title, organization_name,
            content, secondary_use_description, withdrawal_method, contact_name,
            contact_email, contact_phone, requires_guardian, secondary_use_enabled,
            is_delete, create_time
        )
        SELECT
            {draft_id}, forms.form_id, 0, false, :title, :organization,
            :content, :secondary_use, :withdrawal, :contact_name,
            :contact_email, :contact_phone, true, true, false, now()
        FROM forms
    """).bindparams(**values))
    op.execute(sa.text(f"""
        INSERT INTO form_consents (
            consent_id, form_id, version, is_published, title, organization_name,
            content, secondary_use_description, withdrawal_method, contact_name,
            contact_email, contact_phone, requires_guardian, secondary_use_enabled,
            published_at, is_delete, create_time
        )
        SELECT
            {published_id}, forms.form_id, 1, true, :title, :organization,
            :content, :secondary_use, :withdrawal, :contact_name,
            :contact_email, :contact_phone, true, true,
            COALESCE(forms.update_time, forms.create_time, now()), false, now()
        FROM forms
        WHERE upper(forms.status::text) IN ('PUBLISHED', 'CLOSED')
    """).bindparams(**values))
    op.execute(f"""
        UPDATE forms
        SET published_consent_id = {published_id}
        WHERE upper(forms.status::text) IN ('PUBLISHED', 'CLOSED')
    """)
    op.create_foreign_key(
        "fk_forms_published_consent_id",
        "forms",
        "form_consents",
        ["published_consent_id"],
        ["consent_id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint("fk_forms_published_consent_id", "forms", type_="foreignkey")
    op.drop_column("forms", "published_consent_id")
    op.drop_index("ix_consent_records_response_id", table_name="consent_records")
    op.drop_index("ix_consent_records_consent_record_id", table_name="consent_records")
    op.drop_index("ix_consent_records_consent_id", table_name="consent_records")
    op.drop_table("consent_records")
    op.drop_index("uq_form_consent_draft", table_name="form_consents")
    op.drop_index("ix_form_consents_form_id", table_name="form_consents")
    op.drop_index("ix_form_consents_consent_id", table_name="form_consents")
    op.drop_table("form_consents")
