"""stakeholder relation type and owned outcomes costs

Revision ID: 5a202633ce5d
Revises: d1cc1cc03218
Create Date: 2026-11-08 21:18:07.121899

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a202633ce5d'
down_revision: Union[str, None] = 'd1cc1cc03218'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # forms.status 的型別差異是既有的，跟這次無關，autogenerate 產生的 alter_column 已移除
    op.add_column('project_costs', sa.Column('stakeholder_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_project_costs_stakeholder_id'), 'project_costs', ['stakeholder_id'], unique=False)
    op.create_foreign_key(
        'fk_project_costs_stakeholder_id', 'project_costs', 'project_stakeholders',
        ['stakeholder_id'], ['stakeholder_id'], ondelete='CASCADE',
    )
    op.add_column('project_outcomes', sa.Column('stakeholder_id', sa.String(length=36), nullable=True))
    op.create_index(op.f('ix_project_outcomes_stakeholder_id'), 'project_outcomes', ['stakeholder_id'], unique=False)
    op.create_foreign_key(
        'fk_project_outcomes_stakeholder_id', 'project_outcomes', 'project_stakeholders',
        ['stakeholder_id'], ['stakeholder_id'], ondelete='CASCADE',
    )
    op.add_column('project_stakeholders', sa.Column('relation', sa.String(length=100), server_default='', nullable=False))
    op.add_column('project_stakeholders', sa.Column('stakeholder_type', sa.String(length=100), server_default='', nullable=False))

    # 舊的「關係／類型」文字搬到類型
    op.execute("UPDATE project_stakeholders SET stakeholder_type = role WHERE role <> ''")

    # 舊的成果、成本歸給該專案排序第一位（未刪除）的利害關係人；沒有利害關係人的維持 NULL
    first_stakeholder = """
        SELECT DISTINCT ON (project_id) project_id, stakeholder_id
        FROM project_stakeholders
        WHERE is_delete = false
        ORDER BY project_id, position, create_time
    """
    for table in ('project_outcomes', 'project_costs'):
        op.execute(f"""
            UPDATE {table} AS target
            SET stakeholder_id = first.stakeholder_id
            FROM ({first_stakeholder}) AS first
            WHERE target.project_id = first.project_id
              AND target.stakeholder_id IS NULL
        """)


def downgrade() -> None:
    op.drop_column('project_stakeholders', 'stakeholder_type')
    op.drop_column('project_stakeholders', 'relation')
    op.drop_constraint('fk_project_outcomes_stakeholder_id', 'project_outcomes', type_='foreignkey')
    op.drop_index(op.f('ix_project_outcomes_stakeholder_id'), table_name='project_outcomes')
    op.drop_column('project_outcomes', 'stakeholder_id')
    op.drop_constraint('fk_project_costs_stakeholder_id', 'project_costs', type_='foreignkey')
    op.drop_index(op.f('ix_project_costs_stakeholder_id'), table_name='project_costs')
    op.drop_column('project_costs', 'stakeholder_id')
