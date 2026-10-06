"""foods.source accepts the five reference food tables

Revision ID: 0018
Revises: 0017
Create Date: 2026-10-06

A food picked from an imported national table (USDA, UK CoFID, France Ciqual,
Australia AFCD, Canada CNF -- see app/reference_foods.py) and saved to the
library keeps that table as its badge. Without this, the only honest value
would have been 'user', which claims the numbers are the user's own -- the
same dead end lib/libraryMatch.ts documents for saved AI items.

Only the CHECK changes. The reference data itself is NOT in the database: it
ships as CSVs inside the app and is searched in memory, so there is no table
here and nothing to bulk-load on deploy.

⚠️ SQLite rebuilds the table to change a CHECK (batch mode), and SQLAlchemy
cannot reflect an expression index, so the rebuild silently drops
uq_foods_user_lower_name. It is re-created explicitly below. Postgres alters
the constraint in place and keeps the index.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0018'
down_revision: str | None = '0017'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

OLD = "source IN ('user', 'openfoodfacts')"
NEW = "source IN ('user', 'openfoodfacts', 'usda', 'cofid', 'ciqual', 'afcd', 'cnf')"


def _replace_check(condition: str) -> None:
    if op.get_bind().dialect.name != 'sqlite':
        op.drop_constraint('ck_foods_source', 'foods', type_='check')
        op.create_check_constraint('ck_foods_source', 'foods', condition)
        return
    with op.batch_alter_table('foods', recreate='always') as batch_op:
        batch_op.drop_constraint('ck_foods_source', type_='check')
        batch_op.create_check_constraint('ck_foods_source', condition)
    # The rebuild ALWAYS loses the expression index (see the module docstring),
    # so it is re-created unconditionally. Not "if missing": SQLAlchemy cannot
    # see an expression index on SQLite at all, so that check is always true
    # and would only read as if it were testing something.
    op.create_index(
        'uq_foods_user_lower_name', 'foods',
        ['user_id', sa.text('lower(name)')], unique=True,
    )


def upgrade() -> None:
    _replace_check(NEW)


def downgrade() -> None:
    # A row saved from a reference table would violate the old CHECK. 'user' is
    # the value the app itself gives a row whose provenance it can't vouch for
    # (routers/foods.py:update_food), so that is what they become.
    op.execute(
        "UPDATE foods SET source = 'user' "
        "WHERE source NOT IN ('user', 'openfoodfacts')"
    )
    _replace_check(OLD)
