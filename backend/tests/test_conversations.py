"""Conversation persistence CRUD tests."""

from fastapi.testclient import TestClient


def test_create_and_list_conversations_and_messages(client: TestClient) -> None:
    create_resp = client.post("/api/v1/conversations", json={"title": "Sessão Inicial"})
    assert create_resp.status_code == 201
    conv = create_resp.json()
    assert conv["title"] == "Sessão Inicial"
    conv_id = conv["id"]

    list_resp = client.get("/api/v1/conversations")
    assert list_resp.status_code == 200
    assert len(list_resp.json()) == 1

    msg_resp = client.post(
        f"/api/v1/conversations/{conv_id}/messages",
        json={"role": "user", "content": "Olá, Jarvis."},
    )
    assert msg_resp.status_code == 201
    assert msg_resp.json()["content"] == "Olá, Jarvis."

    messages_resp = client.get(f"/api/v1/conversations/{conv_id}/messages")
    assert messages_resp.status_code == 200
    messages = messages_resp.json()
    assert len(messages) == 1
    assert messages[0]["role"] == "user"
