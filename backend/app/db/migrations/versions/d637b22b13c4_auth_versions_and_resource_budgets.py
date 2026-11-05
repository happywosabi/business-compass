"""auth versions and resource budgets

Revision ID: d637b22b13c4
Revises: 88c207a3257d
Create Date: 2026-11-06 01:48:45.851837
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d637b22b13c4"
down_revision: str | None = "88c207a3257d"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "hot_collection_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("model", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.Text(), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("embedding_tokens", sa.Integer(), nullable=False),
        sa.Column("llm_calls", sa.Integer(), nullable=False),
        sa.Column("embedding_calls", sa.Integer(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_hot_collection_runs")),
    )
    op.create_table(
        "calculation_runs",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_calculation_runs_user_id_users"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_calculation_runs")),
    )
    op.create_index(
        op.f("ix_calculation_runs_user_id_created_at"),
        "calculation_runs",
        ["user_id", "created_at"],
        unique=False,
    )
    op.add_column(
        "email_tokens",
        sa.Column("password_version", sa.Integer(), server_default="1", nullable=False),
    )
    op.add_column(
        "sessions", sa.Column("password_version", sa.Integer(), server_default="1", nullable=False)
    )
    op.add_column(
        "users", sa.Column("password_version", sa.Integer(), server_default="1", nullable=False)
    )
    # 旧会话/重置令牌没有密码版本依据，升级时失效，避免保留修复前竞争签发的会话。
    op.execute("DELETE FROM sessions")
    op.execute(
        "UPDATE email_tokens SET used_at = now() WHERE purpose = 'reset_password' AND used_at IS NULL"
    )


def downgrade() -> None:
    op.drop_column("users", "password_version")
    op.drop_column("sessions", "password_version")
    op.drop_column("email_tokens", "password_version")
    op.drop_index(op.f("ix_calculation_runs_user_id_created_at"), table_name="calculation_runs")
    op.drop_table("calculation_runs")
    op.drop_table("hot_collection_runs")
