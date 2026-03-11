"""add footer_template to channels

Revision ID: 930d376edcfd
Revises: b8c2d4e6f7a9
Create Date: 2026-03-07 15:09:21.392003

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '930d376edcfd'
down_revision: Union[str, None] = 'b8c2d4e6f7a9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('channels', sa.Column('footer_template', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('channels', 'footer_template')
