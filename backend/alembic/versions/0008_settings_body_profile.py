"""settings body profile and targets_auto

Revision ID: 0008
Revises: 0007
Create Date: 2026-08-20

The body profile behind the calorie/BMI calculator. Five nullable columns plus
one boolean flag, all on the existing `settings` row rather than a new table:
there is exactly one profile per account, `settings` is already keyed by
user_id alone, and a second 1:1 table would buy a join every read for nothing.

`birth_date` stores the date, not an age. An age column is right until the
user's next birthday and quietly wrong for the year after, and nothing in the
system would notice.

`targets_auto` is NOT NULL and therefore carries a server_default, the same way
`weight_unit` did in 0004 -- existing rows all predate the flag and must
backfill to "off", which is the behaviour they already have.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0008'
down_revision: str | None = '0007'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Nullable, so no backfill is needed: an account with no profile set reads
    # NULL everywhere and the calculator simply reports what is missing.
    op.add_column('settings', sa.Column('height_cm', sa.Float(), nullable=True))
    op.add_column('settings', sa.Column('birth_date', sa.Date(), nullable=True))
    op.add_column('settings', sa.Column('sex', sa.String(length=6), nullable=True))
    op.add_column(
        'settings', sa.Column('activity_level', sa.String(length=12), nullable=True)
    )
    op.add_column(
        'settings', sa.Column('goal_rate_kg_per_week', sa.Float(), nullable=True)
    )
    # server_default backfills existing rows to "off", which is what they do
    # today: goals stay whatever the user typed.
    op.add_column(
        'settings',
        sa.Column(
            'targets_auto',
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )

    # Added separately, as in 0004: SQLite cannot ALTER a table to add a CHECK,
    # so batch_alter_table rebuilds it there. On Postgres -- the only dialect
    # that ever runs these migrations, since SQLite's schema comes from
    # create_all -- batch mode emits a plain ALTER TABLE ADD CONSTRAINT.
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.create_check_constraint('ck_settings_sex', "sex IN ('male', 'female')")
        batch_op.create_check_constraint(
            'ck_settings_activity_level',
            "activity_level IN "
            "('sedentary', 'light', 'moderate', 'active', 'very_active')",
        )


def downgrade() -> None:
    # Dropping these loses the body profile outright -- height, birth date, sex,
    # activity level and goal rate are only stored here. The four daily goals
    # survive at whatever value they last held, which for a targets_auto
    # account is the last computed set rather than anything the user typed.
    with op.batch_alter_table('settings', schema=None) as batch_op:
        batch_op.drop_constraint('ck_settings_activity_level', type_='check')
        batch_op.drop_constraint('ck_settings_sex', type_='check')
        batch_op.drop_column('targets_auto')
        batch_op.drop_column('goal_rate_kg_per_week')
        batch_op.drop_column('activity_level')
        batch_op.drop_column('sex')
        batch_op.drop_column('birth_date')
        batch_op.drop_column('height_cm')
