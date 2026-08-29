"""Administrator APIs for end-to-end NetAI evaluations."""

from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import select

from app.api.deps import (
    AsyncSessionDep,
    CheckUserSSODep,
    EvalServiceDep,
    RequestIDDep,
)
from app.api.models.evals import EvalEvaluator, EvalRun, EvalScenario
from app.api.models.users import UserRole
from app.api.schemas.evals import (
    EvalEvaluatorCreate,
    EvalEvaluatorResponse,
    EvalEvaluatorUpdate,
    EvalRunResponse,
    EvalScenarioCreate,
    EvalScenarioResponse,
    EvalScenarioToggle,
    EvalScenarioUpdate,
)

router = APIRouter(prefix="/evals", tags=["evals"])


def _require_admin(role: UserRole) -> None:
    if role not in {UserRole.admin, UserRole.superuser}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN)


async def _active_evaluators(db: AsyncSessionDep) -> list[EvalEvaluator]:
    result = await db.execute(
        select(EvalEvaluator)
        .where(EvalEvaluator.archived.is_(False))
        .order_by(EvalEvaluator.builtin.desc(), EvalEvaluator.created_at.asc())
    )
    return list(result.scalars().all())


async def _scenario_or_404(db: AsyncSessionDep, scenario_id: str) -> EvalScenario:
    result = await db.execute(
        select(EvalScenario).where(
            EvalScenario.id == scenario_id,
            EvalScenario.archived.is_(False),
        )
    )
    scenario = result.scalar_one_or_none()
    if scenario is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    return scenario


async def _last_runs_by_scenario(db: AsyncSessionDep) -> dict[str, str]:
    result = await db.execute(select(EvalRun).order_by(EvalRun.created_at.desc()))
    latest: dict[str, str] = {}
    for eval_run in result.scalars().all():
        latest.setdefault(eval_run.scenario_id, eval_run.id)
    return latest


def _scenario_response(
    scenario: EvalScenario,
    last_runs: dict[str, str],
) -> EvalScenarioResponse:
    return EvalScenarioResponse.model_validate(
        {
            "id": scenario.id,
            "name": scenario.name,
            "description": scenario.description,
            "owner": scenario.owner_name,
            "tags": scenario.tags,
            "prompt": scenario.prompt,
            "fixture": scenario.fixture,
            "required_tools": scenario.required_tools,
            "forbidden_tools": scenario.forbidden_tools,
            "expected_facts": scenario.expected_facts,
            "evaluator_ids": scenario.evaluator_ids,
            "enabled": scenario.enabled,
            "last_run_id": last_runs.get(scenario.id),
            "created_at": scenario.created_at,
        }
    )


