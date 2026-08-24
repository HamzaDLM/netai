from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.init_db import init_db


@pytest.mark.anyio
async def test_skill_marketplace_share_approve_and_install(
    async_client,
    test_db_session_factory: async_sessionmaker[AsyncSession],
) -> None:
    await init_db(test_db_session_factory)
    create_skill_resp = await async_client.post(
        "/api/v1/skills",
        json={
            "name": "BGP Drift Audit",
            "description": "Audit BGP drift.",
            "instructions": "Check BGP policy drift and summarize findings.",
            "enabled": True,
        },
    )
    assert create_skill_resp.status_code == 201
    skill = create_skill_resp.json()

    share_resp = await async_client.post(f"/api/v1/skills/{skill['id']}/share")
    assert share_resp.status_code == 200
    assert share_resp.json()["marketplace_status"] == "pending"

    bootstrap_resp = await async_client.get("/api/v1/skills/bootstrap")
    assert bootstrap_resp.status_code == 200
    bootstrap = bootstrap_resp.json()
    assert bootstrap["review_queue"][0]["slug"] == "bgp-drift-audit"

    listing_id = bootstrap["review_queue"][0]["id"]
    admin_bootstrap_resp = await async_client.get("/api/v1/skills/admin/bootstrap")
    assert admin_bootstrap_resp.status_code == 200
    admin_bootstrap = admin_bootstrap_resp.json()
    assert admin_bootstrap["stats"]["pending_approvals"] == 1
    assert admin_bootstrap["stats"]["registered_skills"] >= 3
    assert admin_bootstrap["review_queue"][0]["owner_username"] == "testuser"
    created_admin_skill = next(
        item for item in admin_bootstrap["skills"] if item["id"] == skill["id"]
    )
    assert created_admin_skill["owner_username"] == "testuser"
    assert created_admin_skill["marketplace_status"] == "pending"

    approve_resp = await async_client.post(
        f"/api/v1/skills/marketplace/{listing_id}/approve",
        json={"review_notes": "Looks good."},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    approved_bootstrap_resp = await async_client.get("/api/v1/skills/bootstrap")
    assert approved_bootstrap_resp.status_code == 200
    approved_bootstrap = approved_bootstrap_resp.json()
    assert approved_bootstrap["marketplace"][0]["id"] == listing_id
    assert approved_bootstrap["marketplace"][0]["status"] == "approved"

    approved_admin_resp = await async_client.get("/api/v1/skills/admin/bootstrap")
    assert approved_admin_resp.status_code == 200
    approved_admin = approved_admin_resp.json()
    assert approved_admin["stats"]["pending_approvals"] == 0
    assert approved_admin["stats"]["marketplace_skills"] == 1

    install_resp = await async_client.post(
        f"/api/v1/skills/marketplace/{listing_id}/install"
    )
    assert install_resp.status_code == 201
    installed_skill = install_resp.json()
    assert installed_skill["installed_from_listing_id"] == listing_id
    assert installed_skill["slug"].startswith("bgp-drift-audit")
