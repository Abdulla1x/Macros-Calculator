"""password_resets table

Revision ID: 0005
Revises: 0004
Create Date: 2026-08-04

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0005'
down_revision: str | None = '0004'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'password_resets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        # SHA-256 hex of the emailed token; see models.PasswordReset for why
        # this is not a password hash.
        sa.Column('token_hash', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
        sa.Column('used_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
    )
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.create_index('ix_password_resets_user_id', ['user_id'])
        batch_op.create_index(
            'uq_password_resets_token_hash', ['token_hash'], unique=True
        )


def downgrade() -> None:
    with op.batch_alter_table('password_resets', schema=None) as batch_op:
        batch_op.drop_index('uq_password_resets_token_hash')
        batch_op.drop_index('ix_password_resets_user_id')
    op.drop_table('password_resets')
