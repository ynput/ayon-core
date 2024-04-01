import os
import sys
import uuid
import getpass
import logging
import platform
import socket
import time
import threading
import copy

from . import Terminal

# Check for `unicode` in builtins
USE_UNICODE = hasattr(__builtins__, "unicode")


class LogStreamHandler(logging.StreamHandler):
    """ StreamHandler class designed to handle utf errors in python 2.x hosts.

    """

    def __init__(self, stream=None):
        super(LogStreamHandler, self).__init__(stream)
        self.enabled = True

    def enable(self):
        """ Enable StreamHandler

            Used to silence output
        """
        self.enabled = True

    def disable(self):
        """ Disable StreamHandler

            Make StreamHandler output again
        """
        self.enabled = False

    def emit(self, record):
        if not self.enable:
            return
        try:
            msg = self.format(record)
            msg = Terminal.log(msg)
            stream = self.stream
            if stream is None:
                return
            fs = "%s\n"
            # if no unicode support...
            if not USE_UNICODE:
                stream.write(fs % msg)
            else:
                try:
                    if (isinstance(msg, unicode) and  # noqa: F821
                            getattr(stream, 'encoding', None)):
                        ufs = u'%s\n'
                        try:
                            stream.write(ufs % msg)
                        except UnicodeEncodeError:
                            stream.write((ufs % msg).encode(stream.encoding))
                    else:
                        if (getattr(stream, 'encoding', 'utf-8')):
                            ufs = u'%s\n'
                            stream.write(ufs % unicode(msg))  # noqa: F821
                        else:
                            stream.write(fs % msg)
                except UnicodeError:
                    stream.write(fs % msg.encode("UTF-8"))
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

    # Logging level - AYON_LOG_LEVEL
    log_level = None

    # Data same for all record documents
    process_data = None
    # Cached process name or ability to set different process name
    _process_name = None
    # TODO Remove 'mongo_process_id' in 1.x.x
    mongo_process_id = uuid.uuid4().hex

    @classmethod
    def get_logger(cls, name=None):
        if not cls.initialized:
            cls.initialize()

        logger = logging.getLogger(name or "__main__")

        logger.setLevel(cls.log_level)

        add_console_handler = True

        for handler in logger.handlers:
            if isinstance(handler, LogStreamHandler):
                add_console_handler = False

        if add_console_handler:
            logger.addHandler(cls._get_console_handler())

        # Do not propagate logs to root logger
        logger.propagate = False

        return logger

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
