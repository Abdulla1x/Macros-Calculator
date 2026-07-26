"""ai_analyses.kind so transcriptions share the quota counter

Revision ID: 0003
Revises: 0002
Create Date: 2026-07-26

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0003'
down_revision: str | None = '0002'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # server_default backfills existing rows, which are all analyses.
    op.add_column(
        'ai_analyses',
        sa.Column(
            'kind',
            sa.String(length=20),
            nullable=False,
            server_default='analysis',
        ),
    )


def downgrade() -> None:
    with op.batch_alter_table('ai_analyses', schema=None) as batch_op:
        batch_op.drop_column('kind')
