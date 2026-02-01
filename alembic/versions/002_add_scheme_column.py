"""add scheme column

Revision ID: 002
Revises: 001
Create Date: 2026-01-31

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'services',
        sa.Column('scheme', sa.String(10), server_default='http', nullable=False)
    )


def downgrade() -> None:
    op.drop_column('services', 'scheme')
