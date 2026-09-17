"""add form builder storage

Revision ID: a21f0c9e8b42
Revises: 5336c1d5636a
Create Date: 2026-09-09
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "a21f0c9e8b42"
down_revision: Union[str, None] = "5336c1d5636a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    form_status = postgresql.ENUM(
        "DRAFT", "PUBLISHED", "CLOSED", name="formstatus", create_type=False
    )
    response_status = postgresql.ENUM(
        "DRAFT", "SUBMITTED", name="responsestatus", create_type=False
    )
    form_status.create(op.get_bind(), checkfirst=True)
    response_status.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "forms",
        sa.Column("status", form_status, server_default="DRAFT", nullable=False),
    )
    op.alter_column(
        "forms",
        "content",
        existing_type=sa.String(length=255),
        type_=sa.Text(),
        existing_nullable=True,
    )
    op.add_column(
        "pages",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "questions",
        sa.Column("is_required", sa.Boolean(), server_default=sa.false(), nullable=False),
    )
    op.add_column(
        "questions",
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
    )
    op.add_column(
        "questions",
        sa.Column(
            "jump_rules",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
    )

    op.create_table(
        "question_options",
        sa.Column("option_id", sa.String(length=36), nullable=False),
        sa.Column("question_id", sa.String(length=36), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("value", sa.String(length=255), nullable=False),
        sa.Column("position", sa.Integer(), server_default="0", nullable=False),
        sa.Column("is_delete", sa.Boolean(), server_default=sa.false(), nullable=False),
        sa.Column("create_time", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("update_time", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["question_id"], ["questions.question_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("option_id"),
    )
    op.create_index("ix_question_options_option_id", "question_options", ["option_id"])
    op.create_index("ix_question_options_question_id", "question_options", ["question_id"])

    op.create_table(
        "form_responses",
        sa.Column("response_id", sa.String(length=36), nullable=False),
        sa.Column("form_id", sa.String(length=36), nullable=False),
        sa.Column("respondent_email", sa.String(length=255)),
        sa.Column("status", response_status, server_default="DRAFT", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True)),
        sa.ForeignKeyConstraint(["form_id"], ["forms.form_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("response_id"),
    )
    op.create_index("ix_form_responses_response_id", "form_responses", ["response_id"])
    op.create_index("ix_form_responses_form_id", "form_responses", ["form_id"])

    op.add_column("answers", sa.Column("response_id", sa.String(length=36)))
    op.add_column("answers", sa.Column("number_value", sa.Integer()))
    op.add_column("answers", sa.Column("date_value", sa.Date()))
    op.alter_column("answers", "email", existing_type=sa.String(length=255), nullable=True)
    op.create_foreign_key(
        "fk_answers_response_id",
        "answers",
        "form_responses",
        ["response_id"],
        ["response_id"],
        ondelete="CASCADE",
    )
    op.create_index("ix_answers_response_id", "answers", ["response_id"])
    op.create_unique_constraint(
        "uq_response_question_answer",
        "answers",
        ["response_id", "question_id"],
    )

    op.create_table(
        "answer_choices",
        sa.Column("answer_id", sa.String(length=36), nullable=False),
        sa.Column("option_id", sa.String(length=36), nullable=False),
        sa.ForeignKeyConstraint(["answer_id"], ["answers.answer_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["option_id"], ["question_options.option_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("answer_id", "option_id"),
    )


def downgrade() -> None:
    op.drop_table("answer_choices")
    op.drop_constraint("uq_response_question_answer", "answers", type_="unique")
    op.drop_index("ix_answers_response_id", table_name="answers")
    op.drop_constraint("fk_answers_response_id", "answers", type_="foreignkey")
    op.alter_column("answers", "email", existing_type=sa.String(length=255), nullable=False)
    op.drop_column("answers", "date_value")
    op.drop_column("answers", "number_value")
    op.drop_column("answers", "response_id")
    op.drop_index("ix_form_responses_form_id", table_name="form_responses")
    op.drop_index("ix_form_responses_response_id", table_name="form_responses")
    op.drop_table("form_responses")
    op.drop_index("ix_question_options_question_id", table_name="question_options")
    op.drop_index("ix_question_options_option_id", table_name="question_options")
    op.drop_table("question_options")
    op.drop_column("questions", "jump_rules")
    op.drop_column("questions", "position")
    op.drop_column("questions", "is_required")
    op.drop_column("pages", "position")
    op.alter_column(
        "forms",
        "content",
        existing_type=sa.Text(),
        type_=sa.String(length=255),
        existing_nullable=True,
    )
    op.drop_column("forms", "status")

    sa.Enum(name="responsestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="formstatus").drop(op.get_bind(), checkfirst=True)
