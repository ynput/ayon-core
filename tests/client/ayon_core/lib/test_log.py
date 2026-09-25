"""Tests for structured logging in 'ayon_core.lib.log'.

Vector delivery is tested against a local HTTP stub, no Vector is needed.
"""
import importlib
import io
import json
import logging
import os
import queue
import sys
import threading
import time
import types
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import structlog

import ayon_core.lib.log


@pytest.fixture
def log_module(monkeypatch):
    """Freshly imported 'ayon_core.lib.log' with clean logging state.

    Environment variables are read on import, set them with 'monkeypatch'
    before calling the returned function.

    Root logger handlers are detached during the test. Those are handlers
    of pytest (live logging re-installs its capture as 'sys.stderr' on
    each record) and of AYON logging initialized on import of other
    modules during collection.
    """
    root = logging.getLogger()
    ayon_root = logging.getLogger("AYON")
    orig_root_handlers = list(root.handlers)
    orig_root_level = root.level
    orig_ayon_handlers = list(ayon_root.handlers)
    for handler in orig_root_handlers:
        root.removeHandler(handler)
    for key in (
        "AYON_LOG_LEVEL",
        "AYON_DEBUG",
        "AYON_LOG_FILE",
        "AYON_VECTOR_LOG_URL",
        "AYON_EXECUTABLE",
        "NO_COLOR",
        "FORCE_COLOR",
    ):
        monkeypatch.delenv(key, raising=False)

    def _reset_structlog():
        structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()

    def _load():
        _reset_structlog()
        module = importlib.reload(ayon_core.lib.log)
        module.Logger.initialize()
        return module

    yield _load

    for handler in list(root.handlers):
        root.removeHandler(handler)
        handler.close()
    for handler in orig_root_handlers:
        root.addHandler(handler)
    for handler in list(ayon_root.handlers):
        if handler not in orig_ayon_handlers:
            ayon_root.removeHandler(handler)
            handler.close()
    root.setLevel(orig_root_level)
    monkeypatch.undo()
    _reset_structlog()
    importlib.reload(ayon_core.lib.log)


class _ListHandler(logging.Handler):
    """Plain stdlib handler like a DCC script editor handler."""

    def __init__(self):
        super().__init__()
        self.messages = []
        self.records = []

    def emit(self, record):
        self.records.append(record)
        self.messages.append(record.getMessage())


@pytest.fixture
def foreign_handler():
    handler = _ListHandler()
    root = logging.getLogger()
    root.addHandler(handler)
    yield handler
    root.removeHandler(handler)


@pytest.mark.parametrize(
    "env, expected",
    [
        ({}, logging.INFO),
        ({"AYON_DEBUG": "1"}, logging.DEBUG),
        ({"AYON_LOG_LEVEL": "10"}, logging.DEBUG),
        ({"AYON_LOG_LEVEL": "warning"}, logging.WARNING),
        ({"AYON_LOG_LEVEL": "bogus", "AYON_DEBUG": "1"}, logging.DEBUG),
        ({"AYON_LOG_LEVEL": "0"}, logging.INFO),
        ({"AYON_DEBUG": "yes"}, logging.INFO),
    ],
)
def test_log_level_from_env(log_module, monkeypatch, env, expected):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    module = log_module()
    module.Logger.get_logger("ayon_core.tests.level")

    assert module.get_log_level_from_env() == expected
    level = logging.getLogger("ayon_core.tests.level").getEffectiveLevel()
    assert level == expected


def test_positional_arguments_are_formatted(log_module, foreign_handler):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.args")

    log.info("Loaded %s from %s", "asset", "disk")

    assert foreign_handler.messages == ["Loaded asset from disk"]


def test_foreign_handlers_get_plain_message(log_module, foreign_handler):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.foreign")

    log.info("Plain message", product="renderMain")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("Failed")

    assert foreign_handler.messages == ["Plain message", "Failed"]
    assert foreign_handler.records[1].exc_info[0] is ValueError


def test_console_formatter_ignores_mutated_record_msg(
    log_module, foreign_handler
):
    """Other handlers may replace 'record.msg', e.g. pyblish does."""
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.mutated")
    handler = next(
        h for h in logging.getLogger().handlers
        if isinstance(h, module._StderrHandler)
    )

    log.info("Original", key="value")
    record = foreign_handler.records[0]
    record.msg = "Mutated"

    output = handler.format(record)
    assert "Original" in output
    assert "key" in output


def test_foreign_processor_formatter_formats_ayon_records(
    log_module, foreign_handler
):
    """Other tools in the process may use plain 'ProcessorFormatter'."""
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.foreign_structlog")
    formatter = structlog.stdlib.ProcessorFormatter(
        processor=structlog.processors.JSONRenderer()
    )

    log.info("Loaded %s", "asset")

    payload = json.loads(formatter.format(foreign_handler.records[0]))
    assert payload["event"] == "Loaded asset"


def test_console_handler_uses_current_stderr(log_module, monkeypatch):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.stderr")

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    log.info("To replaced stderr")
    assert "To replaced stderr" in stream.getvalue()

    # GUI processes may not have stderr at all
    monkeypatch.setattr(sys, "stderr", None)
    log.info("No crash")


