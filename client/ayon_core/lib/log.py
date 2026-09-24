from __future__ import annotations

import atexit
import copy
import getpass
import logging
import queue
from logging.handlers import (
    QueueHandler,
    TimedRotatingFileHandler,
)
import os
import platform
import requests
import requests.adapters
import socket
import sys
import time
import threading
from collections.abc import Callable
from typing import Any
import warnings

import urllib3.util

from . import Terminal
from .local_settings import get_launcher_local_dir


# If structlog is missing (ayon-launcher is outdated),
# the library will fall back to standard logging.
try:
    import structlog
except ImportError:
    structlog: Any = None  # type: ignore[no-redef]


# Record attribute holding the structlog event dict,
#   see '_render_for_stdlib' and '_EventDictProcessorFormatter'.
_EVENT_DICT_ATTR = "_ayon_event_dict"


def _render_for_stdlib(logger, method_name, event_dict):
    """Last structlog processor handing the event over to stdlib logging.

    Unlike 'ProcessorFormatter.wrap_for_formatter', which stores the event
    dict in 'record.msg', the record keeps a plain string message. Handlers
    not using AYON formatters (DCC script editors, pyblish, the publisher
    report) show the message instead of a dict repr. The event dict is
    attached to the record for '_EventDictProcessorFormatter'.
    """
    kwargs: dict[str, Any] = {
        "extra": {
            "_logger": logger,
            "_name": method_name,
            _EVENT_DICT_ATTR: event_dict,
        }
    }
    exc_info = event_dict.get("exc_info")
    if exc_info:
        # Let foreign handlers show the traceback too
        kwargs["exc_info"] = exc_info
    return (str(event_dict.get("event", "")),), kwargs


if structlog is not None:
    class _EventDictProcessorFormatter(structlog.stdlib.ProcessorFormatter):
        """ProcessorFormatter reading the event dict from the record.

        Counterpart of '_render_for_stdlib'. Other handlers may modify
        'record.msg' (pyblish does), the event dict is not affected.
        """

        def format(self, record):
            event_dict = getattr(record, _EVENT_DICT_ATTR, None)
            if event_dict is not None:
                record = logging.makeLogRecord(record.__dict__)
                record.msg = event_dict
                record.args = ()
            return super().format(record)


def bind_contextvars(**kwargs):
    if structlog is None:
        return {}
    return structlog.contextvars.bind_contextvars(**kwargs)


def clear_contextvars():
    if structlog is not None:
        structlog.contextvars.clear_contextvars()


