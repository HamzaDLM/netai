from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.skills import Skill
from app.api.models.users import User, UserRole
from app.db.session import SessionLocal

DEMO_USER_ID = 0
DEMO_USERNAME = "testuser"

DEFAULT_SKILL_BLUEPRINTS: Sequence[dict[str, str | bool]] = (
    {
        "name": "WAN Flap Triage",
        "description": (
            "Investigate branch packet loss, interface flaps, and routing instability "
            "with monitoring, syslog, and control-plane evidence."
        ),
        "instructions": """
When the user mentions packet loss, WAN instability, interface flaps, tunnel resets, or branch brownouts:

- Prioritize `zabbix_specialist`, `syslog_specialist`, and `suzieq_specialist`.
- Use Zabbix to confirm the affected hosts, recent problems, interface health, metrics, and the event timeline.
- Use syslog to pull matching link-down, interface, BGP, or error patterns for the same device and time window.
- Use SuzieQ to validate interface state, control-plane health, and whether BGP or OSPF adjacencies are unstable.
- If the hostname or site is ambiguous, resolve that first instead of guessing.
- Return the likely root cause, impacted devices or interfaces, when the issue started, whether it is still active, and 3-5 evidence bullets tied to tool output.
""".strip(),
        "enabled": True,
    },
    {
        "name": "Network Change Impact Correlation",
        "description": (
            "Correlate outages with recent config changes, topology blast radius, "
            "monitoring alarms, and ITSM records."
        ),
        "instructions": """
When the user asks whether a change caused an outage or wants blast-radius analysis:

- Prioritize `bitbucket_specialist`, `datamodel_specialist`, `servicenow_specialist`, and `zabbix_specialist`.
- Use Bitbucket to identify recent device configuration diffs, commit timing, and affected devices.
- Use the datamodel specialist to map neighbors, links, and the likely blast radius around the changed device.
- Use Zabbix to confirm whether alerts or host problems started after the change window and which devices are impacted.
- Use ServiceNow to find matching incidents, problems, or change records and include their IDs when relevant.
- Return a concise timeline with change time, first symptom time, impacted infrastructure, and whether the evidence supports causation or only loose correlation.
""".strip(),
        "enabled": True,
    },
)


async def _ensure_demo_user(db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == DEMO_USER_ID))
    user = result.scalar_one_or_none()
    if user is not None:
        return user

    user = User(
        id=DEMO_USER_ID,
        username=DEMO_USERNAME,
        role=UserRole.admin,
    )
    db.add(user)
    await db.flush()
    return user


async def init_db(
    session_factory: async_sessionmaker[AsyncSession] = SessionLocal,
) -> None:
    async with session_factory() as db:
        user = await _ensure_demo_user(db)

        existing_name_result = await db.execute(
            select(func.lower(Skill.name)).where(Skill.user_id == user.id)
        )
        existing_names = {
            name
            for name in existing_name_result.scalars().all()
            if isinstance(name, str)
        }

        for skill in DEFAULT_SKILL_BLUEPRINTS:
            name = str(skill["name"]).strip()
            if name.lower() in existing_names:
                continue

            db.add(
                Skill(
                    user_id=user.id,
                    name=name,
                    description=str(skill["description"]).strip(),
                    instructions=str(skill["instructions"]).strip(),
                    enabled=bool(skill.get("enabled", True)),
                )
            )

        await db.commit()
