"""water_logs table and the two water settings columns

Revision ID: 0009
Revises: 0008
Create Date: 2026-08-21

The water tracker. One new user-owned table plus two nullable columns on
`settings`.

`water_logs` is event rows, not a per-day total, and the index is deliberately
NOT unique on (user_id, date) -- see the model docstring. That is the one thing
about this schema that is easy to "tidy up" into a bug later.

Both settings columns are nullable, so there is no backfill and no
server_default: NULL means "derive the goal from my weight" and "use the
shipped quick-add amounts" respectively, which is precisely the behaviour every
existing row should have.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0009'
down_revision: str | None = '0008'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'water_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('ml', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Not unique: several drinks a day is the point of the table.
    op.create_index(
        'ix_water_logs_user_date', 'water_logs', ['user_id', 'date'], unique=False
    )

    op.add_column('settings', sa.Column('water_goal_ml', sa.Float(), nullable=True))
    op.add_column(
        'settings', sa.Column('water_quick_adds_json', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('settings', 'water_quick_adds_json')
    op.drop_column('settings', 'water_goal_ml')
    op.drop_index('ix_water_logs_user_date', table_name='water_logs')
    op.drop_table('water_logs')
