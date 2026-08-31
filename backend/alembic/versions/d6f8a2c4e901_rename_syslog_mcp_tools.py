"""rename syslog MCP tool identifiers

Revision ID: d6f8a2c4e901
Revises: c7e1a4b9d230
Create Date: 2026-08-31 12:00:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "d6f8a2c4e901"
down_revision: str | Sequence[str] | None = "c7e1a4b9d230"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

UPGRADE_TOOL_NAMES = {
    "syslog_get_host_syslogs": "syslog_get_device_events",
    "logs_get_device_events": "syslog_get_device_events",
    "logs_get_severity_summary": "syslog_get_severity_summary",
    "logs_get_event_summary": "syslog_get_event_summary",
}
DOWNGRADE_TOOL_NAMES = {
    "syslog_get_device_events": "logs_get_device_events",
    "syslog_get_severity_summary": "logs_get_severity_summary",
    "syslog_get_event_summary": "logs_get_event_summary",
}


def _rename_tools(names: dict[str, str]) -> None:
    scenarios = sa.table(
        "eval_scenario",
        sa.column("id", sa.String()),
        sa.column("required_tools", sa.JSON()),
        sa.column("forbidden_tools", sa.JSON()),
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(
                scenarios.c.id,
                scenarios.c.required_tools,
                scenarios.c.forbidden_tools,
            )
        )
        .mappings()
        .all()
    )

    for row in rows:
        required_tools = [
            names.get(tool, tool) for tool in (row["required_tools"] or [])
        ]
        forbidden_tools = [
            names.get(tool, tool) for tool in (row["forbidden_tools"] or [])
        ]
        if (
            required_tools == row["required_tools"]
            and forbidden_tools == row["forbidden_tools"]
        ):
            continue
        connection.execute(
            sa.update(scenarios)
            .where(scenarios.c.id == row["id"])
            .values(
                required_tools=required_tools,
                forbidden_tools=forbidden_tools,
            )
        )


def upgrade() -> None:
    _rename_tools(UPGRADE_TOOL_NAMES)


def downgrade() -> None:
    _rename_tools(DOWNGRADE_TOOL_NAMES)
