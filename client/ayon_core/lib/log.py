from __future__ import annotations

import copy
import getpass
import logging
import queue
from logging.handlers import QueueHandler, QueueListener
import os
import platform
import requests
import requests.adapters
import socket
import sys
import time
import threading
import warnings

import structlog

from . import Terminal

VECTOR_LOG_URL = os.getenv("AYON_VECTOR_LOG_URL", None)


class _RawQueueHandler(QueueHandler):
    """QueueHandler that does not pre-format/stringify the record.

    The stdlib's default 'prepare' stringifies 'record.msg', which
    destroys the structlog event dict before it reaches the listener's
    handlers.
    """

    def prepare(self, record):
        return record


class VectorHTTPHandler(logging.Handler):
    """Forward formatted log records to a Vector HTTP source."""

    def __init__(self, url):
        super().__init__()
        self._url = url
        # Reuse a single session so repeated POSTs reuse pooled
        # connections instead of opening a new one per log record.
        self._session = requests.Session()
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=1, pool_maxsize=10
        )
        self._session.mount("http://", adapter)
        self._session.mount("https://", adapter)

    def emit(self, record):
        try:
            self._session.post(
                self._url,
                data=self.format(record),
                headers={"Content-Type": "application/json"},
                timeout=1,
            )
        except Exception:
            self.handleError(record)

    def close(self):
        self._session.close()
        super().close()


def configure_logger() -> None:
    """Configure logging for the application.

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

    def _drop_site_id(logger, method_name, event_dict):
        # Keep 'site_id' in JSON sent to Vector but not in console output
        event_dict.pop("site_id", None)
        return event_dict

    shared_processors = [
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
            structlog.dev.ConsoleRenderer(),
        ],
    )
    json_formatter = structlog.stdlib.ProcessorFormatter(
            foreign_pre_chain=shared_processors,
            processor=structlog.processors.JSONRenderer(),
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(console_formatter)

    if VECTOR_LOG_URL:
        # Send logs to Vector asynchronously so HTTP calls don't block the app.
        vector_handler = VectorHTTPHandler(VECTOR_LOG_URL)
        vector_handler.setFormatter(json_formatter)
        log_queue = queue.Queue(-1)
        queue_handler = _RawQueueHandler(log_queue)
        queue_listener = QueueListener(
            log_queue, vector_handler, respect_handler_level=True
        )
        queue_listener.start()

    root_logger = logging.getLogger()
    root_logger.addHandler(handler)
    if VECTOR_LOG_URL:
        root_logger.addHandler(queue_handler)
    root_logger.setLevel(
        logging.INFO if os.getenv("AYON_DEBUG") != "1" else logging.DEBUG)

    # 'Logger' (ayon_core.lib.log) may have attached its own fallback
    # console handler to the "AYON" logger before structlog was configured.
    # Drop it and let records propagate to the root logger instead, which
    # now owns the shared handlers - avoids logging each record twice.
    ayon_logger = Logger.get_root_logger()
    for old_handler in list(ayon_logger.handlers):
        ayon_logger.removeHandler(old_handler)


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
    def get_logger(cls, name: str) -> logging.Logger:
        if not cls.initialized:
            cls.initialize()

        # Delegate to structlog when configured so records share the same
        # processors (e.g. 'site_id', timestamps) as the rest of the app.
        if structlog.is_configured():
            return structlog.get_logger(name or "__main__")

        logger = logging.getLogger(name or "__main__")
        logger.setLevel(cls.log_level)
        logger.parent = cls._root_logger

        return logger

    @classmethod
    def get_root_logger(cls) -> logging.Logger:
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
        if not structlog.is_configured():
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
