from __future__ import annotations

import atexit
import copy
import functools
import getpass
import logging
import queue
from logging.handlers import (
    QueueHandler,
    TimedRotatingFileHandler,
)
import os
import platform
import socket
import sys
import time
import threading
from collections.abc import Callable
from typing import Any
import warnings

import structlog

from .local_settings import get_launcher_local_dir


# Record attribute holding the structlog logger, method name and event
#   dict, see '_render_for_stdlib' and '_EventDictProcessorFormatter'.
# - must not be '_logger' and '_name' used by 'wrap_for_formatter', plain
#   'ProcessorFormatter' would expect the event dict in 'record.msg'
_EVENT_DICT_ATTR = "_ayon_event_dict"


def _render_for_stdlib(
        logger: logging.Logger,
        method_name: str,
        event_dict: dict[str, Any]) -> tuple[tuple[str], dict[str, Any]]:
    """Last structlog processor handing the event over to stdlib logging.

    Unlike 'ProcessorFormatter.wrap_for_formatter', which stores the event
    dict in 'record.msg', the record keeps a plain string message. Handlers
    not using AYON formatters (DCC script editors, pyblish, the publisher
    report) show the message instead of a dict repr. The event dict is
    attached to the record for '_EventDictProcessorFormatter'.

    Args:
            logger (logging.Logger): The standard library logger.
            method_name (str): The logging method name (e.g., "info", "error").
            event_dict (dict[str, Any]): The structlog event dictionary.

    Returns:
        tuple[tuple[str], dict[str, Any]]: A tuple containing
            the message tuple and keyword arguments for
            the standard library logger.

    """
    kwargs: dict[str, Any] = {
        "extra": {
            _EVENT_DICT_ATTR: (logger, method_name, event_dict),
        }
    }
    exc_info = event_dict.get("exc_info")
    if exc_info:
        # Let foreign handlers show the traceback too
        kwargs["exc_info"] = exc_info
    return (str(event_dict.get("event", "")),), kwargs


class _EventDictProcessorFormatter(structlog.stdlib.ProcessorFormatter):
    """ProcessorFormatter reading the event dict from the record.

    Counterpart of '_render_for_stdlib'. Other handlers may modify
    'record.msg' (pyblish does), the event dict is not affected.
    Records from 'wrap_for_formatter' and foreign stdlib records are
    processed as by 'ProcessorFormatter'.
    """

    def format(self, record: logging.LogRecord) -> str:
        """Format the log record, extracting the event dict if present.
        Args:
            record (logging.LogRecord): The log record to format.

        Returns:
            str: The formatted log message.

        """
        structlog_data = getattr(record, _EVENT_DICT_ATTR, None)
        if structlog_data is not None:
            logger, method_name, event_dict = structlog_data
            # Attributes are set only on the copy, see '_EVENT_DICT_ATTR'
            record = logging.makeLogRecord(record.__dict__)
            record._logger = logger
            record._name = method_name
            record.msg = event_dict
            record.args = ()
        return super().format(record)


def bind_contextvars(**kwargs):
    return structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars():
    structlog.contextvars.clear_contextvars()


def unbind_contextvars(*keys):
    structlog.contextvars.unbind_contextvars(*keys)


def _get_level_names_mapping() -> dict[str, int]:
    """Level name to level mapping, including custom levels.

    'logging.getLevelName' is deprecated for name to level lookup.
    'logging.getLevelNamesMapping' is available since Python 3.11,
    older interpreters in DCCs fall back to the private mapping.

    Returns:
        dict[str, int]: Level name to level mapping.

    """
    getter = getattr(logging, "getLevelNamesMapping", None)
    if getter is not None:
        return getter()
    return dict(logging._nameToLevel)


def get_log_level_from_env() -> int:
    """Resolve the AYON log level from environment variables.

    'AYON_LOG_LEVEL' has precedence and accepts a numeric ('10') or
    a named ('DEBUG') level. When it is not set, or is invalid,
    'AYON_DEBUG' greater than 0 enables DEBUG. Defaults to INFO.

    Returns:
        int: Log level.

    """
    log_level = os.getenv("AYON_LOG_LEVEL", "").strip()
    if log_level:
        if log_level.isdigit():
            level = int(log_level)
        else:
            level = _get_level_names_mapping().get(log_level.upper(), 0)
        if level > 0:
            return level

    try:
        if int(os.getenv("AYON_DEBUG", "0")) > 0:
            return logging.DEBUG
    except ValueError:
        pass
    return logging.INFO


