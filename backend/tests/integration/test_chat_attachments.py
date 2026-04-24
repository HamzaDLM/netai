from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_chat_attachment_lifecycle(async_client) -> None:
    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Attachments"}
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    upload_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/attachments",
        json={
            "filename": "runbook.md",
            "content_type": "text/markdown",
            "content": "# Runbook\n\nRestart the edge firewall only after confirming maintenance window.",
        },
    )
    assert upload_resp.status_code == 200
    uploaded = upload_resp.json()
    assert uploaded["filename"] == "runbook.md"
    assert uploaded["active"] is True
    assert uploaded["estimated_tokens"] > 0

    list_resp = await async_client.get(
        f"/api/v1/llm/conversation/{conversation_id}/attachments"
    )
    assert list_resp.status_code == 200
    listed = list_resp.json()
    assert len(listed) == 1
    assert listed[0]["id"] == uploaded["id"]

    delete_resp = await async_client.delete(
        f"/api/v1/llm/conversation/{conversation_id}/attachments/{uploaded['id']}"
    )
    assert delete_resp.status_code == 200
    deleted = delete_resp.json()
    assert deleted["id"] == uploaded["id"]
    assert deleted["active"] is False

    list_after_delete_resp = await async_client.get(
        f"/api/v1/llm/conversation/{conversation_id}/attachments"
    )
    assert list_after_delete_resp.status_code == 200
    assert list_after_delete_resp.json() == []


@pytest.mark.anyio
async def test_chat_attachment_rejects_unsupported_type(async_client) -> None:
    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "Attachments"}
    )
    conversation_id = create_resp.json()["id"]

    upload_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/attachments",
        json={
            "filename": "diagram.pdf",
            "content_type": "application/pdf",
            "content": "pretend-binary",
        },
    )

    assert upload_resp.status_code == 422
    assert upload_resp.json()["detail"] == "attachment_type_unsupported"