def _raise_with_local(log):
    # Built at runtime, the source line shown in tracebacks differs
    secret_local = "-".join(("secret", "local", "value"))  # noqa: F841
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("Failed")


@pytest.mark.parametrize("from_sources", [True, False])
@pytest.mark.parametrize("force_color", [True, False])
def test_console_traceback(log_module, monkeypatch, from_sources, force_color):
    executable = "python.exe" if from_sources else "ayon.exe"
    monkeypatch.setenv("AYON_EXECUTABLE", executable)
    if force_color:
        monkeypatch.setenv("FORCE_COLOR", "1")
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.traceback")

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    _raise_with_local(log)
    output = stream.getvalue()

    assert "ValueError" in output
    assert "boom" in output
    assert "secret-local-value" not in output
    assert ("\x1b[" in output) is force_color
    # Plain traceback frames look like 'File "<path>", line <n>, in <name>'
    assert ('", line ' in output) is not from_sources


def test_console_without_tty_has_no_colors(log_module, monkeypatch):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.no_tty")

    class _TTYStream(io.StringIO):
        def isatty(self):
            return True

    stream = _TTYStream()
    monkeypatch.setattr(sys, "stderr", stream)
    monkeypatch.setenv("NO_COLOR", "1")
    log.info("No color")
    assert "\x1b[" not in stream.getvalue()

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    monkeypatch.delenv("NO_COLOR")
    log.info("Not a terminal")
    assert "\x1b[" not in stream.getvalue()


def test_console_unencodable_characters(log_module, monkeypatch):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.encoding")

    buffer = io.BytesIO()
    stream = io.TextIOWrapper(buffer, encoding="ascii")
    monkeypatch.setattr(sys, "stderr", stream)
    log.info("Asset \u010dau")
    stream.flush()

    assert b"Asset \\u010dau" in buffer.getvalue()


def test_log_file_per_process_and_cleanup(log_module, monkeypatch, tmp_path):
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    old_file = logs_dir / "ayon_20200101-000000_1.ndjson"
    old_rotated = logs_dir / "ayon_20200101-000000_1.ndjson.2020-01-01"
    other_file = logs_dir / "other.txt"
    for path in (old_file, old_rotated, other_file):
        path.write_text("")
        old_time = time.time() - (3 * 24 * 60 * 60)
        os.utime(path, (old_time, old_time))

    monkeypatch.setenv("AYON_LOG_FILE", "1")
    monkeypatch.setenv("AYON_LOG_RETENTION_DAYS", "2")
    monkeypatch.setattr(
        "ayon_core.lib.local_settings.get_launcher_local_dir",
        lambda *args: str(tmp_path.joinpath(*args)),
    )
    module = log_module()
    module.Logger.get_logger("ayon_core.tests.file").info("To file")

    remaining = sorted(path.name for path in logs_dir.iterdir())
    assert "other.txt" in remaining
    assert old_file.name not in remaining
    assert old_rotated.name not in remaining
    own_files = [
        name for name in remaining
        if name.endswith(f"_{os.getpid()}.ndjson")
    ]
    assert len(own_files) == 1
    records = [
        json.loads(line)
        for line in (logs_dir / own_files[0]).read_text().splitlines()
    ]
    assert [r["event"] for r in records] == ["To file"]


def test_vector_queue_renders_in_logging_thread(log_module):
    module = log_module()
    log_queue = queue.Queue()
    handler = module._DroppingQueueHandler(log_queue)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[structlog.processors.JSONRenderer()],
        )
    )
    logger = logging.getLogger("ayon_core.tests.vector_queue")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        data = {"frame": 1}
        logger.warning("Data %s", data)
        # Mutation after logging must not change the queued record
        data["frame"] = 2
        # Vector delivery problems are not sent to Vector
        logging.getLogger(module._VECTOR_LOGGER_NAME).addHandler(handler)
        logging.getLogger(module._VECTOR_LOGGER_NAME).warning("Skipped")
    finally:
        logger.removeHandler(handler)
        logging.getLogger(module._VECTOR_LOGGER_NAME).removeHandler(handler)

    queued = [log_queue.get_nowait() for _ in range(log_queue.qsize())]
    assert len(queued) == 1
    assert json.loads(queued[0])["event"] == "Data {'frame': 1}"


def test_vector_queue_drops_when_full(log_module):
    module = log_module()
    log_queue = queue.Queue(maxsize=1)
    handler = module._DroppingQueueHandler(log_queue)
    logger = logging.getLogger("ayon_core.tests.vector_full")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        logger.warning("First")
        logger.warning("Dropped")
    finally:
        logger.removeHandler(handler)
    assert log_queue.qsize() == 1


