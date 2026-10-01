"""make respondent email unique within each form

Revision ID: e8f1a2b3c4d5
Revises: c4d8e1f2a903
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "e8f1a2b3c4d5"
down_revision: Union[str, None] = "c4d8e1f2a903"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "form_responses",
        sa.Column(
            "is_duplicate_legacy",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.execute(
        "UPDATE form_responses "
        "SET respondent_email = LOWER(TRIM(respondent_email)) "
        "WHERE respondent_email IS NOT NULL"
    )
    op.execute(
        "WITH ranked AS ("
        "SELECT response_id, ROW_NUMBER() OVER ("
        "PARTITION BY form_id, respondent_email "
        "ORDER BY submitted_at NULLS LAST, started_at, response_id"
        ") AS duplicate_number "
        "FROM form_responses WHERE respondent_email IS NOT NULL"
        ") "
        "UPDATE form_responses AS response "
        "SET is_duplicate_legacy = TRUE "
        "FROM ranked "
        "WHERE response.response_id = ranked.response_id "
        "AND ranked.duplicate_number > 1"
    )
    op.create_index(
        "uq_form_response_email",
        "form_responses",
        ["form_id", "respondent_email"],
        unique=True,
        postgresql_where=sa.text("is_duplicate_legacy = false"),
    )


def downgrade() -> None:
    op.drop_index(
        "uq_form_response_email",
        table_name="form_responses",
    )
    op.drop_column("form_responses", "is_duplicate_legacy")
