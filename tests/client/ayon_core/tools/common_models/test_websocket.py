"""Tests for connection handling of websocket 'EventHub'."""

from __future__ import annotations

import json
import threading
import time

import pytest
from websocket import ABNF, WebSocketTimeoutException

from ayon_core.tools.common_models import websocket as ws_model

HEARTBEAT = (ABNF.OPCODE_TEXT, json.dumps({"topic": "heartbeat"}))
RESTART = (
    ABNF.OPCODE_TEXT, json.dumps({"topic": "server.restart_requested"})
)
PONG = (ABNF.OPCODE_PONG, b"")
CLOSE = (ABNF.OPCODE_CLOSE, b"")
TIMEOUT = "timeout"
# Thread did not run for longer than '_RECV_TIMEOUT' (e.g. DCC main thread
#   held the GIL), then the socket timed out
STALL = "stall"
# Creating websocket connection fails (e.g. server is not running)
CREATE_FAILED = "create_failed"


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
    """Run event hub loop with scripted websocket responses.

    Each argument is a script of one connection, 'CREATE_FAILED' makes
        the connection attempt fail.

    """
    monkeypatch.setattr(ws_model, "_RECONNECT_DELAYS", (0.0,))

    def _run_hub(*scripts):
        stop_event = threading.Event()
        scripts = list(scripts)
        sockets = []

        def create_ws_connection():
            if not scripts:
                stop_event.set()
                raise ConnectionError("End of test")
            script = scripts.pop(0)
            if script == CREATE_FAILED:
                raise ConnectionError("Connection refused")
            fake_ws = FakeWebSocket(script, stop_event)
            sockets.append(fake_ws)
            return fake_ws

        hub = ws_model.EventHub(FakeConnection())
        monkeypatch.setattr(
            hub, "_create_ws_connection", create_ws_connection
        )
        monkeypatch.setattr(hub, "_check_token", lambda: True)
        recorder = EventsRecorder()
        hub.add_callback("connection.*", recorder.on_event, connect=False)
        hub._loop(stop_event)
        return recorder.topics, sockets

    return _run_hub


def test_busy_server_without_heartbeat_is_connected(run_hub):
    """Server answering pings is alive even if it does not send heartbeat.

    Server does not send heartbeat while it publishes other messages,
        which might take much longer than '_RECV_TIMEOUT'.

    """
    responses = [HEARTBEAT] + [TIMEOUT, PONG] * 10
    topics, sockets = run_hub(responses)

    assert topics == ["connection.opened"]
    assert sockets[0].pings == 10


def test_no_response_to_ping_is_connection_lost(run_hub):
    responses = [HEARTBEAT, TIMEOUT, TIMEOUT, TIMEOUT]
    topics, sockets = run_hub(responses, CREATE_FAILED)

    assert topics == ["connection.opened", "connection.closed"]
    assert sockets[0].pings == 2


def test_stalled_thread_is_not_connection_lost(run_hub, monkeypatch):
    """Thread that did not run for a while did not lose connection.

    DCC main thread can hold the GIL for a long time (e.g. while
        rendering), messages from server wait in the socket meanwhile.

    """
    monkeypatch.setattr(ws_model, "_PING_INTERVAL", 0.01)
    monkeypatch.setattr(ws_model, "_RECV_TIMEOUT", 0.03)
    responses = [HEARTBEAT, STALL, HEARTBEAT, HEARTBEAT]
    topics, sockets = run_hub(responses)

    assert topics == ["connection.opened"]
    assert sockets[0].pings == 1


def test_closed_connection_reconnects_without_reporting(run_hub):
    """Closed working connection is reported only if reconnect fails.

    Server closes connection of a client that did not answer its pings,
        e.g. when host held the GIL for a long time.

    """
    topics, _ = run_hub([HEARTBEAT, CLOSE], [HEARTBEAT])

    assert topics == ["connection.opened"]


def test_failed_reconnect_is_connection_lost(run_hub):
    topics, _ = run_hub([HEARTBEAT, CLOSE], CREATE_FAILED, [HEARTBEAT])

    assert topics == [
        "connection.opened", "connection.closed", "connection.opened"
    ]


def test_reconnect_closed_before_message_is_connection_lost(run_hub):
    """New connection closed by server without a message, e.g. bad token."""
    topics, _ = run_hub([HEARTBEAT, CLOSE], [CLOSE])

    assert topics == ["connection.opened", "connection.closed"]


def test_server_restart_is_connection_lost(run_hub):
    """Restart is reported, 'connection.opened' hides restart overlay."""
    topics, _ = run_hub([HEARTBEAT, RESTART, CLOSE], [HEARTBEAT])

    assert topics == [
        "connection.opened", "connection.closed", "connection.opened"
    ]


class FakeClock:
    def __init__(self) -> None:
        self.value = 1000.0
        self.slept: list[float] = []

    def monotonic(self) -> float:
        return self.value

    def sleep(self, seconds: float) -> None:
        self.slept.append(seconds)


@pytest.fixture
def clock_hub(monkeypatch):
    """Event hub with fake time, its loop thread is considered running."""
    clock = FakeClock()
    monkeypatch.setattr(ws_model, "time", clock)
    hub = ws_model.EventHub(FakeConnection())
    monkeypatch.setattr(hub, "is_running", lambda: True)
    return hub, clock


def test_loop_thread_gets_time_only_when_starved(clock_hub, monkeypatch):
    """Main thread yields only when loop thread is overdue.

    Host (e.g. Silhouette) can hold the GIL while idle, so the loop thread
        does not run until main thread releases the GIL.

    """
    hub, clock = clock_hub
    # Loop thread waits as expected ('wait' returns at once, event is set)
    stop_event = threading.Event()
    stop_event.set()
    hub._wait(stop_event, ws_model._PING_INTERVAL)
    hub.give_loop_thread_time()
    assert clock.slept == []

    # Loop thread should have run already
    clock.value += ws_model._PING_INTERVAL + ws_model._STARVED_MARGIN + 0.1
    hub.give_loop_thread_time()
    # Other tool processing events at the same time
    hub.give_loop_thread_time()
    assert len(clock.slept) == 1

    clock.value += ws_model._YIELD_INTERVAL
    hub.give_loop_thread_time()
    assert len(clock.slept) == 2

    # Loop thread is not running
    monkeypatch.setattr(hub, "is_running", lambda: False)
    clock.value += ws_model._YIELD_INTERVAL
    hub.give_loop_thread_time()
    assert len(clock.slept) == 2


def test_starved_loop_thread_catches_up(clock_hub):
    """Receive returning long after its timeout means thread was starved.

    Messages buffered meanwhile should be processed, so main thread keeps
        giving time to the loop thread for a while.

    """
    hub, clock = clock_hub

    class FakeRecvWebSocket:
        def __init__(self, duration: float) -> None:
            self._duration = duration

        def recv_data(self, control_frame: bool = False):
            clock.value += self._duration
            return HEARTBEAT

    hub._recv_data(FakeRecvWebSocket(0.1))
    hub.give_loop_thread_time()
    assert clock.slept == []

    # Data was waiting in the socket but thread did not run for a while
    hub._recv_data(FakeRecvWebSocket(ws_model._PING_INTERVAL + 1.0))
    # Loop thread waits on socket for the next message
    hub._loop_state.wake_by = clock.value + ws_model._PING_INTERVAL
    hub.give_loop_thread_time()
    assert len(clock.slept) == 1

    clock.value += ws_model._CATCH_UP_TIME
    hub.give_loop_thread_time()
    assert len(clock.slept) == 1
