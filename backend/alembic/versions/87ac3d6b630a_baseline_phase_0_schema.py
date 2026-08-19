"""baseline: phase 0 schema

Revision ID: 87ac3d6b630a
Revises:
Create Date: 2026-08-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = '87ac3d6b630a'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('email', sa.String(255), nullable=False, unique=True),
        sa.Column('api_key', sa.String(255), unique=True, nullable=True),
        sa.Column('api_key_hash', sa.String(255), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('updated_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_users_email', 'users', ['email'])

    op.create_table(
        'organizations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('users.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('plan', sa.String(50), server_default='free'),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_organizations_user_id', 'organizations', ['user_id'])

    op.create_table(
        'projects',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('org_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('organizations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('github_repo_url', sa.String(255), nullable=True),
        sa.Column('github_token_encrypted', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_projects_org_id', 'projects', ['org_id'])

    op.create_table(
        'evaluations',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('project_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('projects.id', ondelete='CASCADE'), nullable=False),
        sa.Column('commit_hash', sa.String(40), nullable=True),
        sa.Column('prompt_version', sa.String(255), nullable=True),
        sa.Column('model_name', sa.String(100), nullable=True),
        sa.Column('test_cases_count', sa.Integer(), server_default='0'),
        sa.Column('status', sa.String(50), server_default='pending'),
        sa.Column('results_json', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
        sa.Column('completed_at', sa.DateTime(), nullable=True),
    )
    op.create_index('idx_evaluations_project_id', 'evaluations', ['project_id'])
    op.create_index('idx_evaluations_created_at', 'evaluations', ['created_at'])

    op.create_table(
        'eval_results',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('eval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=False),
        sa.Column('metric_name', sa.String(100), nullable=True),
        sa.Column('metric_value', sa.Float(), nullable=True),
        sa.Column('status', sa.String(50), server_default='pass'),
        sa.Column('details', postgresql.JSONB(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_eval_results_eval_id', 'eval_results', ['eval_id'])

    op.create_table(
        'traces',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('eval_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('evaluations.id', ondelete='CASCADE'), nullable=True),
        sa.Column('trace_data', postgresql.JSONB(), nullable=True),
        sa.Column('latency_ms', sa.Integer(), nullable=True),
        sa.Column('cost_usd', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(), server_default=sa.text('CURRENT_TIMESTAMP')),
    )
    op.create_index('idx_traces_eval_id', 'traces', ['eval_id'])


def downgrade() -> None:
    op.drop_table('traces')
    op.drop_table('eval_results')
    op.drop_table('evaluations')
    op.drop_table('projects')
    op.drop_table('organizations')
    op.drop_table('users')