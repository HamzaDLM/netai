from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.models.skills import Skill
from app.api.models.users import User
from app.db.init_db import init_db


@pytest.mark.anyio
async def test_init_db_seeds_demo_user_and_example_skills(
    test_db_session_factory,
) -> None:
    await init_db(test_db_session_factory)
    await init_db(test_db_session_factory)

    async with test_db_session_factory() as db:
        user_result = await db.execute(select(User).where(User.id == 0))
        user = user_result.scalar_one_or_none()
        assert user is not None
        assert user.username == "testuser"

        skill_result = await db.execute(
            select(Skill)
            .where(Skill.user_id == 0)
            .order_by(Skill.created_at.asc(), Skill.id.asc())
        )
        skills = skill_result.scalars().all()

    assert [skill.name for skill in skills] == [
        "WAN Flap Triage",
        "Network Change Impact Correlation",
    ]
    assert all(skill.enabled is True for skill in skills)
