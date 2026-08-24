"""End-to-end evaluation runtime for administrator-authored Agent scenarios."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
from datetime import datetime, timezone
from uuid import uuid4

from haystack.components.evaluators import LLMEvaluator
from haystack.components.generators.chat.types import ChatGenerator
from haystack.dataclasses import ChatMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.models.evals import (
    EvalEvaluator,
    EvalEvaluatorRule,
    EvalRun,
    EvalRunStatus,
    EvalScenario,
)
from app.core.config import Settings
from app.core.version import get_backend_git_sha, get_backend_version
from app.services.netai import NetAIRun, NetAIService, create_chat_generator

logger = logging.getLogger(__name__)


def _bounded_text(value: object, limit: int = 2_000) -> str:
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, default=str, ensure_ascii=False)
        except TypeError:
            text = str(value)
    return text if len(text) <= limit else f"{text[:limit]}…"


class EvalService:
    """Run the production Agent and score its observable behavior."""

    def __init__(
        self,
        *,
        settings: Settings,
        netai_service: NetAIService,
        judge_generator: ChatGenerator | None = None,
    ) -> None:
        self.settings = settings
        self.netai_service = netai_service
        self.judge_generator = judge_generator or create_chat_generator(
            settings,
            generation_kwargs={
                "temperature": 0,
                "response_mime_type": "application/json",
            },
        )

    async def warm_up(self) -> None:
        warm_up_async = getattr(self.judge_generator, "warm_up_async", None)
        if callable(warm_up_async):
            await warm_up_async()
            return
        warm_up = getattr(self.judge_generator, "warm_up", None)
        if callable(warm_up):
            result = warm_up()
            if inspect.isawaitable(result):
                await result

    async def close(self) -> None:
        close_async = getattr(self.judge_generator, "close_async", None)
        if callable(close_async):
            await close_async()
            return
        close = getattr(self.judge_generator, "close", None)
        if callable(close):
            result = close()
            if inspect.isawaitable(result):
                await result

    @staticmethod
    def _tool_calls(
        agent_run: NetAIRun, scenario: EvalScenario
    ) -> list[dict[str, object]]:
        required = set(scenario.required_tools)
        forbidden = set(scenario.forbidden_tools)
        calls: list[dict[str, object]] = []
        for execution in agent_run.observer.tool_executions:
            if execution.connector == "internal":
                continue
            expectation = "allowed"
            if execution.tool_name in required:
                expectation = "required"
            elif execution.tool_name in forbidden:
                expectation = "unexpected"
            calls.append(
                {
                    "id": execution.call_id,
                    "name": execution.tool_name,
                    "connector": execution.connector,
                    "status": execution.status,
                    "expectation": expectation,
                    "duration_ms": execution.latency_ms or 0,
                    "summary": _bounded_text(
                        execution.output
                        if execution.status == "success"
                        else execution.error_message or execution.output
                    ),
                }
            )
        return calls

    @staticmethod
    def _tool_trajectory_check(
        evaluator: EvalEvaluator,
        scenario: EvalScenario,
        calls: list[dict[str, object]],
    ) -> dict[str, object]:
        successful = {
            str(call["name"]) for call in calls if call.get("status") == "success"
        }
        invoked = {str(call["name"]) for call in calls}
        missing = sorted(set(scenario.required_tools) - successful)
        forbidden = sorted(set(scenario.forbidden_tools) & invoked)
        passed = not missing and not forbidden
        details: list[str] = []
        if missing:
            details.append(f"Missing successful required tools: {', '.join(missing)}.")
        if forbidden:
            details.append(f"Forbidden tools invoked: {', '.join(forbidden)}.")
        if passed:
            details.append(
                "All required tools succeeded and no forbidden tool was invoked."
            )
        return {
            "id": f"check_{uuid4().hex}",
            "name": evaluator.name,
            "kind": evaluator.kind.value,
            "status": "passed" if passed else "failed",
            "score": 100 if passed else 0,
            "detail": " ".join(details),
        }

    @staticmethod
    def _completion_check(
        evaluator: EvalEvaluator,
        agent_run: NetAIRun,
        calls: list[dict[str, object]],
    ) -> dict[str, object]:
        failures: list[str] = []
        if not agent_run.answer.strip():
            failures.append("No final answer was produced.")
        if len(calls) > 10:
            failures.append(
                f"The run used {len(calls)} infrastructure calls (limit: 10)."
            )
        passed = not failures
        return {
            "id": f"check_{uuid4().hex}",
            "name": evaluator.name,
            "kind": evaluator.kind.value,
            "status": "passed" if passed else "failed",
            "score": 100 if passed else 0,
            "detail": " ".join(failures)
            if failures
            else f"A final answer was produced in {len(calls)} read-only infrastructure calls.",
        }

    async def _judge_check(
        self,
        evaluator: EvalEvaluator,
        scenario: EvalScenario,
        agent_run: NetAIRun,
        calls: list[dict[str, object]],
    ) -> dict[str, object]:
        evaluator_component = LLMEvaluator(
            instructions=(
                "Evaluate the NetAI answer using the supplied rubric. Use only the "
                "recorded tool evidence and reference expectations. Return an integer "
                "score from 0 to 100 and concise reasoning. Rubric: "
                f"{evaluator.criteria}"
            ),
            inputs=[
                ("questions", list[str]),
                ("answers", list[str]),
                ("reference_contexts", list[str]),
                ("tool_evidence", list[str]),
            ],
            outputs=["score", "reasoning"],
            examples=[
                {
                    "inputs": {
                        "questions": "Why is the route absent?",
                        "answers": "The peer is down, as confirmed by routing evidence.",
                        "reference_contexts": "Expected: peer is down.",
                        "tool_evidence": "routing_peer: peer state is down",
                    },
                    "outputs": {
                        "score": 100,
                        "reasoning": "The conclusion is fully supported by the evidence.",
                    },
                }
            ],
            progress_bar=False,
            raise_on_failure=False,
            chat_generator=self.judge_generator,
        )
        evidence = json.dumps(calls, ensure_ascii=False)
        reference = json.dumps(
            {
                "fixture_notes": scenario.fixture,
                "expected_facts": scenario.expected_facts,
            },
            ensure_ascii=False,
        )
        result = await evaluator_component.run_async(
            questions=[scenario.prompt],
            answers=[agent_run.answer],
            reference_contexts=[reference],
            tool_evidence=[evidence],
        )
        results = result.get("results")
        judged = results[0] if isinstance(results, list) and results else None
        if not isinstance(judged, dict):
            return {
                "id": f"check_{uuid4().hex}",
                "name": evaluator.name,
                "kind": evaluator.kind.value,
                "status": "warning",
                "score": 0,
                "detail": "The LLM judge did not return a valid structured result.",
            }
        raw_score = judged.get("score", 0)
        try:
            score = max(0, min(100, int(round(float(raw_score)))))
        except (TypeError, ValueError):
            score = 0
        passed = score >= evaluator.threshold
        return {
            "id": f"check_{uuid4().hex}",
            "name": evaluator.name,
            "kind": evaluator.kind.value,
            "status": "passed" if passed else "failed",
            "score": score,
            "detail": _bounded_text(judged.get("reasoning", "No reasoning returned.")),
        }

    async def _evaluate(
        self,
        scenario: EvalScenario,
        evaluators: list[EvalEvaluator],
        agent_run: NetAIRun,
        calls: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        checks: list[dict[str, object]] = []
        for evaluator in evaluators:
            if evaluator.rule == EvalEvaluatorRule.tool_trajectory:
                checks.append(self._tool_trajectory_check(evaluator, scenario, calls))
            elif evaluator.rule == EvalEvaluatorRule.completion_safety:
                checks.append(self._completion_check(evaluator, agent_run, calls))
            else:
                checks.append(
                    await self._judge_check(evaluator, scenario, agent_run, calls)
                )
        return checks

    async def execute(
        self,
        *,
        db: AsyncSession,
        scenario: EvalScenario,
        evaluators: list[EvalEvaluator],
        user_id: int,
        request_id: str,
    ) -> EvalRun:
        """Persist and execute one scenario using NetAI's production Agent path."""

        now = datetime.now(timezone.utc)
        eval_run = EvalRun(
            id=f"run_{uuid4().hex}",
            scenario_id=scenario.id,
            created_by_user_id=user_id,
            status=EvalRunStatus.running,
            started_at=now,
            model=self.settings.GEMINI_MODEL,
            version=f"{get_backend_version()}@{get_backend_git_sha()}",
        )
        db.add(eval_run)
        await db.commit()
        # AsyncSession expires ORM attributes on commit by default. Reload every
        # object used during the long-running Agent call explicitly so later
        # attribute access never attempts implicit synchronous database I/O.
        await db.refresh(eval_run)
        await db.refresh(scenario)
        for evaluator in evaluators:
            await db.refresh(evaluator)

        logger.info(
            "evaluation run started",
            extra={
                "event": "eval.start",
                "eval_run_id": eval_run.id,
                "scenario_id": scenario.id,
            },
        )
        try:
            agent_run = await self.netai_service.run(
                messages=[ChatMessage.from_user(scenario.prompt)],
                conversation_id=f"eval:{eval_run.id}",
                user_id=user_id,
                request_id=request_id,
            )
            calls = self._tool_calls(agent_run, scenario)
            checks = await self._evaluate(scenario, evaluators, agent_run, calls)
            score = (
                round(
                    sum(int(str(check["score"])) for check in checks) / len(checks), 1
                )
                if checks
                else 0.0
            )
            eval_run.answer = agent_run.answer
            eval_run.duration_ms = agent_run.duration_ms
            eval_run.tool_calls = calls
            eval_run.checks = checks
            eval_run.score = score
            eval_run.status = (
                EvalRunStatus.passed
                if checks and all(check["status"] == "passed" for check in checks)
                else EvalRunStatus.failed
            )
        except asyncio.CancelledError:
            eval_run.status = EvalRunStatus.failed
            eval_run.score = 0
            eval_run.error = "Evaluation request was cancelled before completion."
            raise
        except Exception as exc:
            logger.exception(
                "evaluation run failed",
                extra={"event": "eval.failed", "eval_run_id": eval_run.id},
            )
            eval_run.status = EvalRunStatus.failed
            eval_run.score = 0
            eval_run.error = f"{type(exc).__name__}: {exc}"
        finally:
            eval_run.ended_at = datetime.now(timezone.utc)
            if eval_run.duration_ms is None:
                eval_run.duration_ms = max(
                    0,
                    int(
                        (eval_run.ended_at - eval_run.started_at).total_seconds() * 1000
                    ),
                )
            await db.commit()
            await db.refresh(eval_run)

        logger.info(
            "evaluation run finished",
            extra={
                "event": "eval.finish",
                "eval_run_id": eval_run.id,
                "status": eval_run.status.value,
                "score": eval_run.score,
            },
        )
        return eval_run
