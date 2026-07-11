"""users.password_changed_at for token revocation on password change

Revision ID: 0002
Revises: 0001
Create Date: 2026-07-11

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0002'
down_revision: str | None = '0001'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'users', sa.Column('password_changed_at', sa.DateTime(), nullable=True)
    )


def downgrade() -> None:
    with op.batch_alter_table('users', schema=None) as batch_op:
        batch_op.drop_column('password_changed_at')
