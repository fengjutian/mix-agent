"""drop approvals table

Revision ID: a1b2c3d4e5f6
Revises: 0ec36b828269
Create Date: 2026-06-19 12:00:00.000000

移除审批功能对应的 approvals 表。
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '0ec36b828269'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_table('approvals')


def downgrade() -> None:
    op.create_table(
        'approvals',
        sa.Column('id', sa.dialects.postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('finding_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('auditor_id', sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decision', sa.String(16), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['auditor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['finding_id'], ['audit_findings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
