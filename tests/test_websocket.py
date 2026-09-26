"""Tests for the Phase 1 WebSocket protocol."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_transcript_acknowledgement() -> None:
    """Transcript messages receive a deterministic acknowledgement."""
    with client.websocket_connect("/ws/stream") as websocket:
        websocket.send_json({"transcript": "You approach LarkFellow."})
        response = websocket.receive_json()

    assert response == {
        "type": "transcript_ack",
        "transcript": "You approach LarkFellow.",
        "matches": [],
    }
