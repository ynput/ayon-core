from __future__ import annotations

import atexit
import copy
import getpass
import logging
import queue
from logging.handlers import (
    QueueHandler,
    QueueListener,
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
from typing import Any
import warnings

import urllib3.util

from . import Terminal
from .local_settings import get_launcher_local_dir


# If structlog is missing (ayon-launcher is outdated),
# the library will fall back to standard logging.

structlog: Any = None
try:
    import structlog as _structlog
except ImportError:
    pass
else:
    structlog = _structlog


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


VECTOR_LOG_URL = os.getenv("AYON_VECTOR_LOG_URL", None)
LOG_FILE_ENABLED = os.getenv("AYON_LOG_FILE") == "1"
LOG_FILE_RETENTION_DAYS = int(os.getenv("AYON_LOG_RETENTION_DAYS", "1"))
LOG_FILE_NAME = "ayon.ndjson"

# Max records buffered for Vector delivery. Beyond this, new records are
# dropped rather than growing memory unbounded during an outage.
VECTOR_QUEUE_MAX_SIZE = 10_000
# Consecutive send failures after which the circuit opens (stop trying
# HTTP calls for a while, just drop records fast).
VECTOR_FAILURE_THRESHOLD = 5
# How long the circuit stays open once tripped.
VECTOR_CIRCUIT_COOLDOWN = 30.0
# Minimum time between "records are being dropped" warnings, to avoid
# flooding the console/log file during a prolonged outage.
VECTOR_WARN_INTERVAL = 30.0


class _RateLimitedLogger:
    """Log a warning at most once per 'interval' seconds."""

    def __init__(self, logger, interval):
        self._logger = logger
        self._interval = interval
        self._last_emit = 0.0

    def warning(self, msg, **kwargs):
        now = time.monotonic()
        if now - self._last_emit < self._interval:
            return
        self._last_emit = now
        self._logger.warning(msg, **kwargs)


_vector_warn_logger = _RateLimitedLogger(
    logging.getLogger("ayon.vector_log"), VECTOR_WARN_INTERVAL
)


class _RawQueueHandler(QueueHandler):
    """QueueHandler that does not pre-format/stringify the record.

    The stdlib's default 'prepare' stringifies 'record.msg', which
    destroys the structlog event dict before it reaches the listener's
    handlers.
    """

    def prepare(self, record):
        return record

    def enqueue(self, record):
        # handle full queue gracefully by dropping
        # the record instead of raising.
        try:
            self.queue.put_nowait(record)
        except queue.Full:
            _vector_warn_logger.warning(
                "Vector log queue is full, dropping log records."
            )


class VectorHTTPHandler(logging.Handler):
    """Forward formatted log records to a Vector HTTP source."""

    def __init__(
        self,
        url,
        failure_threshold=VECTOR_FAILURE_THRESHOLD,
        cooldown=VECTOR_CIRCUIT_COOLDOWN,
    ):
        super().__init__()
        self._url = url
        self._failure_threshold = failure_threshold
        self._cooldown = cooldown
        self._consecutive_failures = 0
        self._circuit_open_until = 0.0
        # Reuse a single session so repeated POSTs reuse pooled
        # connections instead of opening a new one per log record.
        self._session = requests.Session()
        retry = urllib3.util.Retry(
            total=2,
            backoff_factor=0.3,
            status_forcelist=(502, 503, 504),
            allowed_methods=("POST",),
        )
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1, pool_maxsize=10, max_retries=retry
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def emit(self, record):
        now = time.monotonic()
        if now < self._circuit_open_until:
            # Circuit is open - skip the HTTP attempt entirely so a dead
            # Vector endpoint cannot slow down the sender thread.
            return
        try:
            self._session.post(
                self._url,
                data=self.format(record),
                headers={"Content-Type": "application/json"},
                timeout=(0.3, 1.0),
            )
        except Exception:
            self._consecutive_failures += 1
            if self._consecutive_failures >= self._failure_threshold:
                self._circuit_open_until = now + self._cooldown
                self._consecutive_failures = 0
                _vector_warn_logger.warning(
                    "Vector endpoint unreachable, pausing log delivery.",
                    cooldown=self._cooldown,
                )
            self.handleError(record)
        else:
            self._consecutive_failures = 0

    def handleError(self, record):
        # Rate-limit warnings in case of Vector outage.
        _vector_warn_logger.warning("Failed to send log record to Vector.")

    def close(self):
        self._session.close()
        super().close()


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
            print(repr(record))
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
    def get_root_logger(cls) -> logging.Logger | None:
        if not cls.initialized:
            cls.initialize()
        return cls._root_logger

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
        if not cls._init_lock.locked():
            with cls._init_lock:
                cls._initialize()
        else:
            # If lock is locked wait until is finished
            while cls._init_lock.locked():
                time.sleep(0.1)

    @classmethod
    def _initialize(cls):
        # Change initialization state to prevent runtime changes
        # if is executed during runtime
        cls.initialized = False
        cls.configure_logger()

        # Define what is logging level
        log_level = os.getenv("AYON_LOG_LEVEL")
        if not log_level:
            # Check AYON_DEBUG for debug level
            op_debug = os.getenv("AYON_DEBUG")
            if op_debug and int(op_debug) > 0:
                log_level = 10
            else:
                log_level = 20
        cls.log_level = int(log_level)
        root_logger = logging.getLogger("AYON")
        # root_logger.propagate = False
        root_logger.setLevel(cls.log_level)
        # Skip own handler when structlog already owns the output pipeline
        # to avoid double-formatting/handling the same records.
        if structlog is None or not structlog.is_configured():
            root_logger.addHandler(cls._get_console_handler())
        cls._root_logger = root_logger

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

        def _drop_site_id(logger, method_name, event_dict):
            # Keep 'site_id' in JSON sent to Vector but not in console output
            event_dict.pop("site_id", None)
            return event_dict

        shared_processors = [
            structlog.contextvars.merge_contextvars,
            structlog.processors.add_log_level,
            structlog.stdlib.add_logger_name,
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.StackInfoRenderer(),
            _add_site_id,
        ]

        structlog.configure(
            processors=shared_processors + [
                # Prepares details if sent to standard logging
                structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
            ],
            logger_factory=structlog.stdlib.LoggerFactory(),
            wrapper_class=structlog.stdlib.BoundLogger,
            cache_logger_on_first_use=True,
        )

        console_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors + [
                structlog.stdlib.PositionalArgumentsFormatter(),
            ],
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                _drop_site_id,
                structlog.dev.ConsoleRenderer(
                    exception_formatter=structlog.dev.rich_traceback,
                ),
            ],
        )
        json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processors=[
                structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                structlog.processors.format_exc_info,
                structlog.processors.JSONRenderer(),
            ],
        )

        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(console_formatter)

        if LOG_FILE_ENABLED:
            log_dir = get_launcher_local_dir("logs")
            os.makedirs(log_dir, exist_ok=True)
            file_handler = TimedRotatingFileHandler(
                os.path.join(log_dir, LOG_FILE_NAME),
                when="midnight",
                backupCount=LOG_FILE_RETENTION_DAYS,
                encoding="utf-8",
            )
            file_handler.setFormatter(json_formatter)

        if VECTOR_LOG_URL:
            # Send logs to Vector asynchronously so HTTP calls
            # don't block the app.
            vector_handler = VectorHTTPHandler(VECTOR_LOG_URL)
            vector_handler.setFormatter(json_formatter)
            # Queue is bounded so a Vector outage drops records instead of
            # growing memory without bound.
            log_queue: queue.Queue = queue.Queue(VECTOR_QUEUE_MAX_SIZE)
            queue_handler = _RawQueueHandler(log_queue)
            queue_listener = QueueListener(
                log_queue, vector_handler, respect_handler_level=True
            )
            queue_listener.start()
            # The listener thread is non-daemon by default and otherwise
            # would keep the process alive/delay shutdown since
            # 'queue_listener.stop()' is never called explicitly elsewhere.
            if queue_listener._thread is not None:
                queue_listener._thread.daemon = True
            atexit.register(queue_listener.stop)

        root_logger = logging.getLogger()
        root_logger.addHandler(handler)
        if LOG_FILE_ENABLED:
            root_logger.addHandler(file_handler)
        if VECTOR_LOG_URL:
            root_logger.addHandler(queue_handler)
        # set default logging level to INFO, but
        # allow override via AYON_LOG_LEVEL or AYON_DEBUG
        root_logger.setLevel(logging.INFO)
        if os.getenv("AYON_LOG_LEVEL") is not None:
            root_logger.setLevel(int(
                os.getenv("AYON_LOG_LEVEL", logging.INFO)))
        if os.getenv("AYON_DEBUG") is not None:
            root_logger.setLevel(logging.DEBUG)

        # 'Logger' (ayon_core.lib.log) may have attached its own fallback
        # console handler to the "AYON" logger before structlog was configured.
        # Drop it and let records propagate to the root logger instead, which
        # now owns the shared handlers - avoids logging each record twice.
        ayon_logger = logging.getLogger("AYON")
        for old_handler in list(ayon_logger.handlers):
            ayon_logger.removeHandler(old_handler)