VECTOR_LOG_URL = os.getenv("AYON_VECTOR_LOG_URL", None)
LOG_FILE_ENABLED = os.getenv("AYON_LOG_FILE") == "1"
try:
    LOG_FILE_RETENTION_DAYS = int(
        max(1, int(
            os.getenv("AYON_LOG_RETENTION_DAYS", "1")
        ))
    )
except ValueError:
    LOG_FILE_RETENTION_DAYS = 1
# Each process writes its own file, see '_get_log_file_path'
LOG_FILE_PREFIX = "ayon_"
LOG_FILE_EXT = ".ndjson"


def _get_log_file_path(log_dir: str) -> str:
    """Log file path unique for the current process.

    Multiple AYON processes (tray, hosts, publish jobs) log at the same
    time. They must not share one file: writes would interleave and
    rotation of a shared file fails on Windows when another process has
    the file open.
    """
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    return os.path.join(
        log_dir,
        f"{LOG_FILE_PREFIX}{timestamp}_{os.getpid()}{LOG_FILE_EXT}"
    )


def _remove_old_log_files(log_dir: str, retention_days: int) -> None:
    """Remove AYON log files not modified within retention period.

    Includes files of other processes, and rotated files of this one.
    """
    threshold = time.time() - (retention_days * 24 * 60 * 60)
    try:
        filenames = os.listdir(log_dir)
    except OSError:
        return
    for filename in filenames:
        if (
            not filename.startswith(LOG_FILE_PREFIX)
            or LOG_FILE_EXT not in filename
        ):
            continue
        path = os.path.join(log_dir, filename)
        try:
            if os.path.getmtime(path) < threshold:
                os.remove(path)
        except OSError:
            # Removed meanwhile or still open by other process on Windows
            pass


# Max records buffered for Vector delivery. Beyond this, new records are
# dropped rather than growing memory unbounded during an outage.
VECTOR_QUEUE_MAX_SIZE = 10_000
# Max records sent to Vector in one request.
VECTOR_BATCH_SIZE = 500
# Max seconds a record waits for more records to be batched with it.
VECTOR_FLUSH_INTERVAL = 1.0
# Consecutive send failures after which the circuit opens (stop trying
# HTTP calls for a while, just drop records fast).
VECTOR_FAILURE_THRESHOLD = 5
# How long the circuit stays open once tripped.
VECTOR_CIRCUIT_COOLDOWN = 30.0
# Minimum time between "records are being dropped" warnings, to avoid
# flooding the console/log file during a prolonged outage.
VECTOR_WARN_INTERVAL = 30.0
# Logger for problems of Vector delivery. Its records are not sent to
# Vector, see '_DroppingQueueHandler'.
_VECTOR_LOGGER_NAME = "ayon.vector_log"


class _RateLimitedLogger:
    """Log a warning at most once per 'interval' seconds.

    Used in logging to vector to prevent flooding the log
    with repeated warnings when there is vector delivery failure.

    """
    def __init__(self, logger: logging.Logger, interval: float):
        self._logger = logger
        self._interval = interval
        self._last_emit = 0.0

    def warning(self, msg: str, *args: Any) -> None:
        """Log a warning message if the rate limit allows.

        Args:
            msg (str): The warning message.
            *args (Any): Positional arguments for the log message.

        Returns:
            None

        """
        now = time.monotonic()
        if now - self._last_emit < self._interval:
            return
        self._last_emit = now
        # Only positional arguments - the wrapped logger is a plain
        #   stdlib logger which raises 'TypeError' on unknown kwargs.
        self._logger.warning(msg, *args)


_vector_warn_logger = _RateLimitedLogger(
    logging.getLogger(_VECTOR_LOGGER_NAME), VECTOR_WARN_INTERVAL
)


