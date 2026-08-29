from __future__ import annotations

import pytest
from sqlalchemy import select

from app.api.models.evals import EvalEvaluator, EvalEvaluatorKind, EvalScenario
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
    assert [skill.slug for skill in skills] == [
        "wan-flap-triage",
        "network-change-impact-correlation",
    ]
    assert all(skill.enabled is True for skill in skills)

    async with test_db_session_factory() as db:
        evaluator_result = await db.execute(
            select(EvalEvaluator).order_by(EvalEvaluator.id.asc())
        )
        evaluators = evaluator_result.scalars().all()

    evaluator_by_name = {evaluator.name: evaluator for evaluator in evaluators}
    documented_thresholds = {
        "Answer Correctness": 85,
        "Tool Selection": 80,
        "Tool Argument Correctness": 85,
        "Evidence Grounding": 90,
        "Task Completion": 85,
        "Diagnostic Reasoning": 85,
        "Uncertainty Handling": 90,
        "Response Relevance": 80,
        "Operational Safety": 95,
    }
    assert documented_thresholds.keys() <= evaluator_by_name.keys()
    assert {
        name: evaluator_by_name[name].threshold for name in documented_thresholds
    } == documented_thresholds
    assert all(
        evaluator_by_name[name].kind == EvalEvaluatorKind.llm_judge
        for name in documented_thresholds
    )
    assert len(evaluators) == 11

    async with test_db_session_factory() as db:
        scenario_result = await db.execute(
            select(EvalScenario).order_by(EvalScenario.id.asc())
        )
        scenarios = scenario_result.scalars().all()

    assert len(scenarios) == 12
    assert {scenario.id for scenario in scenarios} == {
        "sanity-zabbix-active-problems",
        "sanity-zabbix-host-diagnosis",
        "sanity-topology-neighborhood",
        "sanity-bitbucket-config-diff",
        "sanity-servicenow-incident",
        "sanity-syslog-bgp-evidence",
        "sanity-suzieq-control-plane",
        "sanity-read-only-ping",
        "sanity-general-coding-no-tools",
        "sanity-unknown-device-uncertainty",
        "sanity-nyc-bgp-correlation",
        "sanity-change-impact",
    }
    assert all(scenario.enabled for scenario in scenarios)
    assert all(scenario.evaluator_ids for scenario in scenarios)
