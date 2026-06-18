"""initial_schema

Revision ID: 0ec36b828269
Revises:
Create Date: 2026-06-18 15:20:42.273492

Phase 1 表结构：users / teams / tasks / diff_files / audit_findings /
approvals / audit_reports / audit_operation_log / agent_token_logs / langgraph_checkpoints
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '0ec36b828269'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ──────────── teams ────────────
    op.create_table(
        'teams',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('name', sa.String(128), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )

    # ──────────── users ────────────
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('username', sa.String(64), nullable=False),
        sa.Column('password_hash', sa.String(256), nullable=False),
        sa.Column('role', sa.String(16), server_default='developer', nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('username'),
    )

    # ──────────── tasks ────────────
    op.create_table(
        'tasks',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('status', sa.String(32), server_default='pending', nullable=False),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('repo_path', sa.Text(), nullable=False),
        sa.Column('target_branch', sa.String(256), nullable=False),
        sa.Column('base_branch', sa.String(256), server_default='main', nullable=False),
        sa.Column('path_filter', sa.String(512), nullable=True),
        sa.Column('task_type', sa.String(16), server_default='standard', nullable=True),
        sa.Column('cost_budget', sa.Numeric(8, 4), server_default='0.05', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['team_id'], ['teams.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_tasks_user', 'tasks', ['user_id', sa.text('created_at DESC')])
    op.create_index('idx_tasks_team', 'tasks', ['team_id', sa.text('created_at DESC')])
    op.create_index('idx_tasks_status', 'tasks', ['status'], postgresql_where=sa.text("status IN ('running', 'awaiting_approval')"))

    # ──────────── diff_files ────────────
    op.create_table(
        'diff_files',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=False),
        sa.Column('change_type', sa.String(16), nullable=False),
        sa.Column('additions', sa.Integer(), server_default='0', nullable=True),
        sa.Column('deletions', sa.Integer(), server_default='0', nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ──────────── audit_findings ────────────
    op.create_table(
        'audit_findings',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent', sa.String(64), nullable=False),
        sa.Column('finding_type', sa.String(64), nullable=False),
        sa.Column('risk_level', sa.String(16), nullable=False),
        sa.Column('file_path', sa.Text(), nullable=True),
        sa.Column('line_number', sa.Integer(), nullable=True),
        sa.Column('code_snippet', sa.Text(), nullable=True),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('recommendation', sa.Text(), nullable=True),
        sa.Column('auto_fix_patch', sa.Text(), nullable=True),
        sa.Column('is_deleted', sa.Boolean(), server_default='false', nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_findings_task', 'audit_findings', ['task_id'], postgresql_where=sa.text('NOT is_deleted'))

    # ──────────── approvals ────────────
    op.create_table(
        'approvals',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('finding_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('auditor_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('decision', sa.String(16), nullable=False),
        sa.Column('feedback', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['auditor_id'], ['users.id']),
        sa.ForeignKeyConstraint(['finding_id'], ['audit_findings.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )

    # ──────────── audit_reports ────────────
    op.create_table(
        'audit_reports',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('format', sa.String(8), server_default='json', nullable=False),
        sa.Column('content', postgresql.JSONB(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('task_id'),
    )

    # ──────────── audit_operation_log ────────────
    op.create_table(
        'audit_operation_log',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('team_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('action_type', sa.String(64), nullable=False),
        sa.Column('target_type', sa.String(64), nullable=True),
        sa.Column('target_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('detail', postgresql.JSONB(), nullable=True),
        sa.Column('ip_address', postgresql.INET(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_audit_user_time', 'audit_operation_log', ['user_id', sa.text('created_at DESC')])

    # ──────────── agent_token_logs ────────────
    op.create_table(
        'agent_token_logs',
        sa.Column('id', postgresql.UUID(as_uuid=True), server_default=sa.text('gen_random_uuid()'), nullable=False),
        sa.Column('task_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('agent', sa.String(64), nullable=False),
        sa.Column('model', sa.String(64), nullable=False),
        sa.Column('prompt_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('completion_tokens', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cost', sa.Numeric(10, 6), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['task_id'], ['tasks.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('idx_token_logs_task', 'agent_token_logs', ['task_id'])

    # ──────────── langgraph_checkpoints ────────────
    op.create_table(
        'langgraph_checkpoints',
        sa.Column('thread_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('checkpoint_ns', sa.String(256), server_default='', nullable=False),
        sa.Column('checkpoint_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('parent_checkpoint_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('type', sa.String(32), nullable=True),
        sa.Column('checkpoint', postgresql.JSONB(), nullable=False),
        sa.Column('metadata', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id'),
    )


def downgrade() -> None:
    op.drop_table('langgraph_checkpoints')
    op.drop_index('idx_token_logs_task', table_name='agent_token_logs')
    op.drop_table('agent_token_logs')
    op.drop_index('idx_audit_user_time', table_name='audit_operation_log')
    op.drop_table('audit_operation_log')
    op.drop_table('audit_reports')
    op.drop_table('approvals')
    op.drop_index('idx_findings_task', table_name='audit_findings')
    op.drop_table('audit_findings')
    op.drop_table('diff_files')
    op.drop_index('idx_tasks_status', table_name='tasks')
    op.drop_index('idx_tasks_team', table_name='tasks')
    op.drop_index('idx_tasks_user', table_name='tasks')
    op.drop_table('tasks')
    op.drop_table('users')
    op.drop_table('teams')
