from __future__ import annotations

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.init_db import init_db


@pytest.mark.anyio
async def test_admin_can_create_and_list_eval_scenarios(
    async_client: AsyncClient,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await init_db(test_db_session_factory)

    evaluators_response = await async_client.get("/api/v1/evals/evaluators")
    assert evaluators_response.status_code == 200
    evaluator_ids = {item["id"] for item in evaluators_response.json()}
    assert {"tool-trajectory", "completion-safety"} <= evaluator_ids

    create_response = await async_client.post(
        "/api/v1/evals/scenarios",
        json={
            "name": "BGP investigation",
            "description": "Protect the end-to-end diagnosis path.",
            "prompt": "Why is edge-1 missing its route?",
            "fixture": "Peer is down in the target environment.",
            "tags": ["BGP"],
            "required_tools": ["zabbix_get_problems"],
            "forbidden_tools": ["bitbucket_commit_changes"],
            "expected_facts": ["The peer is down"],
            "evaluator_ids": ["tool-trajectory", "completion-safety"],
        },
    )
    assert create_response.status_code == 201
    created = create_response.json()
    assert created["owner"] == "testuser"
    assert created["enabled"] is True
    assert created["last_run_id"] is None

    list_response = await async_client.get("/api/v1/evals/scenarios")
    assert list_response.status_code == 200
    assert [item["id"] for item in list_response.json()] == [created["id"]]

    disable_response = await async_client.patch(
        f"/api/v1/evals/scenarios/{created['id']}/enabled",
        json={"enabled": False},
    )
    assert disable_response.status_code == 200
    assert disable_response.json()["enabled"] is False

    delete_response = await async_client.delete(
        f"/api/v1/evals/scenarios/{created['id']}"
    )
    assert delete_response.status_code == 204
    assert (await async_client.get("/api/v1/evals/scenarios")).json() == []


@pytest.mark.anyio
async def test_scenario_rejects_unknown_evaluator(
    async_client: AsyncClient,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await init_db(test_db_session_factory)
    response = await async_client.post(
        "/api/v1/evals/scenarios",
        json={
            "name": "Invalid suite",
            "prompt": "Check edge-1.",
            "evaluator_ids": ["missing-evaluator"],
        },
    )
    assert response.status_code == 422
    assert "missing-evaluator" in response.json()["detail"]
