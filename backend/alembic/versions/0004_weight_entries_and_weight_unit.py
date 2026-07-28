"""weights table and settings.weight_unit

Revision ID: 0004
Revises: 0003
Create Date: 2026-07-28

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0004'
down_revision: str | None = '0003'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'weights',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('date', sa.Date(), nullable=False),
        sa.Column('weight_kg', sa.Float(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('weights', schema=None) as batch_op:
        batch_op.create_index(
            'uq_weights_user_date', ['user_id', 'date'], unique=True
        )

    # server_default backfills existing rows, which all predate the preference.
    op.add_column(
        'settings',
        sa.Column(
            'weight_unit',
            sa.String(length=2),
            nullable=False,
            server_default='kg',
        ),
    )
    # Added separately: SQLite cannot ALTER a table to add a CHECK, so on that
    # dialect batch_alter_table rebuilds the table with the constraint in place.
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.create_check_constraint(
            'ck_settings_weight_unit', "weight_unit IN ('kg', 'lb')"
        )


def downgrade() -> None:
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_constraint('ck_settings_weight_unit', type_='check')
        batch_op.drop_column('weight_unit')

    with op.batch_alter_table('weights', schema=None) as batch_op:
        batch_op.drop_index('uq_weights_user_date')
    op.drop_table('weights')
