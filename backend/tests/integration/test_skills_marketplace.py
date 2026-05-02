from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_skill_marketplace_share_approve_and_install(async_client) -> None:
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
    approve_resp = await async_client.post(
        f"/api/v1/skills/marketplace/{listing_id}/approve",
        json={"review_notes": "Looks good."},
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["status"] == "approved"

    install_resp = await async_client.post(
        f"/api/v1/skills/marketplace/{listing_id}/install"
    )
    assert install_resp.status_code == 201
    installed_skill = install_resp.json()
    assert installed_skill["installed_from_listing_id"] == listing_id
    assert installed_skill["slug"].startswith("bgp-drift-audit")
