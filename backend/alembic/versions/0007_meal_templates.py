"""meal_templates table

Revision ID: 0007
Revises: 0006
Create Date: 2026-08-15

A saved meal the user can re-log in one tap. `items_json` holds the ingredient
rows as serialized JSON rather than a child table: nothing queries by
ingredient, so the rows are read whole or not at all, which is the same reason
ai_analyses stores its payload that way.

`created_at` is NOT NULL with no server_default, matching weights in 0004. That
is only safe because the table is new and therefore empty -- there are no
existing rows to leave without a value.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0007'
down_revision: str | None = '0006'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'meal_templates',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False),
        sa.Column('calories', sa.Float(), nullable=False),
        sa.Column('protein', sa.Float(), nullable=False),
        sa.Column('carbs', sa.Float(), nullable=True),
        sa.Column('fat', sa.Float(), nullable=True),
        # Nullable: a template saved while editing an existing meal has only a
        # pass-through row, so "totals but no items" is a valid template.
        sa.Column('items_json', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    # Expression index, so it goes at top level rather than inside
    # batch_alter_table -- batch mode cannot express one. Same hand-written
    # shape as uq_foods_user_lower_name in 0001; autogenerate cannot emit it.
    op.create_index(
        'uq_meal_templates_user_lower_name', 'meal_templates',
        ['user_id', sa.text('lower(name)')], unique=True,
    )


def downgrade() -> None:
    op.drop_index('uq_meal_templates_user_lower_name', table_name='meal_templates')
    op.drop_table('meal_templates')