def unbind_contextvars(*keys):
    if structlog is not None:
        structlog.contextvars.unbind_contextvars(*keys)


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
            level = logging.getLevelName(log_level.upper())
        if isinstance(level, int) and level > 0:
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
    """Log a warning at most once per 'interval' seconds."""

    def __init__(self, logger, interval):
        self._logger = logger
        self._interval = interval
        self._last_emit = 0.0

    def warning(self, msg, *args):
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

    def __init__(self, log_queue):
        super().__init__(log_queue)
        self.addFilter(lambda record: record.name != _VECTOR_LOGGER_NAME)

    def prepare(self, record):
        return self.format(record)

    def enqueue(self, record):
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
    """

    _stop_sentinel = object()

    def __init__(
        self,
        url,
        log_queue,
        batch_size=VECTOR_BATCH_SIZE,
        flush_interval=VECTOR_FLUSH_INTERVAL,
        failure_threshold=VECTOR_FAILURE_THRESHOLD,
        cooldown=VECTOR_CIRCUIT_COOLDOWN,
    ):
        self._url = url
        self._queue = log_queue
        self._batch_size = batch_size
        self._flush_interval = flush_interval
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        self._thread = None
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

    def start(self):
        self._thread = threading.Thread(
            target=self._run, name="AYONVectorSender", daemon=True
        )
        self._thread.start()

    def stop(self, timeout=5.0):
        """Send records remaining in the queue and stop the thread."""
        if self._thread is None:
            return
        try:
            self._queue.put(self._stop_sentinel, timeout=timeout)
        except queue.Full:
            pass
        self._thread.join(timeout)
        self._thread = None
        self._session.close()

    def _run(self):
        stop = False
        while not stop:
            item = self._queue.get()
            if item is self._stop_sentinel:
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
                if item is self._stop_sentinel:
                    stop = True
                    break
                batch.append(item)
            self._send(batch)

    def _send(self, batch):
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


class _StderrHandler(logging.StreamHandler):
    """StreamHandler writing to the current 'sys.stderr'.

    Hosts and AYON tools replace 'sys.stderr' after logging is configured.
    'logging.StreamHandler' would keep writing to the stream it received
    on creation. Same approach as stdlib 'logging._StderrHandler'.

    Logs go to stderr so stdout of AYON CLI commands stays usable for
    their output, same as the previous 'LogStreamHandler' default.
    """

    def __init__(self, level=logging.NOTSET):
        logging.Handler.__init__(self, level)

    @property
    def stream(self):
        return sys.stderr

    def emit(self, record):
        # 'sys.stderr' is None in GUI processes without console
        if sys.stderr is not None:
            super().emit(record)


class LogStreamHandler(logging.StreamHandler):
    """StreamHandler class.

    This was originally designed to handle UTF errors in python 2.x hosts,
    however currently solely remains for backwards compatibility.

    """

    def __init__(self, stream=None):
        super(LogStreamHandler, self).__init__(stream)
        self.enabled = True

    def enable(self):
        """Enable StreamHandler

        Make StreamHandler output again
        """
        self.enabled = True

    def disable(self):
        """Disable StreamHandler

        Used to silence output
        """
        self.enabled = False

    def emit(self, record):
        if not self.enabled or self.stream is None:
            return
        try:
            msg = self.format(record)
            msg = Terminal.log(msg)
            stream = self.stream
            stream.write(f"{msg}\n")
            self.flush()
        except (KeyboardInterrupt, SystemExit):
            raise

        except OSError:
            self.handleError(record)

        except Exception:
            sys.stderr.write(f"{record!r}\n")
            self.handleError(record)


class LogFormatter(logging.Formatter):

    DFT = '%(levelname)s >>> { %(name)s }: [ %(message)s ]'
    default_formatter = logging.Formatter(DFT)

    def __init__(self, formats):
        super(LogFormatter, self).__init__()
        self.formatters = {}
        for loglevel in formats:
            self.formatters[loglevel] = logging.Formatter(formats[loglevel])

    def format(self, record):
        formatter = self.formatters.get(record.levelno, self.default_formatter)

        _exc_info = record.exc_info
        record.exc_info = None

        out = formatter.format(record)
        record.exc_info = _exc_info

        if record.exc_info is not None:
            line_len = len(str(record.exc_info[1]))
            if line_len > 30:
                line_len = 30
            out = "{}\n{}\n{}\n{}\n{}".format(
                out,
                line_len * "=",
                str(record.exc_info[1]),
                line_len * "=",
                self.formatException(record.exc_info)
            )
        return out


def _deprecated_getter(func):
    def _get_logger_deprecate(cls, name: str | None = None) -> logging.Logger:
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
    DFT = '%(levelname)s >>> { %(name)s }: [ %(message)s ] '
    DBG = "  - { %(name)s }: [ %(message)s ] "
    INF = ">>> [ %(message)s ] "
    WRN = "*** WRN: >>> { %(name)s }: [ %(message)s ] "
    ERR = "!!! ERR: %(asctime)s >>> { %(name)s }: [ %(message)s ] "
    CRI = "!!! CRI: %(asctime)s >>> { %(name)s }: [ %(message)s ] "

    FORMAT_FILE = {
        logging.INFO: INF,
        logging.DEBUG: DBG,
        logging.WARNING: WRN,
        logging.ERROR: ERR,
        logging.CRITICAL: CRI,
    }

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
    def get_logger(cls, name: str) -> Any | logging.Logger:
        """Get a logger by name, initializing the logging system if necessary.

        Reparent the underlying stdlib logger under the "AYON" root so
        its effective level/propagation is controlled from one place,
        regardless of where the logger's dotted name places it in the
        stdlib logger hierarchy.

        Args:
            name (str): The name of the logger to retrieve.

        Returns:
            logging.Logger: The logger instance associated with the given name.

        """
        if not cls.initialized:
            cls.initialize()

        name = name or "__main__"

        logger = logging.getLogger(name)
        if logger is not cls._root_logger:
            logger.parent = cls._root_logger

        # Delegate to structlog when configured so records share the same
        # processors (e.g. 'site_id', timestamps) as the rest of the app.
        if structlog is not None and structlog.is_configured():
            return structlog.get_logger(name)

        return logger

    @classmethod
    def get_root_logger(cls) -> logging.Logger:
        if not cls.initialized:
            cls.initialize()
        return cls._root_logger  # type: ignore[invalid-return-type, return-value]

    @classmethod
    def _get_console_handler(cls):
        formatter = LogFormatter(cls.FORMAT_FILE)
        console_handler = LogStreamHandler()

        console_handler.set_name("LogStreamHandler")
        console_handler.setFormatter(formatter)
        return console_handler

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
        # Skip own handler when structlog already owns the output pipeline
        # to avoid double-formatting/handling the same records.
        # - with structlog the records must propagate to the root logger
        #   where the structlog handlers are.
        if structlog is None or not structlog.is_configured():
            # Records are already printed by the own handler, don't pass
            #   them to root logger handlers too (e.g. DCC script editor).
            root_logger.propagate = False
            root_logger.addHandler(cls._get_console_handler())
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
        if structlog is None:
            return

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

        console_formatter = _EventDictProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _drop_log_context,
                structlog.dev.ConsoleRenderer(
                    exception_formatter=structlog.dev.rich_traceback,
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

        handler = _StderrHandler()
        handler.setFormatter(console_formatter)

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
            log_queue: queue.Queue = queue.Queue(VECTOR_QUEUE_MAX_SIZE)
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
