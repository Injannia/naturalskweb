"""multi_download_tasks

Revision ID: 0002
Revises: 0001
Create Date: 2026-06-05

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '0002'
down_revision: Union[str, Sequence[str], None] = '0001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'multi_download_tasks',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('progress', sa.Float(), nullable=False),
        sa.Column('filename', sa.String(length=512), nullable=True),
        sa.Column('file_size', sa.Integer(), nullable=True),
        sa.Column('error', sa.String(length=1024), nullable=True),
        sa.Column('url', sa.String(length=2048), nullable=False),
        sa.Column('title', sa.String(length=512), nullable=True),
        sa.Column('thumbnail', sa.String(length=2048), nullable=True),
        sa.Column('platform', sa.String(length=40), nullable=True),
        sa.Column('audio_only', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('shared_file_id', sa.String(length=36), nullable=True),
        sa.Column('hidden', sa.Boolean(), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('CURRENT_TIMESTAMP'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_multi_download_tasks_user_id'), 'multi_download_tasks', ['user_id'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_multi_download_tasks_user_id'), table_name='multi_download_tasks')
    op.drop_table('multi_download_tasks')
