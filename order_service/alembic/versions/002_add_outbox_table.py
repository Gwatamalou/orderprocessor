"""add outbox table

Revision ID: 002
Revises: 001
Create Date: 2025-01-01 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'outbox_messages',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('aggregate_id', sa.String(length=255), nullable=False),
        sa.Column('aggregate_type', sa.String(length=100), nullable=False),
        sa.Column('event_type', sa.String(length=100), nullable=False),
        sa.Column('payload', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('processed_at', sa.DateTime(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('idx_outbox_processed_created', 'outbox_messages', ['processed_at', 'created_at'])
    op.create_index(op.f('ix_outbox_messages_aggregate_id'), 'outbox_messages', ['aggregate_id'])


def downgrade() -> None:
    op.drop_index(op.f('ix_outbox_messages_aggregate_id'), table_name='outbox_messages')
    op.drop_index('idx_outbox_processed_created', table_name='outbox_messages')
    op.drop_table('outbox_messages')
