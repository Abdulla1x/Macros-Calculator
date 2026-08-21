"""supplement tracker: supplements + supplement_logs

Revision ID: 0011
Revises: 0010
Create Date: 2026-08-21

Two tables and no settings column, which is what makes this phase different
from 0009 and 0010. Water and steps each hung a goal off `settings`; a
supplement's schedule belongs to the supplement, so there is nothing to add to
that row and nothing to backfill on it.

The unique index on supplement_logs is the one to not "simplify". It spans
(user_id, supplement_id, date, time_of_day) because a tick is a state rather
than an event: tapping the same box twice is the same fact, and the constraint
is what makes POST idempotent instead of a way to record one pill as two.

`uq_supplements_user_lower_name` is an expression index, so it is hand-written
the way 0007's and 0001's are -- autogenerate cannot emit one, and batch mode
cannot express one either.

`active` is NOT NULL with a server_default. The table is new so nothing needs
backfilling on the way up; the default earns its place on the way back up from
a downgrade, when the rows recreated by an operator's own INSERT may omit it.

No batch_alter_table anywhere -- nothing existing is being rebuilt.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0011'
down_revision: str | None = '0010'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'supplements',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('dose', sa.String(length=60), nullable=True),
        sa.Column('times_json', sa.Text(), nullable=False),
        sa.Column(
            'active', sa.Boolean(), nullable=False, server_default=sa.true()
        ),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'uq_supplements_user_lower_name', 'supplements',
        ['user_id', sa.text('lower(name)')], unique=True,
    )

    op.create_table(
        'supplement_logs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('supplement_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('time_of_day', sa.String(length=5), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(
            ['supplement_id'], ['supplements.id'], ondelete='CASCADE'
        ),
        sa.PrimaryKeyConstraint('id'),
    )
    # Unique: one tick per dose per day, which is what makes the write
    # idempotent rather than duplicable.
    op.create_index(
        'uq_supplement_logs_user_supp_date_time', 'supplement_logs',
        ['user_id', 'supplement_id', 'date', 'time_of_day'], unique=True,
    )


def downgrade() -> None:
    # Logs first: they carry the FK into supplements, and dropping the parent
    # while a child table still references it fails on Postgres.
    op.drop_index(
        'uq_supplement_logs_user_supp_date_time', table_name='supplement_logs'
    )
    op.drop_table('supplement_logs')
    op.drop_index('uq_supplements_user_lower_name', table_name='supplements')
    op.drop_table('supplements')
