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
from logging.handlers import TimedRotatingFileHandler

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

    Console handler is forced by 'AYON_LOG_CONSOLE', pytest adds its
    handlers to the root logger during the test.
    """
    root = logging.getLogger()
    ayon_root = logging.getLogger("AYON")
    package_logger = logging.getLogger("ayon_core")
    orig_root_handlers = list(root.handlers)
    orig_root_level = root.level
    orig_ayon_handlers = list(ayon_root.handlers)
    orig_package_level = package_logger.level
    for handler in orig_root_handlers:
        root.removeHandler(handler)
    package_logger.setLevel(logging.NOTSET)
    for key in (
        "AYON_LOG_LEVEL",
        "AYON_DEBUG",
        "AYON_LOG_FILE",
        "AYON_VECTOR_LOG_URL",
        "AYON_EXECUTABLE",
        "AYON_CORE_TIMERS",
        "NO_COLOR",
        "FORCE_COLOR",
    ):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("AYON_LOG_CONSOLE", "1")

    def _reset_structlog():
        structlog.reset_defaults()
        structlog.contextvars.clear_contextvars()

    def _load(initialize=True):
        _reset_structlog()
        module = importlib.reload(ayon_core.lib.log)
        if initialize:
            module.Logger.initialize()
        return module

    yield _load

    vector_sender = ayon_core.lib.log._vector_sender
    if vector_sender is not None:
        vector_sender.stop(1.0)

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
    package_logger.setLevel(orig_package_level)
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
        ({"AYON_LOG_LEVEL": "10"}, logging.DEBUG),
        ({"AYON_LOG_LEVEL": "warning"}, logging.WARNING),
        ({"AYON_LOG_LEVEL": "bogus"}, logging.INFO),
        ({"AYON_LOG_LEVEL": "0"}, logging.INFO),
        # Does not affect log level, see '--debug' of AYON launcher
        ({"AYON_DEBUG": "1"}, logging.INFO),
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


@pytest.mark.parametrize("name", [None, ""])
def test_get_logger_without_name(log_module, name):
    """Root logger must not be reparented under its child 'AYON'."""
    module = log_module()

    with pytest.warns(UserWarning, match="without passed name"):
        module.Logger.get_logger(name)

    assert logging.getLogger().parent is None
    assert logging.getLogger("__main__").parent is logging.getLogger("AYON")


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


def test_rate_limited_logger_accepts_arguments(log_module, monkeypatch):
    module = log_module()
    # Monotonic clock shortly after boot, e.g. on a fresh CI machine
    monkeypatch.setattr(module.time, "monotonic", lambda: 5.0)
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


def _event_dicts(handler, module, logger_name):
    return [
        getattr(record, module._EVENT_DICT_ATTR)[2]
        for record in handler.records
        if record.name == logger_name
    ]


def test_span_logged_only_when_enabled(
    log_module, monkeypatch, foreign_handler
):
    module = log_module()
    with module.log_span("tests.disabled"):
        pass
    assert _event_dicts(foreign_handler, module, module.SPAN_LOGGER_NAME) == []

    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module()
    with module.log_span("tests.enabled", key="a/b") as span:
        span.set(cache_hit=True)

    (event,) = _event_dicts(foreign_handler, module, module.SPAN_LOGGER_NAME)
    assert event["event"] == "tests.enabled"
    assert event["level"] == "debug"
    assert event["status"] == "ok"
    assert event["key"] == "a/b"
    assert event["cache_hit"] is True
    assert event["duration_ms"] >= 0
    assert event["trace_id"] == span.trace_id
    assert event["span_id"] == span.span_id
    assert "parent_span_id" not in event
    assert event["module"] == __name__
    assert event["func_name"] == "test_span_logged_only_when_enabled"


def test_span_nesting_and_log_correlation(
    log_module, monkeypatch, foreign_handler
):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.span_inner")

    with module.log_span("tests.outer") as outer:
        with module.log_span("tests.inner") as inner:
            log.info("Inside")
    log.info("Outside")

    assert inner.trace_id == outer.trace_id
    assert inner.span_id != outer.span_id
    spans = {
        event["event"]: event
        for event in _event_dicts(
            foreign_handler, module, module.SPAN_LOGGER_NAME
        )
    }
    assert spans["tests.inner"]["parent_span_id"] == outer.span_id
    inside, outside = _event_dicts(
        foreign_handler, module, "ayon_core.tests.span_inner"
    )
    assert inside["trace_id"] == inner.trace_id
    assert inside["span_id"] == inner.span_id
    assert "trace_id" not in outside
    assert "span_id" not in outside

    # A new root span starts a new trace
    with module.log_span("tests.other") as other:
        pass
    assert other.trace_id != outer.trace_id


def test_span_records_error(log_module, monkeypatch, foreign_handler):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module()

    with pytest.raises(ValueError):
        with module.log_span("tests.error"):
            raise ValueError("boom")

    (event,) = _event_dicts(foreign_handler, module, module.SPAN_LOGGER_NAME)
    assert event["status"] == "error"
    assert event["error_type"] == "ValueError"


def test_slow_span_logged_as_warning(log_module, foreign_handler):
    module = log_module()

    with module.log_span("tests.fast", slow_threshold=60.0):
        pass
    with module.log_span("tests.slow", slow_threshold=0.0):
        pass

    (event,) = _event_dicts(foreign_handler, module, module.SPAN_LOGGER_NAME)
    assert event["event"] == "tests.slow"
    assert event["level"] == "warning"
    assert event["slow"] is True


def test_span_decorator(log_module, monkeypatch, foreign_handler):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module()

    @module.log_span("tests.decorated", kind="unit")
    def decorated(value):
        return value * 2

    assert decorated(2) == 4
    assert decorated(3) == 6

    events = _event_dicts(foreign_handler, module, module.SPAN_LOGGER_NAME)
    assert len(events) == 2
    assert events[0]["span_id"] != events[1]["span_id"]
    assert events[0]["kind"] == "unit"
    assert events[0]["func_name"].endswith("decorated")
    assert events[0]["module"] == __name__


def test_span_ids_hidden_in_console(log_module, monkeypatch):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module()
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)

    with module.log_span("tests.console") as span:
        pass

    output = stream.getvalue()
    assert "tests.console" in output
    assert "duration_ms" in output
    assert span.span_id not in output
    assert span.trace_id not in output


def test_task_queue_runs_task_in_requester_context(log_module):
    task_queue = pytest.importorskip("ayon_core.ui.components.task_queue")
    AsyncTask = task_queue.AsyncTask

    module = log_module()
    with module.log_span("tests.enqueue") as span:
        task = AsyncTask(
            name="test",
            function=structlog.contextvars.get_contextvars,
            callback=lambda _result: None,
        )

    results = []
    thread = threading.Thread(
        target=lambda: results.append(task._context.run(task.function))
    )
    thread.start()
    thread.join()

    assert results[0]["trace_id"] == span.trace_id
    assert results[0]["span_id"] == span.span_id


def test_process_context_in_records_of_all_threads(
    log_module, foreign_handler
):
    """Unlike context variables, process context is in all threads."""
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.process_context")
    module.set_process_context(host_name="test", project="project")
    module.bind_contextvars(bound="main")

    thread = threading.Thread(target=lambda: log.info("In thread"))
    thread.start()
    thread.join()
    module.set_process_context(project=None)
    log.info("Without project")

    in_thread, without_project = _event_dicts(
        foreign_handler, module, "ayon_core.tests.process_context"
    )
    assert in_thread["host_name"] == "test"
    assert in_thread["project"] == "project"
    assert "bound" not in in_thread
    assert without_project["host_name"] == "test"
    assert "project" not in without_project
    assert module.get_process_context() == {"host_name": "test"}


def test_process_context_not_in_console(log_module, monkeypatch):
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.process_console")
    stream = _capture_stderr(monkeypatch)
    module.set_process_context(project="process_project")

    log.info("Implicit")
    log.info("Explicit", project="other_project")

    output = stream.getvalue()
    assert "process_project" not in output
    assert "other_project" in output


@pytest.fixture
def log_context(log_module, monkeypatch):
    """Log context of installed host, see 'install_host'."""
    context_tools = pytest.importorskip("ayon_core.pipeline.context_tools")
    module = log_module()
    monkeypatch.setenv("AYON_FOLDER_PATH", "/a")
    monkeypatch.setenv("AYON_TASK_NAME", "one")
    context_tools._set_log_context("test", "project")
    yield module
    module.set_process_context(
        host_name=None, project=None, folder=None, task=None
    )


def test_install_sets_log_context(log_context):
    assert log_context.get_process_context() == {
        "host_name": "test",
        "project": "project",
        "folder": "/a",
        "task": "one",
    }


def test_task_changed_updates_log_context(log_context):
    from ayon_core.lib import emit_event, register_event_callback

    contexts = []

    def _on_task_changed():
        contexts.append(log_context.get_process_context())

    # Registered after log context callback, with default order
    callback = register_event_callback("taskChanged", _on_task_changed)
    try:
        emit_event("taskChanged", {
            "project_name": "project",
            "folder_path": "/b",
            "task_name": None,
        })
    finally:
        callback.deregister()

    expected = {"host_name": "test", "project": "project", "folder": "/b"}
    assert log_context.get_process_context() == expected
    # Other callbacks already log with the new context
    assert contexts == [expected]


def test_host_context_change_updates_log_context(log_context):
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

    host = _Host()
    host.set_current_context(
        {"path": "/b"},
        {"name": "two"},
        project_entity={"name": "project"},
        anatomy=object(),
    )

    context = log_context.get_process_context()
    assert context["folder"] == "/b"
    assert context["task"] == "two"


@pytest.fixture
def log_module_without_structlog(log_module, monkeypatch):
    """'ayon_core.lib.log' imported as if 'structlog' is not installed.

    Older AYON launchers and dependency packages don't have 'structlog'.
    """
    def _load():
        monkeypatch.setitem(sys.modules, "structlog", None)
        return log_module()

    return _load


def test_without_structlog_uses_stdlib_logger(
    log_module_without_structlog, monkeypatch, foreign_handler
):
    module = log_module_without_structlog()
    assert module.structlog is None

    log = module.Logger.get_logger("ayon_core.tests.fallback")
    assert isinstance(log, logging.Logger)
    assert log.parent is logging.getLogger("AYON")

    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    log.info("Loaded %s", "asset")

    assert foreign_handler.messages == ["Loaded asset"]
    output = stream.getvalue()
    assert "Loaded asset" in output
    assert "[ayon_core.tests.fallback]" in output


def test_without_structlog_contextvars_are_noop(log_module_without_structlog):
    module = log_module_without_structlog()

    assert module.bind_contextvars(project="project") == {}
    module.unbind_contextvars("project")
    module.clear_contextvars()


def test_without_structlog_span_is_logged(
    log_module_without_structlog, monkeypatch, foreign_handler
):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    module = log_module_without_structlog()

    with module.log_span("tests.fallback", key="a/b") as span:
        pass

    (record,) = [
        record for record in foreign_handler.records
        if record.name == module.SPAN_LOGGER_NAME
    ]
    message = record.getMessage()
    assert message.startswith("tests.fallback ")
    assert "key='a/b'" in message
    assert f"span_id='{span.span_id}'" in message
    assert "duration_ms=" in message


def test_without_structlog_skips_file_and_vector(
    log_module_without_structlog, monkeypatch, foreign_handler
):
    monkeypatch.setenv("AYON_LOG_FILE", "1")
    monkeypatch.setenv("AYON_VECTOR_LOG_URL", "http://127.0.0.1:1/")
    module = log_module_without_structlog()
    # Repeated configuration does not add handlers
    module.Logger._configure_logger()

    # Root also holds handlers of pytest log capture
    handler_types = [type(handler) for handler in logging.getLogger().handlers]
    assert handler_types.count(module._StderrHandler) == 1
    assert TimedRotatingFileHandler not in handler_types
    assert module._DroppingQueueHandler not in handler_types
    assert any(
        "require 'structlog'" in message
        for message in foreign_handler.messages
    )


def _capture_stderr(monkeypatch):
    # Must be called in the test, pytest replaces 'sys.stderr' after
    #   fixtures are set up
    stream = io.StringIO()
    monkeypatch.setattr(sys, "stderr", stream)
    return stream


@pytest.fixture
def restore_logger_levels():
    """Restore levels of loggers changed by the test."""
    orig_levels = {}

    def _get_logger(name):
        logger = logging.getLogger(name)
        orig_levels.setdefault(name, logger.level)
        return logger

    yield _get_logger

    for name, level in orig_levels.items():
        logging.getLogger(name).setLevel(level)


def test_root_logger_level_is_not_changed(log_module, monkeypatch):
    monkeypatch.setenv("AYON_LOG_LEVEL", "DEBUG")
    root = logging.getLogger()
    root.setLevel(logging.WARNING)

    log_module()

    assert root.level == logging.WARNING


@pytest.fixture
def log_root(tmp_path_factory):
    """Directory unique for the test.

    'tmp_path' of 'pytest_ayon' plugin is shared by the whole session.
    """
    return tmp_path_factory.mktemp("log_root")


def _enable_log_file(monkeypatch, tmp_path):
    monkeypatch.setenv("AYON_LOG_FILE", "1")
    monkeypatch.setattr(
        "ayon_core.lib.local_settings.get_launcher_local_dir",
        lambda *args: str(tmp_path.joinpath(*args)),
    )


def _log_file_events(tmp_path):
    """Events written to the log file of this process."""
    (path,) = (tmp_path / "logs").glob(f"*_{os.getpid()}.ndjson")
    return [
        json.loads(line)["event"]
        for line in path.read_text().splitlines()
    ]


@pytest.mark.parametrize("log_level", ["INFO", "DEBUG"])
def test_log_file_filters_pyblish_by_ayon_level(
    log_module,
    monkeypatch,
    log_root,
    restore_logger_levels,
    log_level,
):
    """Pyblish sets DEBUG level on plugin loggers, log file filters it.

    Console shows all plugin records as before structured logging.
    """
    monkeypatch.setenv("AYON_LOG_LEVEL", log_level)
    _enable_log_file(monkeypatch, log_root)
    log_module()
    stderr_stream = _capture_stderr(monkeypatch)
    plugin_log = restore_logger_levels("pyblish.TestHandlerLevelPlugin")
    plugin_log.setLevel(logging.DEBUG)

    plugin_log.debug("Plugin debug")
    plugin_log.info("Plugin info")

    assert "Plugin debug" in stderr_stream.getvalue()
    assert "Plugin info" in stderr_stream.getvalue()
    expected = ["Plugin info"]
    if log_level == "DEBUG":
        expected.insert(0, "Plugin debug")
    assert _log_file_events(log_root) == expected


def test_explicit_logger_level_is_respected(
    log_module, monkeypatch, restore_logger_levels
):
    """DEBUG level set on a single logger shows its debug records."""
    module = log_module()
    stderr_stream = _capture_stderr(monkeypatch)
    restore_logger_levels(module.SPAN_LOGGER_NAME).setLevel(logging.DEBUG)
    restore_logger_levels("ayon_core.tests.explicit").setLevel(logging.DEBUG)

    with module.log_span("tests.explicit"):
        pass
    logging.getLogger("ayon_core.tests.explicit").debug("Explicit debug")
    logging.getLogger("ayon_core.tests.implicit").debug("Implicit debug")

    output = stderr_stream.getvalue()
    assert "tests.explicit" in output
    assert "Explicit debug" in output
    assert "Implicit debug" not in output


def test_module_loggers_keep_host_root_level(
    log_module, monkeypatch, restore_logger_levels
):
    """Only loggers from 'Logger.get_logger' use AYON log level."""
    module = log_module()
    stderr_stream = _capture_stderr(monkeypatch)
    # Host application owns the root logger level
    logging.getLogger().setLevel(logging.WARNING)
    restore_logger_levels("ayon_tests_addon")

    module.Logger.get_logger("ayon_core.tests.module").info("Core module")
    logging.getLogger("ayon_core.tests.plain").info("Plain core module")
    logging.getLogger("ayon_tests_addon.module").info("Addon module")
    logging.getLogger("thirdparty.module").info("Third party")

    output = stderr_stream.getvalue()
    assert "Core module" in output
    assert "Plain core module" not in output
    assert "Addon module" not in output
    assert "Third party" not in output
    assert logging.getLogger("ayon_core").level == logging.NOTSET
    assert logging.getLogger("ayon_tests_addon").level == logging.NOTSET


@pytest.mark.parametrize(
    "env_value, root_handlers, expected",
    [
        ("", [], True),
        ("", [logging.NullHandler()], True),
        ("", [_ListHandler()], False),
        ("0", [], False),
        ("1", [_ListHandler()], True),
    ],
)
def test_console_handler_enabled(
    log_module, monkeypatch, env_value, root_handlers, expected
):
    module = log_module()
    monkeypatch.setenv("AYON_LOG_CONSOLE", env_value)
    monkeypatch.setattr(logging.getLogger(), "handlers", root_handlers)

    assert module._console_handler_enabled() is expected


def test_host_handler_replaces_console_handler(
    log_module, monkeypatch, foreign_handler
):
    """Host handler on root logger shows AYON records, no duplicates."""
    monkeypatch.delenv("AYON_LOG_CONSOLE")
    module = log_module()

    module.Logger.get_logger("ayon_core.tests.host").info("In host")

    assert not any(
        isinstance(handler, module._StderrHandler)
        for handler in logging.getLogger().handlers
    )
    assert foreign_handler.messages == ["In host"]


def test_publish_report_captures_debug_with_info_level(
    log_module, monkeypatch, log_root, restore_logger_levels
):
    pytest.importorskip("pyblish.plugin")
    from ayon_core.pipeline.publish.logic import MessageHandler, PublishLogic

    _enable_log_file(monkeypatch, log_root)
    log_module()
    stderr_stream = _capture_stderr(monkeypatch)
    plugin_log = restore_logger_levels("pyblish.TestReportDebugPlugin")
    plugin_log.setLevel(logging.DEBUG)
    plugin = types.SimpleNamespace(log=plugin_log)
    publish_logic = types.SimpleNamespace(
        _log_handler=MessageHandler(),
        _log_to_console=True,
    )

    with PublishLogic._log_manager(publish_logic, plugin) as handler:
        plugin_log.debug("Plugin debug")
        messages = [record.getMessage() for record in handler.get_records()]

    assert messages == ["Plugin debug"]
    assert "Plugin debug" in stderr_stream.getvalue()
    assert "Plugin debug" not in _log_file_events(log_root)


def test_structured_handlers(log_module, monkeypatch, log_root):
    module = log_module()
    assert module.Logger.get_structured_handlers() == []

    _enable_log_file(monkeypatch, log_root)
    module = log_module()

    handlers = module.Logger.get_structured_handlers()
    assert [type(handler) for handler in handlers] == [
        TimedRotatingFileHandler
    ]


def test_publisher_plugin_logs_go_to_log_file(
    log_module, monkeypatch, log_root, restore_logger_levels
):
    """Publisher does not show plugin logs in console by default.

    Records still go to the publish report, log file and Vector.
    """
    pytest.importorskip("pyblish.plugin")
    from ayon_core.pipeline.publish.logic import MessageHandler, PublishLogic

    _enable_log_file(monkeypatch, log_root)
    log_module()
    stderr_stream = _capture_stderr(monkeypatch)
    plugin_log = restore_logger_levels("pyblish.TestPublisherFilePlugin")
    plugin_log.setLevel(logging.DEBUG)
    orig_handlers = list(plugin_log.handlers)
    plugin = types.SimpleNamespace(log=plugin_log)
    publish_logic = types.SimpleNamespace(
        _log_handler=MessageHandler(),
        _log_to_console=False,
    )

    with PublishLogic._log_manager(publish_logic, plugin) as handler:
        plugin_log.debug("Plugin debug")
        plugin_log.info("Plugin info")
        messages = [record.getMessage() for record in handler.get_records()]

    assert messages == ["Plugin debug", "Plugin info"]
    assert _log_file_events(log_root) == ["Plugin info"]
    assert "Plugin" not in stderr_stream.getvalue()
    assert plugin_log.handlers == orig_handlers
    assert plugin_log.propagate is True


# --- Threads ---
# Logging from 'QThread' must not block Vector delivery and vice versa.
def _run_in_qthread(qtbot, func):
    """Run function in a 'QThread' and wait until it is finished.

    Waiting with timeout also proves the function did not block.
    """
    from qtpy import QtCore

    class _Thread(QtCore.QThread):
        def run(self):
            func()

    thread = _Thread()
    thread.start()
    qtbot.waitUntil(thread.isFinished, timeout=5000)
    thread.wait()
    thread.deleteLater()


def _wait_for(predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate():
        if time.monotonic() > deadline:
            raise AssertionError("Condition not met in time")
        time.sleep(0.01)


def _stub_events(stub):
    return [item["event"] for body in stub.bodies for item in body]


def test_logger_first_created_in_qthread(log_module, monkeypatch, qtbot):
    """Vector sender started from a 'QThread' outlives the thread."""
    stub = _StubVector()
    monkeypatch.setenv("AYON_VECTOR_LOG_URL", stub.url)
    module = log_module(initialize=False)
    try:
        _run_in_qthread(
            qtbot,
            lambda: module.Logger.get_logger(
                "ayon_core.tests.qthread"
            ).info("From QThread"),
        )
        sender_thread = module._vector_sender._thread
        assert sender_thread is not None and sender_thread.is_alive()

        module.Logger.get_logger("ayon_core.tests.qthread").info("From main")
        _wait_for(
            lambda: {"From QThread", "From main"} <= set(_stub_events(stub))
        )
    finally:
        stub.close()


def test_concurrent_initialization_from_qthread(
    log_module, monkeypatch, qtbot
):
    stub = _StubVector()
    monkeypatch.setenv("AYON_VECTOR_LOG_URL", stub.url)
    module = log_module(initialize=False)
    barrier = threading.Barrier(2)
    loggers = []

    def _get_logger():
        barrier.wait(5.0)
        loggers.append(module.Logger.get_logger("ayon_core.tests.init"))

    try:
        from qtpy import QtCore

        class _Thread(QtCore.QThread):
            def run(self):
                _get_logger()

        thread = _Thread()
        thread.start()
        _get_logger()
        qtbot.waitUntil(thread.isFinished, timeout=5000)
        thread.wait()
    finally:
        stub.close()

    assert len(loggers) == 2
    handler_types = [type(handler) for handler in logging.getLogger().handlers]
    assert handler_types.count(module._StderrHandler) == 1
    assert handler_types.count(module._DroppingQueueHandler) == 1
    senders = [
        thread for thread in threading.enumerate()
        if thread.name == "AYONVectorSender"
    ]
    assert senders == [module._vector_sender._thread]


def test_full_vector_queue_does_not_block_qthread(log_module, qtbot):
    module = log_module()
    module._vector_warn_logger._interval = 0
    warn_handler = _ListHandler()
    warn_logger = logging.getLogger(module._VECTOR_LOGGER_NAME)
    warn_logger.addHandler(warn_handler)
    # Nobody reads the queue, e.g. Vector sender is stuck
    handler = module._DroppingQueueHandler(queue.Queue(maxsize=2))
    logger = logging.getLogger("ayon_core.tests.qthread_full")
    logger.addHandler(handler)
    logger.propagate = False
    try:
        _run_in_qthread(
            qtbot,
            lambda: [logger.warning("Record %s", idx) for idx in range(100)],
        )
    finally:
        logger.removeHandler(handler)
        warn_logger.removeHandler(warn_handler)

    assert handler.queue.qsize() == 2
    assert "Vector log queue is full" in warn_handler.messages[0]


def test_records_of_qthreads_are_sent_once(log_module, qtbot):
    module = log_module()
    stub = _StubVector()
    log_queue = queue.Queue()
    sender = module.VectorHTTPSender(
        stub.url, log_queue, batch_size=50, flush_interval=0.05
    )
    handler = module._DroppingQueueHandler(log_queue)
    handler.setFormatter(
        structlog.stdlib.ProcessorFormatter(
            processors=[structlog.processors.JSONRenderer()],
        )
    )
    logger = logging.getLogger("ayon_core.tests.qthread_many")
    logger.addHandler(handler)
    logger.propagate = False

    from qtpy import QtCore

    class _Thread(QtCore.QThread):
        def __init__(self, thread_idx):
            super().__init__()
            self._thread_idx = thread_idx

        def run(self):
            for idx in range(50):
                logger.warning("%s-%s", self._thread_idx, idx)

    threads = [_Thread(thread_idx) for thread_idx in range(8)]
    try:
        sender.start()
        for thread in threads:
            thread.start()
        for thread in threads:
            qtbot.waitUntil(thread.isFinished, timeout=5000)
            thread.wait()
        sender.stop()
    finally:
        logger.removeHandler(handler)
        stub.close()

    events = _stub_events(stub)
    expected = {
        f"{thread_idx}-{idx}"
        for thread_idx in range(8)
        for idx in range(50)
    }
    assert len(events) == len(expected)
    assert set(events) == expected


def test_disable_vector_after_fork(log_module, monkeypatch):
    """Fork handler is called in the child, here directly."""
    stub = _StubVector()
    monkeypatch.setenv("AYON_VECTOR_LOG_URL", stub.url)
    module = log_module()
    try:
        vector_sender = module._vector_sender
        (queue_handler,) = [
            handler for handler in logging.getLogger().handlers
            if isinstance(handler, module._DroppingQueueHandler)
        ]

        module._disable_vector_after_fork(queue_handler, vector_sender)

        assert queue_handler not in logging.getLogger().handlers
        assert module._vector_sender is None
        # 'stop' at exit does not wait for the thread
        start = time.monotonic()
        vector_sender.stop()
        assert time.monotonic() - start < 1.0
    finally:
        stub.close()


@pytest.mark.skipif(not hasattr(os, "fork"), reason="Requires 'os.fork'")
def test_vector_disabled_in_forked_child(log_module, monkeypatch):
    stub = _StubVector()
    monkeypatch.setenv("AYON_VECTOR_LOG_URL", stub.url)
    module = log_module()
    try:
        pid = os.fork()
        if pid == 0:
            # Child, leave without running pytest teardown
            try:
                has_queue_handler = any(
                    isinstance(handler, module._DroppingQueueHandler)
                    for handler in logging.getLogger().handlers
                )
                logging.getLogger("ayon_core.tests.fork").warning("Child")
                os._exit(1 if has_queue_handler else 0)
            except BaseException:
                os._exit(2)
        _, status = os.waitpid(pid, 0)
    finally:
        stub.close()

    assert os.waitstatus_to_exitcode(status) == 0


class _BrokenStream:
    """Stream which fails on every write, like some host streams do."""

    def write(self, _text):
        raise SystemError("<built-in function write> returned a result")

    def flush(self):
        pass


def test_console_does_not_raise_on_broken_stream(log_module, monkeypatch):
    """A failing stream must not break the code that is logging."""
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.broken_stream")

    stream = _BrokenStream()
    # The host replaces the standard streams too, so neither printing
    # nor the 'handleError' report to 'sys.stderr' can succeed.
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(sys, "stderr", stream)

    log.info("message %s", "value")
    try:
        raise ValueError("boom")
    except ValueError:
        log.exception("failed")


def test_console_propagates_keyboard_interrupt(log_module, monkeypatch):
    """Interrupts raised while writing are not swallowed."""
    module = log_module()
    log = module.Logger.get_logger("ayon_core.tests.interrupted")

    class _InterruptedStream(_BrokenStream):
        def write(self, _text):
            raise KeyboardInterrupt

    monkeypatch.setattr(sys, "stderr", _InterruptedStream())

    with pytest.raises(KeyboardInterrupt):
        log.info("message")
