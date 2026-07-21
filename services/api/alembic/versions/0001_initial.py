"""Initial public schema tables.

Revision ID: 0001_initial
Revises:
Create Date: 2026-07-20

"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0001_initial"
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "plugins",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("framework_version", sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_plugins")),
    )
    op.create_table(
        "test_definitions",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("steps_csv", sa.Text(), nullable=False),
        sa.Column("plugin_id", sa.String(length=128), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_test_definitions")),
    )
    op.create_table(
        "scenarios",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("name", sa.String(length=256), nullable=False),
        sa.Column("test_ids_csv", sa.Text(), nullable=False),
        sa.Column("sut_version", sa.String(length=128), nullable=False),
        sa.Column("history_max_runs", sa.Integer(), nullable=True),
        sa.Column("history_max_days", sa.Integer(), nullable=True),
        sa.Column("artifact_max_runs", sa.Integer(), nullable=True),
        sa.Column("artifact_max_days", sa.Integer(), nullable=True),
        sa.Column("artifact_keep_failed_only", sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_scenarios")),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("sut_version", sa.String(length=128), nullable=False),
        sa.Column("framework_version", sa.String(length=64), nullable=False),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["scenario_id"],
            ["scenarios.id"],
            name=op.f("fk_runs_scenario_id_scenarios"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_runs")),
    )
    op.create_index(op.f("ix_runs_scenario_id"), "runs", ["scenario_id"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("test_id", sa.String(length=128), nullable=True),
        sa.Column("step_id", sa.String(length=128), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=True),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("error_trace", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("artifacts_json", sa.Text(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("contracts_version", sa.String(length=32), nullable=False),
        sa.ForeignKeyConstraint(
            ["run_id"],
            ["runs.id"],
            name=op.f("fk_run_events_run_id_runs"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_run_events")),
    )
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"], unique=False)

    op.create_table(
        "fingerprint_occurrences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=False),
        sa.Column("run_id", sa.String(length=128), nullable=False),
        sa.Column("fingerprint", sa.String(length=32), nullable=False),
        sa.Column("label", sa.Text(), nullable=False),
        sa.Column("test_id", sa.String(length=128), nullable=False),
        sa.Column("step_id", sa.String(length=128), nullable=False),
        sa.Column("sut_version", sa.String(length=128), nullable=False),
        sa.Column("framework_version", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_fingerprint_occurrences")),
    )
    op.create_index(
        op.f("ix_fingerprint_occurrences_scenario_id"),
        "fingerprint_occurrences",
        ["scenario_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fingerprint_occurrences_run_id"),
        "fingerprint_occurrences",
        ["run_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_fingerprint_occurrences_fingerprint"),
        "fingerprint_occurrences",
        ["fingerprint"],
        unique=False,
    )

    op.create_table(
        "analysis_reports",
        sa.Column("id", sa.String(length=128), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("scenario_id", sa.String(length=128), nullable=True),
        sa.Column("run_id", sa.String(length=128), nullable=True),
        sa.Column("test_id", sa.String(length=128), nullable=True),
        sa.Column("fingerprint", sa.String(length=32), nullable=True),
        sa.Column("report_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_analysis_reports")),
    )
    op.create_index(op.f("ix_analysis_reports_scenario_id"), "analysis_reports", ["scenario_id"], unique=False)
    op.create_index(op.f("ix_analysis_reports_run_id"), "analysis_reports", ["run_id"], unique=False)
    op.create_index(op.f("ix_analysis_reports_test_id"), "analysis_reports", ["test_id"], unique=False)
    op.create_index(op.f("ix_analysis_reports_fingerprint"), "analysis_reports", ["fingerprint"], unique=False)


def downgrade() -> None:
    op.drop_table("analysis_reports")
    op.drop_table("fingerprint_occurrences")
    op.drop_table("run_events")
    op.drop_table("runs")
    op.drop_table("scenarios")
    op.drop_table("test_definitions")
    op.drop_table("plugins")
