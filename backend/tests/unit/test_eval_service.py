from __future__ import annotations

from typing import cast

import pytest
from haystack.components.generators.chat.types import ChatGenerator
from haystack.dataclasses import ChatMessage
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.api.models.evals import (
    EvalEvaluator,
    EvalEvaluatorKind,
    EvalEvaluatorRule,
    EvalRunStatus,
    EvalScenario,
)
from app.api.models.users import User, UserRole
from app.core.config import project_settings
from app.services.agent_events import RunObserver, ToolExecution
from app.services.evals import EvalService
from app.services.netai import NetAIRun, NetAIService


class FakeJudgeGenerator:
    async def warm_up_async(self) -> None:
        pass

    async def close_async(self) -> None:
        pass

    async def run_async(
        self,
        *,
        messages: list[ChatMessage],
        **_: object,
    ) -> dict[str, object]:
        assert messages
        return {
            "replies": [
                ChatMessage.from_assistant(
                    '{"score": 91, "reasoning": "The answer matches the evidence."}'
                )
            ]
        }


class FakeNetAIService:
    def __init__(self, result: NetAIRun) -> None:
        self.result = result
        self.calls: list[dict[str, object]] = []

    async def run(self, **kwargs: object) -> NetAIRun:
        self.calls.append(kwargs)
        return self.result


@pytest.mark.anyio
async def test_eval_service_runs_agent_and_scores_recorded_behavior(
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    observer = RunObserver(run_id="agent-run", conversation_id="eval")
    observer.tool_executions.append(
        ToolExecution(
            call_id="call-1",
            tool_name="zabbix_get_problems",
            connector="zabbix",
            input_params={"host": "edge-1"},
            started_at=0,
            status="success",
            latency_ms=42,
            output={"problems": ["BGP peer down"]},
        )
    )
    agent_result = NetAIRun(
        answer="The BGP peer is down according to Zabbix.",
        duration_ms=120,
        result={"step_count": 2},
        observer=observer,
    )
    runtime = FakeNetAIService(agent_result)
    service = EvalService(
        settings=project_settings,
        netai_service=cast(NetAIService, runtime),
        judge_generator=cast(ChatGenerator, FakeJudgeGenerator()),
    )

    async with test_db_session_factory() as db:
        db.add(User(id=10, username="admin", role=UserRole.admin))
        trajectory = EvalEvaluator(
            id="trajectory",
            created_by_user_id=10,
            name="Trajectory",
            kind=EvalEvaluatorKind.deterministic,
            rule=EvalEvaluatorRule.tool_trajectory,
            description="",
            criteria="Required tools must succeed.",
            threshold=100,
            builtin=True,
        )
        judge = EvalEvaluator(
            id="judge",
            created_by_user_id=10,
            name="Groundedness",
            kind=EvalEvaluatorKind.llm_judge,
            rule=EvalEvaluatorRule.llm_judge,
            description="",
            criteria="Claims must match evidence.",
            threshold=85,
            builtin=True,
        )
        scenario = EvalScenario(
            id="scenario-1",
            created_by_user_id=10,
            owner_name="admin",
            name="BGP investigation",
            description="",
            prompt="Why is edge-1 unhealthy?",
            fixture="Expected BGP alarm",
            required_tools=["zabbix_get_problems"],
            forbidden_tools=[],
            expected_facts=["BGP peer down"],
            evaluator_ids=[trajectory.id, judge.id],
        )
        db.add_all([trajectory, judge, scenario])
        await db.commit()
        # Match the production session's default and guard against implicit
        # lazy loads after EvalService commits its initial running row.
        db.sync_session.expire_on_commit = True

        eval_run = await service.execute(
            db=db,
            scenario=scenario,
            evaluators=[trajectory, judge],
            user_id=10,
            request_id="request-1",
        )

    assert eval_run.status == EvalRunStatus.passed
    assert eval_run.score == 95.5
    assert [check["score"] for check in eval_run.checks] == [100, 91]
    assert eval_run.tool_calls[0]["expectation"] == "required"
    assert runtime.calls[0]["conversation_id"] == f"eval:{eval_run.id}"


@pytest.mark.anyio
async def test_eval_service_fails_missing_required_tool(
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    observer = RunObserver(run_id="agent-run", conversation_id="eval")
    runtime = FakeNetAIService(
        NetAIRun(
            answer="No evidence found.", duration_ms=25, result={}, observer=observer
        )
    )
    service = EvalService(
        settings=project_settings,
        netai_service=cast(NetAIService, runtime),
        judge_generator=cast(ChatGenerator, FakeJudgeGenerator()),
    )
    async with test_db_session_factory() as db:
        db.add(User(id=11, username="admin", role=UserRole.admin))
        evaluator = EvalEvaluator(
            id="trajectory",
            created_by_user_id=11,
            name="Trajectory",
            kind=EvalEvaluatorKind.deterministic,
            rule=EvalEvaluatorRule.tool_trajectory,
            description="",
            criteria="Required tools must succeed.",
            threshold=100,
            builtin=True,
        )
        scenario = EvalScenario(
            id="scenario-2",
            created_by_user_id=11,
            owner_name="admin",
            name="Missing evidence",
            description="",
            prompt="Check edge-1.",
            fixture="",
            required_tools=["zabbix_get_problems"],
            forbidden_tools=[],
            expected_facts=[],
            evaluator_ids=[evaluator.id],
        )
        db.add_all([evaluator, scenario])
        await db.commit()

        eval_run = await service.execute(
            db=db,
            scenario=scenario,
            evaluators=[evaluator],
            user_id=11,
            request_id="request-2",
        )

    assert eval_run.status == EvalRunStatus.failed
    assert eval_run.score == 0
    assert "Missing successful required tools" in str(eval_run.checks[0]["detail"])