@router.get("/scenarios", response_model=list[EvalScenarioResponse])
async def list_scenarios(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> list[EvalScenarioResponse]:
    _require_admin(user.role)
    result = await db.execute(
        select(EvalScenario)
        .where(EvalScenario.archived.is_(False))
        .order_by(EvalScenario.created_at.desc())
    )
    last_runs = await _last_runs_by_scenario(db)
    return [_scenario_response(item, last_runs) for item in result.scalars().all()]


@router.post(
    "/scenarios",
    response_model=EvalScenarioResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_scenario(
    payload: EvalScenarioCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> EvalScenarioResponse:
    _require_admin(user.role)
    active_ids = {evaluator.id for evaluator in await _active_evaluators(db)}
    missing_ids = sorted(set(payload.evaluator_ids) - active_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown evaluators: {', '.join(missing_ids)}",
        )
    scenario = EvalScenario(
        id=f"scenario_{uuid4().hex}",
        created_by_user_id=user.id,
        owner_name=user.username,
        **payload.model_dump(),
    )
    db.add(scenario)
    await db.commit()
    await db.refresh(scenario)
    return _scenario_response(scenario, {})


@router.put("/scenarios/{scenario_id}", response_model=EvalScenarioResponse)
async def update_scenario(
    scenario_id: str,
    payload: EvalScenarioUpdate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> EvalScenarioResponse:
    _require_admin(user.role)
    scenario = await _scenario_or_404(db, scenario_id)
    active_ids = {evaluator.id for evaluator in await _active_evaluators(db)}
    missing_ids = sorted(set(payload.evaluator_ids) - active_ids)
    if missing_ids:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=f"Unknown evaluators: {', '.join(missing_ids)}",
        )
    for field, value in payload.model_dump().items():
        setattr(scenario, field, value)
    await db.commit()
    await db.refresh(scenario)
    return _scenario_response(scenario, await _last_runs_by_scenario(db))


@router.patch("/scenarios/{scenario_id}/enabled", response_model=EvalScenarioResponse)
async def toggle_scenario(
    scenario_id: str,
    payload: EvalScenarioToggle,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> EvalScenarioResponse:
    _require_admin(user.role)
    scenario = await _scenario_or_404(db, scenario_id)
    scenario.enabled = payload.enabled
    await db.commit()
    await db.refresh(scenario)
    return _scenario_response(scenario, await _last_runs_by_scenario(db))


@router.delete("/scenarios/{scenario_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_scenario(
    scenario_id: str,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> None:
    _require_admin(user.role)
    scenario = await _scenario_or_404(db, scenario_id)
    scenario.enabled = False
    scenario.archived = True
    await db.commit()


@router.get("/evaluators", response_model=list[EvalEvaluatorResponse])
async def list_evaluators(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> list[EvalEvaluatorResponse]:
    _require_admin(user.role)
    evaluators = await _active_evaluators(db)
    scenarios_result = await db.execute(
        select(EvalScenario.evaluator_ids).where(EvalScenario.archived.is_(False))
    )
    usage: dict[str, int] = {}
    for evaluator_ids in scenarios_result.scalars().all():
        for evaluator_id in evaluator_ids:
            usage[evaluator_id] = usage.get(evaluator_id, 0) + 1
    return [
        EvalEvaluatorResponse.model_validate(
            {
                **{
                    field: getattr(evaluator, field)
                    for field in (
                        "id",
                        "name",
                        "kind",
                        "rule",
                        "description",
                        "criteria",
                        "threshold",
                        "builtin",
                        "created_at",
                    )
                },
                "used_by": usage.get(evaluator.id, 0),
            }
        )
        for evaluator in evaluators
    ]


@router.post(
    "/evaluators",
    response_model=EvalEvaluatorResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_evaluator(
    payload: EvalEvaluatorCreate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> EvalEvaluatorResponse:
    _require_admin(user.role)
    if payload.rule is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_CONTENT)
    evaluator = EvalEvaluator(
        id=f"evaluator_{uuid4().hex}",
        created_by_user_id=user.id,
        builtin=False,
        **payload.model_dump(),
    )
    db.add(evaluator)
    await db.commit()
    await db.refresh(evaluator)
    return EvalEvaluatorResponse.model_validate(
        {
            "id": evaluator.id,
            "name": evaluator.name,
            "kind": evaluator.kind,
            "rule": evaluator.rule,
            "description": evaluator.description,
            "criteria": evaluator.criteria,
            "threshold": evaluator.threshold,
            "builtin": evaluator.builtin,
            "used_by": 0,
            "created_at": evaluator.created_at,
        }
    )


@router.put("/evaluators/{evaluator_id}", response_model=EvalEvaluatorResponse)
async def update_evaluator(
    evaluator_id: str,
    payload: EvalEvaluatorUpdate,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
) -> EvalEvaluatorResponse:
    _require_admin(user.role)
    evaluator = await db.get(EvalEvaluator, evaluator_id)
    if evaluator is None or evaluator.archived:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND)
    for field, value in payload.model_dump().items():
        setattr(evaluator, field, value)
    scenarios_result = await db.execute(
        select(EvalScenario.evaluator_ids).where(EvalScenario.archived.is_(False))
    )
    used_by = sum(
        evaluator.id in evaluator_ids
        for evaluator_ids in scenarios_result.scalars().all()
    )
    await db.commit()
    await db.refresh(evaluator)
    return EvalEvaluatorResponse.model_validate(
        {
            "id": evaluator.id,
            "name": evaluator.name,
            "kind": evaluator.kind,
            "rule": evaluator.rule,
            "description": evaluator.description,
            "criteria": evaluator.criteria,
            "threshold": evaluator.threshold,
            "builtin": evaluator.builtin,
            "used_by": used_by,
            "created_at": evaluator.created_at,
        }
    )


@router.get("/runs", response_model=list[EvalRunResponse])
async def list_runs(
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    limit: int = Query(default=100, ge=1, le=500),
) -> list[EvalRunResponse]:
    _require_admin(user.role)
    result = await db.execute(
        select(EvalRun, EvalScenario.name)
        .join(EvalScenario, EvalScenario.id == EvalRun.scenario_id)
        .order_by(EvalRun.created_at.desc())
        .limit(limit)
    )
    return [
        EvalRunResponse.model_validate(
            {
                **{
                    field: getattr(eval_run, field)
                    for field in (
                        "id",
                        "scenario_id",
                        "status",
                        "score",
                        "started_at",
                        "ended_at",
                        "duration_ms",
                        "model",
                        "version",
                        "answer",
                        "tool_calls",
                        "checks",
                        "error",
                    )
                },
                "scenario_name": scenario_name,
            }
        )
        for eval_run, scenario_name in result.all()
    ]


@router.post("/scenarios/{scenario_id}/runs", response_model=EvalRunResponse)
async def run_scenario(
    scenario_id: str,
    db: AsyncSessionDep,
    user: CheckUserSSODep,
    request_id: RequestIDDep,
    eval_service: EvalServiceDep,
) -> EvalRunResponse:
    _require_admin(user.role)
    scenario = await _scenario_or_404(db, scenario_id)
    if not scenario.enabled:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Disabled evaluation scenarios cannot be run.",
        )
    evaluator_by_id = {
        evaluator.id: evaluator for evaluator in await _active_evaluators(db)
    }
    evaluators = [
        evaluator_by_id[evaluator_id]
        for evaluator_id in scenario.evaluator_ids
        if evaluator_id in evaluator_by_id
    ]
    if len(evaluators) != len(scenario.evaluator_ids):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="The scenario references an evaluator that is no longer available.",
        )
    scenario_name = scenario.name
    eval_run = await eval_service.execute(
        db=db,
        scenario=scenario,
        evaluators=evaluators,
        user_id=user.id,
        request_id=request_id,
    )
    return EvalRunResponse.model_validate(
        {
            **{
                field: getattr(eval_run, field)
                for field in (
                    "id",
                    "scenario_id",
                    "status",
                    "score",
                    "started_at",
                    "ended_at",
                    "duration_ms",
                    "model",
                    "version",
                    "answer",
                    "tool_calls",
                    "checks",
                    "error",
                )
            },
            "scenario_name": scenario_name,
        }
    )
