"""Tests for connection handling of websocket 'EventHub'."""

from __future__ import annotations

import json
import threading
import time

import pytest
from websocket import ABNF, WebSocketTimeoutException

from ayon_core.tools.common_models import websocket as ws_model

HEARTBEAT = (ABNF.OPCODE_TEXT, json.dumps({"topic": "heartbeat"}))
PONG = (ABNF.OPCODE_PONG, b"")
TIMEOUT = "timeout"
# Thread did not run for longer than '_RECV_TIMEOUT' (e.g. DCC main thread
#   held the GIL), then the socket timed out
STALL = "stall"


class FakeWebSocket:
    """Replays scripted results of 'recv_data'.

    When the script is exhausted the test is stopped.

    """
    def __init__(self, responses, stop_event) -> None:
        self._responses = list(responses)
        self._stop_event = stop_event
        self.pings = 0

    def send(self, data) -> None:
        pass

    def ping(self) -> None:
        self.pings += 1

    def abort(self) -> None:
        pass

    def recv_data(self, control_frame: bool = False):
        if not self._responses:
            self._stop_event.set()
            raise ConnectionError("End of test")
        response = self._responses.pop(0)
        if response == STALL:
            time.sleep(ws_model._RECV_TIMEOUT * 2)
            raise WebSocketTimeoutException("timed out")
        if response == TIMEOUT:
            raise WebSocketTimeoutException("timed out")
        return response


class FakeConnection:
    access_token = "token"


class EventsRecorder:
    def __init__(self) -> None:
        self.topics: list[str] = []

    def on_event(self, event) -> None:
        self.topics.append(event.topic)


@pytest.fixture
def run_hub(monkeypatch):
    """Run event hub loop with scripted websocket responses."""
    monkeypatch.setattr(ws_model, "_RECONNECT_DELAYS", (0.0,))

    def _run_hub(responses):
        stop_event = threading.Event()
        fake_ws = FakeWebSocket(responses, stop_event)
        connections = [fake_ws]

        def create_ws_connection():
            if connections:
                return connections.pop(0)
            stop_event.set()
            raise ConnectionError("End of test")

        hub = ws_model.EventHub(FakeConnection())
        monkeypatch.setattr(
            hub, "_create_ws_connection", create_ws_connection
        )
        monkeypatch.setattr(hub, "_check_token", lambda: True)
        recorder = EventsRecorder()
        hub.add_callback("connection.*", recorder.on_event, connect=False)
        hub._loop(stop_event)
        return recorder.topics, fake_ws

    return _run_hub


def test_busy_server_without_heartbeat_is_connected(run_hub):
    """Server answering pings is alive even if it does not send heartbeat.

    Server does not send heartbeat while it publishes other messages,
        which might take much longer than '_RECV_TIMEOUT'.

    """
    responses = [HEARTBEAT] + [TIMEOUT, PONG] * 10
    topics, fake_ws = run_hub(responses)

    assert topics == ["connection.opened"]
    assert fake_ws.pings == 10


def test_no_response_to_ping_is_connection_lost(run_hub):
    responses = [HEARTBEAT, TIMEOUT, TIMEOUT, TIMEOUT]
    topics, fake_ws = run_hub(responses)

    assert topics == ["connection.opened", "connection.closed"]
    assert fake_ws.pings == 2


def test_stalled_thread_is_not_connection_lost(run_hub, monkeypatch):
    """Thread that did not run for a while did not lose connection.

    DCC main thread can hold the GIL for a long time (e.g. while
        rendering), messages from server wait in the socket meanwhile.

    """
    monkeypatch.setattr(ws_model, "_PING_INTERVAL", 0.01)
    monkeypatch.setattr(ws_model, "_RECV_TIMEOUT", 0.03)
    responses = [HEARTBEAT, STALL, HEARTBEAT, HEARTBEAT]
    topics, fake_ws = run_hub(responses)

    assert topics == ["connection.opened"]
    assert fake_ws.pings == 1
