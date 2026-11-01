import json

import pytest

from execution.iqoption_adapter import IQOptionAdapter


class FakeSocket:
    def __init__(self, events):
        self.events = iter(events)
        self.close_request = None

    def send(self, payload):
        message = json.loads(payload)
        body = message.get("msg")
        if isinstance(body, dict) and body.get("name") == "marginal-forex.close-position":
            self.close_request = message["request_id"]

    def recv(self):
        event = next(self.events, None)
        if event is None:
            raise TimeoutError("simulated timeout")
        if event.get("request_id") == "SAME_REQUEST":
            event = {**event, "request_id": self.close_request}
        return json.dumps(event)

    def close(self):
        pass


def test_disconnected_broker_position_is_not_simulated():
    adapter = IQOptionAdapter(environment="PAPER")
    result = adapter.close_position("123")
    assert result["success"] is False
    assert result["unknown"] is True


def test_disconnected_paper_simulation_remains_simulated():
    adapter = IQOptionAdapter(environment="PAPER")
    result = adapter.close_position("IQ_PAPER_123")
    assert result["success"] is True
    assert result["status"] == "CLOSED_SIMULATED"


def test_missing_position_id_is_not_simulated():
    adapter = IQOptionAdapter(environment="PAPER")
    assert adapter.close_position("")["success"] is False


@pytest.mark.parametrize("event", [
    {"name": "position-changed", "msg": {"id": 123, "status": "open"}},
    {"name": "position-closed", "msg": {"id": 999}},
    {"name": "result", "request_id": "unrelated", "status": 2000, "msg": {"success": True}},
])
def test_unrelated_event_does_not_confirm_close(event):
    adapter = IQOptionAdapter(ssid="fake", environment="PAPER")
    socket = FakeSocket([{"name": "authenticated"}, event])
    adapter._get_persistent_ws = lambda **kwargs: socket
    result = adapter.close_position("123")
    assert result["success"] is False


@pytest.mark.parametrize("event", [
    {"name": "position-closed", "msg": {"id": 123}},
    {"name": "result", "request_id": "SAME_REQUEST", "msg": {"success": True}},
])
def test_correlated_close_acknowledgment_does_not_claim_settled_pnl(event):
    adapter = IQOptionAdapter(ssid="fake", environment="PAPER")
    socket = FakeSocket([{"name": "authenticated"}, event])
    adapter._get_persistent_ws = lambda **kwargs: socket
    result = adapter.close_position("123")
    assert result["success"] is True
    assert result["status"] == "CLOSE_ACKNOWLEDGED"
    assert "pnl" not in result