class _StubVector:
    """Local HTTP endpoint collecting posted JSON bodies."""

    def __init__(self, status=200):
        self.bodies = []
        stub = self

        class _Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                length = int(self.headers["Content-Length"])
                stub.bodies.append(json.loads(self.rfile.read(length)))
                self.send_response(status)
                self.end_headers()

            def log_message(self, *args):
                pass

        self._server = HTTPServer(("127.0.0.1", 0), _Handler)
        self.url = f"http://127.0.0.1:{self._server.server_port}/"
        threading.Thread(
            target=self._server.serve_forever, daemon=True
        ).start()

    def close(self):
        self._server.shutdown()
        self._server.server_close()


def test_vector_sender_sends_batches(log_module):
    pytest.importorskip("requests")
    module = log_module()
    stub = _StubVector()
    log_queue = queue.Queue()
    sender = module.VectorHTTPSender(
        stub.url, log_queue, batch_size=10, flush_interval=5.0
    )
    try:
        for idx in range(25):
            log_queue.put(json.dumps({"event": str(idx)}))
        sender.start()
        # Stop sends what remains in the queue without waiting for
        #   the flush interval.
        sender.stop()
    finally:
        stub.close()

    assert [len(body) for body in stub.bodies] == [10, 10, 5]
    events = [item["event"] for body in stub.bodies for item in body]
    assert events == [str(idx) for idx in range(25)]


def test_vector_sender_survives_failures(log_module):
    """Failures open the circuit and never kill the sender thread."""
    pytest.importorskip("requests")
    module = log_module()
    module._vector_warn_logger._interval = 0
    stub = _StubVector(status=400)
    log_queue = queue.Queue()
    sender = module.VectorHTTPSender(
        stub.url,
        log_queue,
        batch_size=1,
        flush_interval=0.01,
        failure_threshold=2,
        cooldown=60.0,
    )
    try:
        sender.start()
        for idx in range(5):
            log_queue.put(json.dumps({"event": str(idx)}))
        deadline = time.monotonic() + 5.0
        while not log_queue.empty() and time.monotonic() < deadline:
            time.sleep(0.01)
        time.sleep(0.1)
        thread = sender._thread
        assert thread is not None and thread.is_alive()
    finally:
        sender.stop()
        stub.close()

    # Circuit opened after 2 failed requests, the rest was dropped
    assert len(stub.bodies) == 2


def test_rate_limited_logger_accepts_arguments(log_module):
    module = log_module()
    handler = _ListHandler()
    logger = logging.getLogger("ayon_core.tests.rate_limited")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        rate_limited = module._RateLimitedLogger(logger, interval=60.0)
        rate_limited.warning("Paused for %s seconds.", 30.0)
        rate_limited.warning("Suppressed %s", 1)
    finally:
        logger.removeHandler(handler)
    assert handler.messages == ["Paused for 30.0 seconds."]


def test_publish_log_manager_captures_all_loggers_once(log_module):
    pyblish_plugin = pytest.importorskip("pyblish.plugin")
    from ayon_core.pipeline.publish.logic import MessageHandler, PublishLogic

    module = log_module()
    plugin_log = logging.getLogger("pyblish.plugin.TestPlugin")
    # pyblish sets DEBUG on plugin loggers
    plugin_log.setLevel(logging.DEBUG)
    plugin = types.SimpleNamespace(log=plugin_log)
    library_log = module.Logger.get_logger("ayon_core.tests.library")

    for log_to_console in (True, False):
        publish_logic = types.SimpleNamespace(
            _log_handler=MessageHandler(),
            _log_to_console=log_to_console,
        )
        with PublishLogic._log_manager(publish_logic, plugin) as handler:
            plugin_log.info("Plugin %s", "message")
            library_log.info("Library %s", "message")
            pyblish_plugin.log.error("Pyblish error")
            messages = [
                record.getMessage() for record in handler.get_records()
            ]
        assert messages == [
            "Plugin message", "Library message", "Pyblish error"
        ]
        assert plugin_log.propagate is True


def test_publish_message_handler_does_not_mutate_record():
    from ayon_core.pipeline.publish.logic import MessageHandler

    handler = MessageHandler()
    record = logging.LogRecord(
        "test", logging.INFO, __file__, 1, "Value %s", ("x",), None
    )
    handler.emit(record)

    assert record.msg == "Value %s"
    assert handler.get_records()[0].msg == "Value x"


def test_host_context_change_binds_flat_keys(log_module):
    log_module()
    from ayon_core.host.host import HostBase

    class _Host(HostBase):
        name = "test"
        _context = {
            "project_name": "project",
            "folder_path": "/a",
            "task_name": "one",
        }

        def get_current_context(self):
            return dict(self._context)

        def get_current_project_name(self):
            return self._context["project_name"]

        def _set_current_context(self, data):
            self._context = {
                "project_name": data.project_entity["name"],
                "folder_path": data.folder_entity["path"],
                "task_name": data.task_entity["name"],
            }

        def _emit_context_change_event(self, *args):
            return {}

    host = _Host()
    host.set_current_context(
        {"path": "/b"},
        {"name": "two"},
        project_entity={"name": "project"},
        anatomy=object(),
    )

    context = structlog.contextvars.get_contextvars()
    assert context["project"] == "project"
    assert context["folder"] == "/b"
    assert context["task"] == "two"
    assert "ayon_context" not in context
