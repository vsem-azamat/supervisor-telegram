"""add indexes to messages agent_decisions agent_escalations channel_posts

Revision ID: 1f95dc964397
Revises: 36dc14a33db3
Create Date: 2026-03-11 23:32:50.643945

"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = '1f95dc964397'
down_revision: Union[str, None] = '36dc14a33db3'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index(op.f('ix_messages_chat_id'), 'messages', ['chat_id'], unique=False)
    op.create_index(op.f('ix_messages_user_id'), 'messages', ['user_id'], unique=False)
    op.create_index(op.f('ix_agent_escalations_chat_id'), 'agent_escalations', ['chat_id'], unique=False)
    op.create_index(op.f('ix_agent_escalations_decision_id'), 'agent_escalations', ['decision_id'], unique=False)
    op.create_index(op.f('ix_agent_escalations_target_user_id'), 'agent_escalations', ['target_user_id'], unique=False)
    op.create_index(op.f('ix_channel_posts_status'), 'channel_posts', ['status'], unique=False)


def downgrade() -> None:
    op.drop_index(op.f('ix_channel_posts_status'), table_name='channel_posts')
    op.drop_index(op.f('ix_agent_escalations_target_user_id'), table_name='agent_escalations')
    op.drop_index(op.f('ix_agent_escalations_decision_id'), table_name='agent_escalations')
    op.drop_index(op.f('ix_agent_escalations_chat_id'), table_name='agent_escalations')
    op.drop_index(op.f('ix_messages_user_id'), table_name='messages')
    op.drop_index(op.f('ix_messages_chat_id'), table_name='messages')
