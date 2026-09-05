"""AI timing: ai_analyses.provider_ms + .server_uptime_s

Revision ID: 0015
Revises: 0014
Create Date: 2026-09-05

Two nullable columns on an existing table, so the six-item column checklist
applies rather than the eleven-item one for a new table.

Both are NULLABLE and neither has a server_default, which is the whole design:

* Existing rows were written before anything was timed, and a 0 would be a
  *measurement of zero milliseconds* rather than an absence of one. It would
  drag every median down silently. Same argument keep_warm makes for reporting
  longest_scheduler_gap_seconds as None rather than 0 before two pings exist.

* A call refunded before inference has its row DELETED, so it contributes no
  timing at all. This column therefore describes calls that reached the model,
  not calls that were attempted -- see models.py.

`provider_ms` is named for what it times and not for the row it sits on. On a
table called ai_analyses a name like `duration_ms` would read as "how long the
analysis took", which is the number the USER experiences and is emphatically
not this: it excludes the upload, the cold start, and the request handling
around it. It is also not `latency_ms`, which would imply comparability with
AIProbe.latency_ms -- that times one bare call, this times a call plus its
whole retry budget.

`server_uptime_s` exists because the cold start provably CANNOT be inside
provider_ms: the boot finishes before the handler runs, and Starlette has
already consumed the request body by then. A process that had been up eight
seconds when the call was made served a request that paid for a boot, and this
column is the only place that fact survives.

No index: the only query filters on created_at over a 30-day window, and the
table's hard ceiling is AI_GLOBAL_DAILY_LIMIT rows per day.

No batch_alter_table: nothing existing is rebuilt, only added to.

"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op


revision: str = '0015'
down_revision: str | None = '0014'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column('ai_analyses', sa.Column('provider_ms', sa.Integer(), nullable=True))
    op.add_column(
        'ai_analyses', sa.Column('server_uptime_s', sa.Integer(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('ai_analyses', 'server_uptime_s')
    op.drop_column('ai_analyses', 'provider_ms')