class _DroppingQueueHandler(QueueHandler):
    """QueueHandler rendering records for Vector, dropping on overflow.

    Records are rendered with the handler's formatter in the logging
    thread and the resulting JSON string is queued. Rendering in the
    sender thread instead would race with other handlers mutating the
    shared record (e.g. pyblish's 'MessageHandler' replaces 'record.msg')
    and with later changes of mutable log arguments.

    Records about Vector delivery itself are not queued, they would only
    add load to an endpoint that is already failing.
    """

    def __init__(self, log_queue: queue.Queue):
        super().__init__(log_queue)
        self.addFilter(lambda record: record.name != _VECTOR_LOGGER_NAME)

    def prepare(self, record: logging.LogRecord) -> str:
        return self.format(record)

    def enqueue(self, record: logging.LogRecord) -> None:
        # handle full queue gracefully by dropping
        # the record instead of raising.
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            _vector_warn_logger.warning(
                "Vector log queue is full, dropping log records."
            )


class VectorHTTPSender:
    """Send rendered log records from a queue to a Vector HTTP source.

    A daemon thread collects up to 'batch_size' records, or what arrived
    within 'flush_interval' seconds, and sends them as one JSON array per
    request. Vector's 'json' decoding creates one event per array item.

    A circuit breaker stops sending for 'cooldown' seconds after
    'failure_threshold' consecutive failed requests. Records are dropped
    meanwhile so a dead endpoint cannot slow down the process.

    'None' in the queue is the stop sentinel, see 'stop'.
    """

    def __init__(
        self,
        url: str,
        log_queue: queue.Queue[str | None],
        batch_size: int = VECTOR_BATCH_SIZE,
        flush_interval: float = VECTOR_FLUSH_INTERVAL,
        failure_threshold: int = VECTOR_FAILURE_THRESHOLD,
        cooldown: float = VECTOR_CIRCUIT_COOLDOWN,
    ):
        self._url = url
        self._queue = log_queue
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._thread: threading.Thread | None = None

        # Import only when Vector is used, to not slow down import of
        #   'ayon_core.lib' in every process.
        import requests
        import requests.adapters
        import urllib3.util

        # Reuse a single session so repeated POSTs reuse pooled
        # connections instead of opening a new one per request.
        self._session = requests.Session()
        retry = urllib3.util.Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            allowed_methods=("POST",),
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1, pool_maxsize=1, max_retries=retry
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def start(self) -> None:
        self._thread = threading.Thread(
            target=self._run, name="AYONVectorSender", daemon=True
        )
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Send records remaining in the queue and stop the thread."""
        if self._thread is None:
            return
        try:
            self._queue.put(None, timeout=timeout)
        except queue.Full:
            pass
        self._thread.join(timeout)
        self._thread = None
        self._session.close()

    def _run(self) -> None:
        stop = False
        while not stop:
            item = self._queue.get()
            if item is None:
                break
            batch = [item]
            deadline = time.monotonic() + self._flush_interval
            while len(batch) < self._batch_size:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                try:
                    item = self._queue.get(timeout=remaining)
                except queue.Empty:
                    break
                if item is None:
                    stop = True
                    break
                batch.append(item)
            self._send(batch)

    def _send(self, batch: list[str]) -> None:
        now = time.monotonic()
        if now < self._circuit_open_until:
            # Circuit is open - skip the HTTP attempt entirely so a dead
            # Vector endpoint cannot slow down the sender thread.
            return
        try:
            response = self._session.post(
                self._url,
                data="[{}]".format(",".join(batch)).encode("utf-8"),
                headers={"Content-Type": "application/json"},
                timeout=(0.3, 2.0),
            )
            response.raise_for_status()
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._circuit_open_until = now + self._cooldown
                self._consecutive_failures = 0
                _vector_warn_logger.warning(
                    "Vector endpoint unreachable, pausing log delivery"
                    " for %s seconds.",
                    self._cooldown,
                )
            else:
                # Rate-limit warnings in case of Vector outage.
                _vector_warn_logger.warning(
                    "Failed to send %s log records to Vector.", len(batch)
                )
        else:
            self._consecutive_failures = 0


def _is_running_from_sources() -> bool:
    """AYON launcher runs from sources, not from a build.

    Same check as 'ayon_info.is_running_from_build', which can't be
    imported here because of an import cycle.

    Returns:
        bool: True if running from sources, False otherwise.

    """
    executable = os.environ.get("AYON_EXECUTABLE") or sys.executable
    return "python" in os.path.basename(executable).lower()


def _get_console_exception_formatter(
        colors: bool) -> structlog.types.Processor:
    """Exception formatter for console output.

    Rich tracebacks are used only when running from sources. Builds use
    plain tracebacks. Locals are never shown, they may hold large or
    sensitive values (e.g. credentials).

    Returns:
        structlog.types.Processor: The exception formatter for console output.

    """
    if _is_running_from_sources():
        try:
            import rich  # noqa: F401
        except ImportError:
            pass
        else:
            return structlog.dev.RichTracebackFormatter(
                color_system="truecolor" if colors else None,
                show_locals=False,
            )
    return structlog.dev.plain_traceback


class _ConsoleRenderer(structlog.dev.ConsoleRenderer):
    """ConsoleRenderer not initializing colorama on Windows.

    'colorama.init()' replaces 'sys.stdout' and 'sys.stderr' of the whole
    process, which breaks hosts redirecting them. Whether the stream
    supports colors is resolved by '_StderrHandler' instead.
    """

    @classmethod
    def get_default_column_styles(cls, colors, force_colors=False):
        if colors:
            return structlog.dev._colorful_styles
        return structlog.dev._plain_styles


# Console mode flag enabling ANSI escape sequences on Windows
_ENABLE_VIRTUAL_TERMINAL_PROCESSING = 0x0004


@functools.lru_cache(maxsize=None)
def _enable_windows_ansi(fileno: int) -> bool:
    """Enable ANSI escape sequences in Windows console of 'fileno'.

    Returns:
        bool: The console supports ANSI escape sequences.

    """
    try:
        import ctypes
        import msvcrt

        kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]
        handle = msvcrt.get_osfhandle(fileno)  # type: ignore[attr-defined]
        mode = ctypes.c_uint32()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return False
        if mode.value & _ENABLE_VIRTUAL_TERMINAL_PROCESSING:
            return True
        return bool(kernel32.SetConsoleMode(
            handle, mode.value | _ENABLE_VIRTUAL_TERMINAL_PROCESSING
        ))
    except Exception:
        return False


def _stream_supports_colors(stream) -> bool:
    """Stream is a terminal able to show ANSI colors.

    'NO_COLOR' and 'FORCE_COLOR' environment variables have precedence,
    see https://no-color.org and https://force-color.org.
    """
    if os.environ.get("NO_COLOR"):
        return False
    if os.environ.get("FORCE_COLOR"):
        return True
    try:
        if not stream.isatty():
            return False
        if sys.platform == "win32":
            return _enable_windows_ansi(stream.fileno())
    except (AttributeError, ValueError, OSError):
        # Replaced streams may not implement 'isatty' or 'fileno'
        return False
    return os.environ.get("TERM") != "dumb"


class _StderrHandler(logging.StreamHandler):
    """StreamHandler writing to the current 'sys.stderr'.

    Hosts and AYON tools replace 'sys.stderr' after logging is configured.
    'logging.StreamHandler' would keep writing to the stream it received
    on creation. Same approach as stdlib 'logging._StderrHandler'.

    Logs go to stderr so stdout of AYON CLI commands stays usable for
    their output.

    Records are formatted with 'color_formatter' when the current stream
    supports colors, otherwise with the handler's formatter.
    """

    def __init__(self, level=logging.NOTSET, color_formatter=None):
        logging.Handler.__init__(self, level)
        self.color_formatter = color_formatter

    @property
    def stream(self):
        return sys.stderr

    def format(self, record):
        if (
            self.color_formatter is not None
            and _stream_supports_colors(sys.stderr)
        ):
            return self.color_formatter.format(record)
        return super().format(record)

    def emit(self, record):
        stream = sys.stderr
        # 'sys.stderr' is None in GUI processes without console
        if stream is None:
            return
        try:
            msg = self.format(record) + self.terminator
            try:
                stream.write(msg)
            except UnicodeEncodeError:
                # Stream encoding can't represent some characters, e.g.
                #   non-latin names on a 'cp1252' Windows console.
                encoding = getattr(stream, "encoding", None) or "ascii"
                stream.write(
                    msg.encode(encoding, "backslashreplace").decode(encoding)
                )
            self.flush()
        except RecursionError:
            raise
        except Exception:
            self.handleError(record)


def _deprecated_getter(func):
    def _get_logger_deprecate(cls, name: str | None = None) -> Any:
        if name is None:
            warnings.warn(
                "DEPRECATION: 'Logger.get_logger' without passed name is"
                " deprecated and will be removed in future versions.",
                stacklevel=2,
            )
            name = "__main__"
        return func(cls, name)
    return _get_logger_deprecate


class Logger:
    # Is static class initialized
    initialized = False
    _init_lock = threading.Lock()
    _root_logger = None

    # Logging level - AYON_LOG_LEVEL
    log_level = None

    # Data same for all record documents
    process_data = None
    # Cached process name or ability to set different process name
    _process_name = None

    @classmethod
    @_deprecated_getter
    def get_logger(cls, name: str) -> Any:
        """Get a logger by name, initializing the logging system if necessary.

        Reparent the underlying stdlib logger under the "AYON" root so
        its effective level/propagation is controlled from one place,
        regardless of where the logger's dotted name places it in the
        stdlib logger hierarchy.

        Args:
            name (str): The name of the logger to retrieve.

        Returns:
            structlog.stdlib.BoundLogger: The logger associated with
                the given name.

        """
        if not cls.initialized:
            cls.initialize()

        name = name or "__main__"

        logger = logging.getLogger(name)
        if logger is not cls._root_logger:
            logger.parent = cls._root_logger

        return structlog.get_logger(name)

    @classmethod
    def get_root_logger(cls) -> logging.Logger:
        if not cls.initialized:
            cls.initialize()
        return cls._root_logger  # type: ignore[invalid-return-type, return-value]

    @classmethod
    def initialize(cls):
        # TODO update already created loggers on re-initialization
        if cls.initialized:
            return

        with cls._init_lock:
            if cls.initialized:
                return
            cls._initialize()

    @classmethod
    def _initialize(cls):
        # Change initialization state to prevent runtime changes
        # if is executed during runtime
        cls.initialized = False
        cls.configure_logger()

        cls.log_level = get_log_level_from_env()
        root_logger = logging.getLogger("AYON")
        root_logger.setLevel(cls.log_level)
        # Records propagate to the stdlib root logger which holds
        #   the handlers, see 'configure_logger'.
        cls._root_logger = root_logger

        if cls.log_level < logging.INFO:
            # force silence for some very noisy loggers
            logging.getLogger("urllib3").setLevel(logging.WARNING)
            logging.getLogger("requests").setLevel(logging.WARNING)
            logging.getLogger("GlobalServerAPI").setLevel(logging.WARNING)

        # Mark as initialized
        cls.initialized = True

    @classmethod
    def get_process_data(cls):
        """Data about current process which should be same for all records.

        Process data are used for each record sent to mongo database.
        """
        if cls.process_data is not None:
            return copy.deepcopy(cls.process_data)

        if not cls.initialized:
            cls.initialize()

        host_name = socket.gethostname()
        try:
            host_ip = socket.gethostbyname(host_name)
        except socket.gaierror:
            host_ip = "127.0.0.1"

        process_name = cls.get_process_name()

        cls.process_data = {
            "hostname": host_name,
            "hostip": host_ip,
            "username": getpass.getuser(),
            "system_name": platform.system(),
            "process_name": process_name
        }
        return copy.deepcopy(cls.process_data)

    @classmethod
    def set_process_name(cls, process_name):
        """Set process name for mongo logs."""
        # Just change the attribute
        cls._process_name = process_name
        # Update process data if are already set
        if cls.process_data is not None:
            cls.process_data["process_name"] = process_name

    @classmethod
    def get_process_name(cls):
        """Process name that is like "label" of a process.

        AYON logging can be used from OpenPyppe itself of from hosts.
        Even in AYON process it's good to know if logs are from tray or
        from other cli commands. This should help to identify that information.
        """
        if cls._process_name is not None:
            return cls._process_name

        # Get process name
        process_name = os.environ.get("AYON_APP_NAME")
        if not process_name:
            try:
                import psutil
                process = psutil.Process(os.getpid())
                process_name = process.name()

            except ImportError:
                pass

        if not process_name:
            process_name = os.path.basename(sys.executable)

        cls._process_name = process_name
        return cls._process_name

    @classmethod
    def configure_logger(cls) -> None:
        """Configure structlog.

        Including structlog and handlers for console and Vector HTTP.

        Safe to call multiple times, and safe even if another package (e.g.
        'ayon_common' in ayon-launcher) configures logging first - only the
        first call in the process has any effect, to avoid attaching
        duplicate handlers.

        """
        # 'structlog.is_configured()' is process-wide, so it also guards
        # against other packages configuring logging first.
        if structlog.is_configured():
            return

        def _add_site_id(logger, method_name, event_dict):
            event_dict.setdefault(
                "site_id", os.environ.get("AYON_SITE_ID", "unknown")
            )
            return event_dict

        def _add_session_id(logger, method_name, event_dict):
            session_id = os.environ.get("AYON_SESSION_ID")
            if session_id:
                event_dict.setdefault("session_id", session_id)
            return event_dict

        def _drop_log_context(logger, method_name, event_dict):
            # Keep context fields in JSON sent to Vector but not
            # in console output
            event_dict.pop("site_id", None)
            event_dict.pop("session_id", None)
            return event_dict

        shared_processors: list[Callable] = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            _add_site_id,
            _add_session_id,
        ]

        structlog.configure(
            processors=shared_processors + [
                # Support '%s' style arguments, e.g.
                #   'log.info("Loaded %s", name)'. Records from plain
                #   stdlib loggers are already formatted by
                #   'ProcessorFormatter' via 'record.getMessage()'.
                structlog.stdlib.PositionalArgumentsFormatter(),
                # Hand over to standard logging, rendered by formatters
                _render_for_stdlib,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        def _create_console_formatter(colors):
            return _EventDictProcessorFormatter(
                foreign_pre_chain=shared_processors,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    _drop_log_context,
                    _ConsoleRenderer(
                        colors=colors,
                        exception_formatter=(
                            _get_console_exception_formatter(colors)
                        ),
                    ),
                ],
            )

        json_formatter = _EventDictProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        )

        handler = _StderrHandler(
            color_formatter=_create_console_formatter(colors=True)
        )
        handler.setFormatter(_create_console_formatter(colors=False))

        if LOG_FILE_ENABLED:
            log_dir = get_launcher_local_dir("logs")
            os.makedirs(log_dir, exist_ok=True)
            _remove_old_log_files(log_dir, LOG_FILE_RETENTION_DAYS)
            file_handler = TimedRotatingFileHandler(
                _get_log_file_path(log_dir),
                when="midnight",
                backupCount=LOG_FILE_RETENTION_DAYS,
                encoding="utf-8",
            )
            file_handler.setFormatter(json_formatter)

        if VECTOR_LOG_URL:
            # Send logs to Vector asynchronously so HTTP calls
            # don't block the app.
            # Queue is bounded so a Vector outage drops records instead of
            # growing memory without bound.
            log_queue: queue.Queue[str | None] = queue.Queue(
                VECTOR_QUEUE_MAX_SIZE
            )
            queue_handler = _DroppingQueueHandler(log_queue)
            queue_handler.setFormatter(json_formatter)
            vector_sender = VectorHTTPSender(VECTOR_LOG_URL, log_queue)
            vector_sender.start()
            # The sender thread is a daemon thread, it would be killed on
            # interpreter exit with records still in the queue. Stopping it
            # at exit delivers the queued records first.
            atexit.register(vector_sender.stop)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        if LOG_FILE_ENABLED:
            root_logger.addHandler(file_handler)
        if VECTOR_LOG_URL:
            root_logger.addHandler(queue_handler)
        root_logger.setLevel(get_log_level_from_env())
