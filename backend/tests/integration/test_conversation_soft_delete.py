from __future__ import annotations

import pytest


@pytest.mark.anyio
async def test_delete_conversation_archives_and_hides_from_default_reads(
    async_client,
) -> None:
    create_resp = await async_client.post(
        "/api/v1/llm/conversation", json={"title": "To Archive"}
    )
    assert create_resp.status_code == 200
    conversation_id = create_resp.json()["id"]

    delete_resp = await async_client.delete(
        f"/api/v1/llm/conversation/{conversation_id}"
    )
    assert delete_resp.status_code == 204

    list_resp = await async_client.get("/api/v1/llm/conversations")
    assert list_resp.status_code == 200
    assert conversation_id not in {c["id"] for c in list_resp.json()}

    get_resp = await async_client.get(f"/api/v1/llm/conversation/{conversation_id}")
    assert get_resp.status_code == 404

    rename_resp = await async_client.patch(
        f"/api/v1/llm/conversation/{conversation_id}",
        json={"title": "New title"},
    )
    assert rename_resp.status_code == 404

    ask_resp = await async_client.post(
        f"/api/v1/llm/conversation/{conversation_id}/message",
        json={"content": "hello"},
    )
    assert ask_resp.status_code == 404
