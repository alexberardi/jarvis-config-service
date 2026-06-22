"""add external_host / external_port for off-docker (mobile) clients

Revision ID: 005
Revises: 004
Create Date: 2026-06-22

Internal host/port stay the container coords for direct container-to-container
discovery. These optional columns hold the externally-reachable published
coords (host + published port) returned to clients off the docker network
(the mobile app) via ?style=external.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = '005'
down_revision: Union[str, None] = '004'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('services', sa.Column('external_host', sa.String(255), nullable=True))
    op.add_column('services', sa.Column('external_port', sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column('services', 'external_port')
    op.drop_column('services', 'external_host')
