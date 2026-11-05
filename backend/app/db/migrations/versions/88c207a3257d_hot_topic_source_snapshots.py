"""hot topic source snapshots

Revision ID: 88c207a3257d
Revises: e2e61ca05ac9
Create Date: 2026-11-05 23:17:42.800438
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "88c207a3257d"
down_revision: str | None = "e2e61ca05ac9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "hot_topics",
        sa.Column(
            "sources",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.alter_column("hot_topics", "sources", server_default=None)


def downgrade() -> None:
    op.drop_column("hot_topics", "sources")
