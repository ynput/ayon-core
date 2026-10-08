from __future__ import annotations

import atexit
import collections
import copy
from dataclasses import dataclass, field
import inspect
import json
import logging
import os
import re
import ssl
import threading
import typing
from typing import Any, Callable
import weakref

from ayon_api import get_server_api_connection
import requests
from websocket import ABNF, create_connection

if typing.TYPE_CHECKING:
    from websocket import WebSocket

    from ayon_api.server_api import ServerAPI


@dataclass
class Event:
    topic: str
    data: dict[str, Any] = field(default_factory=dict)
    id: str | None = None
    sender: str | None = None
    event_hash: str | None = None
    project_name: str | None = None
    dependencies: list[str] | None = None
    description: str | None = None
    summary: str | None = None
    payload: dict[str, Any] | None = None
    status: str | None = None
    store: bool | None = None

    def __getitem__(self, key) -> Any:
        return self.data[key]

    def get(self, key, default=None) -> Any:
        return self.data.get(key, default)

    @classmethod
    def from_ws_message(cls, data: dict[str, Any]) -> Event | None:
        topic = data.get("topic")
        if topic is None:
            return None

        return cls(
            topic=topic,
            data=data,
            id=data.get("id"),
            sender=data.get("sender"),
            event_hash=data.get("eventHash"),
            project_name=data.get("project"),
            dependencies=data.get("dependsOn"),
            description=data.get("description"),
            summary=data.get("summary"),
            payload=data.get("payload"),
            status=data.get("status"),
            store=data.get("store"),
        )


def is_func_signature_supported(func, *args, **kwargs):
    """Check if a function signature supports passed args and kwargs.

    This check does not actually call the function, just look if function can
    be called with the arguments.

    Notes:
        This does NOT check if the function would work with passed arguments
            only if they can be passed in. If function have *args, **kwargs
            in parameters, this will always return 'True'.

    Example:
        >>> def my_function(my_number):
        ...     return my_number + 1
        ...
        >>> is_func_signature_supported(my_function, 1)
        True
        >>> is_func_signature_supported(my_function, 1, 2)
        False
        >>> is_func_signature_supported(my_function, my_number=1)
        True
        >>> is_func_signature_supported(my_function, number=1)
        False
        >>> is_func_signature_supported(my_function, "string")
        True
        >>> def my_other_function(*args, **kwargs):
        ...     my_function(*args, **kwargs)
        ...
        >>> is_func_signature_supported(
        ...     my_other_function,
        ...     "string",
        ...     1,
        ...     other=None
        ... )
        True

    Args:
        func (Callable): A function where the signature should be tested.
        *args (Any): Positional arguments for function signature.
        **kwargs (Any): Keyword arguments for function signature.

    Returns:
        bool: Function can pass in arguments.

    """
    sig = inspect.signature(func)
    try:
        sig.bind(*args, **kwargs)
        return True
    except TypeError:
        pass
    return False


def _get_func_ref(func: Callable) -> weakref.ref:
    if inspect.ismethod(func):
        return weakref.WeakMethod(func)
    return weakref.ref(func)


def _get_func_info(func: Callable) -> tuple[str, str]:
    path = "<unknown path>"
    if func is None:
        return "<unknown>", path

    if hasattr(func, "__name__"):
        name = func.__name__
    else:
        name = str(func)

    # Get path to file and fallback to '<unknown path>' if fails
    # NOTE This was added because of 'partial' functions which is handled,
    #   but who knows what else can cause this to fail?
    try:
        path = os.path.abspath(inspect.getfile(func))
    except TypeError:
        pass

    return name, path


class weakref_partial:
    """Partial function with weak reference to the wrapped function.

    Can be used as 'functools.partial' but it will store weak reference to
        function. That means that the function must be reference counted
        to avoid garbage collecting the function itself.

        When the referenced functions is garbage collected then calling the
        weakref partial (no matter the args/kwargs passed) will do nothing.
        It will fail silently, returning `None`. The `is_valid()` method can
        be used to detect whether the reference is still valid.

    Is useful for object methods. In that case the callback is
        deregistered when object is destroyed.

    Warnings:
        Values passed as *args and **kwargs are stored strongly in memory.
            That may "keep alive" objects that should be already destroyed.
            It is recommended to pass only immutable objects like 'str',
            'bool', 'int' etc.

    Args:
        func (Callable): Function to wrap.
        *args: Arguments passed to the wrapped function.
        **kwargs: Keyword arguments passed to the wrapped function.
    """

    def __init__(self, func: Callable, *args, **kwargs) -> None:
        self._func_ref: weakref.ref = _get_func_ref(func)
        self._args: tuple = args
        self._kwargs: dict = kwargs

    def __call__(self, *args, **kwargs) -> Any:
        func = self._func_ref()
        if func is None:
            return None

        new_args = tuple(list(self._args) + list(args))
        new_kwargs = dict(self._kwargs)
        new_kwargs.update(kwargs)
        return func(*new_args, **new_kwargs)

    def get_func(self) -> Callable | None:
        """Get wrapped function.

        Returns:
            Callable | None: Wrapped function or None if it was destroyed.

        """
        return self._func_ref()

    def is_valid(self) -> bool:
        """Check if wrapped function is still valid.

        Returns:
            bool: Is wrapped function still valid.

        """
        return self._func_ref() is not None

    def validate_signature(self, *args, **kwargs) -> bool:
        """Validate if passed arguments are supported by wrapped function.

        Returns:
            bool: Are passed arguments supported by wrapped function.

        """
        func = self._func_ref()
        if func is None:
            return False

        new_args = tuple(list(self._args) + list(args))
        new_kwargs = dict(self._kwargs)
        new_kwargs.update(kwargs)
        return is_func_signature_supported(
            func, *new_args, **new_kwargs
        )


class EventCallback:
    """Callback registered to a topic.

    The callback function is registered to a topic. Topic is a string which
    may contain '*' that will be handled as "any characters".

    # Examples:
    - "entity.folder.attr_changed" - Callback will be triggered if the event
        topic is exactly "entity.folder.attr_changed".
    - "entity.*" - Callback will be triggered an event topic starts with
        "entity." so "entity.folder.created" and "entity.version.created"
        will trigger the callback.
    - "*" Callback will listen to all events.

    Callback can be function or method. In both cases it should expect one
    or none arguments. When 1 argument is expected then the processed 'Event'
    object is passed in.

    The callbacks are validated against their reference counter, that is
        achieved using 'weakref' module. That means that the callback must
        be stored in memory somewhere. e.g. lambda functions are not
        supported as valid callback.

    You can use 'weakref_partial' functions. In that case is partial object
        stored in the callback object and reference counter is checked for
        the wrapped function.

    Args:
        topic (str): Topic which will be listened.
        func (Callable): Callback to a topic.
        order (int | None): Order of callback. Lower number means higher
            priority.

    Raises:
        TypeError: When passed function is not a callable object.
    """
    default_order: int = 100

    def __init__(
        self, topic: str, func: Callable, order: int | None = None
    ) -> None:
        if not callable(func):
            raise TypeError(
                f"Registered callback is not callable. \"{func}\""
            )

        if order is None:
            order = self.default_order
        self._validate_order(order)

        self._log = None
        self._topic: str = topic
        self._order: int = order
        self._enabled: bool = True
        # Replace '*' with any character regex and escape rest of text
        #   - when callback is registered for '*' topic it will receive all
        #       events
        #   - it is possible to register to a partial topis 'my.event.*'
        #       - it will receive all matching event topics
        #           e.g. 'my.event.start' and 'my.event.end'
        topic_regex_str = "^{}$".format(
            ".+".join(
                re.escape(part)
                for part in topic.split("*")
            )
        )
        topic_regex = re.compile(topic_regex_str)
        self._topic_regex: re.Pattern = topic_regex

        # Callback function prep
        if isinstance(func, weakref_partial):
            partial_func = func
            (name, path) = _get_func_info(func.get_func())
            func_ref = None
            expect_args = partial_func.validate_signature("fake")
            expect_kwargs = partial_func.validate_signature(event="fake")

        else:
            partial_func = None
            (name, path) = _get_func_info(func)
            # Convert callback into references
            #   - deleted functions won't cause crashes
            func_ref = _get_func_ref(func)

            # Get expected arguments from function spec
            # - positional arguments are always preferred
            expect_args = is_func_signature_supported(func, "fake")
            expect_kwargs = is_func_signature_supported(func, event="fake")

        self._func_ref: weakref.ref | None = func_ref
        self._partial_func: weakref_partial | None = partial_func
        self._ref_is_valid: bool = True
        self._expect_args: bool = expect_args
        self._expect_kwargs: bool = expect_kwargs

        self._name: str = name
        self._path: str = path

    def __repr__(self) -> str:
        return f"< {self.__class__.__name__} - {self._name} > {self._path}"

    @property
    def log(self) -> logging.Logger:
        if self._log is None:
            self._log = logging.getLogger(self.__class__.__name__)
        return self._log

    @property
    def topic(self) -> str:
        return self._topic

    @property
    def is_ref_valid(self) -> bool:
        """

        Returns:
            bool: Is reference to callback valid.

        """
        self._validate_ref()
        return self._ref_is_valid

    def validate_ref(self) -> None:
        """Validate if reference to callback is valid.

        Deprecated:
            Reference is always live checkd with 'is_ref_valid'.

        """
        # Trigger validate by getting 'is_valid'
        _ = self.is_ref_valid

    @property
    def enabled(self) -> bool:
        """Is callback enabled.

        Returns:
            bool: Is callback enabled.

        """
        return self._enabled

    def set_enabled(self, enabled: bool) -> None:
        """Change if callback is enabled.

        Args:
            enabled (bool): Change enabled state of the callback.

        """
        self._enabled = enabled

    def deregister(self) -> None:
        """Calling this function will cause that callback will be removed."""
        self._ref_is_valid = False
        self._partial_func = None
        self._func_ref = None

    def get_order(self) -> int:
        """Get callback order.

        Returns:
            int: Callback order.

        """
        return self._order

    def set_order(self, order: int) -> None:
        """Change callback order.

        Args:
            order (int): Order of callback. Lower number means
                higher priority.

        """
        self._validate_order(order)
        self._order = order

    order = property(get_order, set_order)

    def topic_matches(self, topic: str) -> bool:
        """Check if event topic matches callback's topic.

        Args:
            topic (str): Topic name.

        Returns:
            bool: Topic matches callback's topic.

        """
        return self._topic_regex.match(topic)

    def process_event(self, event: Event) -> None:
        """Process event.

        Args:
            event(Event): Event that was triggered.

        """
        # Skip if callback is not enabled
        if not self._enabled:
            return

        # Get reference and skip if is not available
        callback = self._get_callback()
        if callback is None:
            return

        if not self.topic_matches(event.topic):
            return

        # Try to execute callback
        try:
            if self._expect_args:
                callback(event)

            elif self._expect_kwargs:
                callback(event=event)

            else:
                callback()

        except Exception:
            self.log.warning(
                f"Failed to execute event callback {repr(self)}",
                exc_info=True
            )

    def _validate_order(self, order: int) -> None:
        if isinstance(order, int):
            return

        raise TypeError(f"Expected type 'int' got '{type(order)}'.")

    def _get_callback(self) -> Callable | None:
        if self._partial_func is not None:
            return self._partial_func

        if self._func_ref is not None:
            return self._func_ref()
        return None

    def _validate_ref(self) -> None:
        if self._ref_is_valid is False:
            return

        if self._func_ref is not None:
            self._ref_is_valid = self._func_ref() is not None

        elif self._partial_func is not None:
            self._ref_is_valid = self._partial_func.is_valid()

        else:
            self._ref_is_valid = False

        if not self._ref_is_valid:
            self._func_ref = None
            self._partial_func = None


# Server sends 'heartbeat' message to authorized clients when there was no
#   other message for ~5 seconds. If nothing arrives for this amount of time
#   the connection is considered dead.
_RECV_TIMEOUT: float = 15.0
# Timeout for opening websocket connection and for the auth check request.
_CONNECT_TIMEOUT: float = 5.0
# Delays between reconnection attempts (last value is used repeatedly).
_RECONNECT_DELAYS: tuple[float, ...] = (0.5, 1.0, 2.0, 5.0)
# Delay between reconnection attempts when the token is known to be invalid.
_AUTH_FAILED_DELAY: float = 30.0
# How long to wait for the loop thread on stop. The thread is daemon so
#   it can't block process exit even if it does not finish in time.
_STOP_TIMEOUT: float = 1.0


def _abort_ws(ws_con: WebSocket) -> None:
    """Close websocket without waiting for server response.

    'WebSocket.close' sends close frame and waits for the response
        (up to 3 seconds) which would block the caller.

    """
    for method_name in ("abort", "shutdown"):
        method = getattr(ws_con, method_name, None)
        if method is None:
            continue
        try:
            method()
            return
        except Exception:
            pass


@dataclass
class _LoopState:
    stop_event: threading.Event = field(default_factory=threading.Event)
    # Subscribe message has to be sent
    auth_required: bool = False
    # Some message was received with current websocket connection
    received_message: bool = False
    # Connection state reported via events
    #   - 'None' means unknown (nothing was reported yet)
    connected: bool | None = None
    auth_failed: bool = False
    failed_attempts: int = 0
    registered_topics: set[str] = field(default_factory=set)
    server_is_restarting: bool = False


class EventHub:
    """Receive AYON server events via websocket and trigger callbacks.

    Websocket connection is handled in a daemon thread, so it never blocks
        the caller (e.g. DCC main thread) nor the process exit.

    Warnings:
        Callbacks are triggered in the websocket thread! Use
            'WSEventsModel' (or own queue) to process them in main thread,
            especially if a callback touches Qt widgets.

    Internal topics:
        - 'connection.opened' first message received after (re)connection.
        - 'connection.closed' connection was lost or could not be created.
        - 'auth.failed' server rejected the token.

    Args:
        connection (ServerAPI | None): Server connection. Global connection
            is used if not passed.

    """

    def __init__(self, connection: ServerAPI | None = None) -> None:
        if connection is None:
            connection = get_server_api_connection()

        self._log = logging.getLogger(self.__class__.__name__)
        self._connection: ServerAPI = connection
        self._ws_connection: WebSocket | None = None
        self._loop_state: _LoopState = _LoopState()
        self._loop_thread: threading.Thread | None = None
        self._thread_lock = threading.Lock()
        self._callbacks_lock = threading.RLock()
        self._registered_callbacks: list[EventCallback] = []
        self._internal_callbacks: list[EventCallback] = [
            EventCallback(
                "server.restart_requested", self._on_server_restart,
            ),
        ]
        self.add_callbacks(self._internal_callbacks, connect=False)
        atexit.register(self._stop)

    def is_running(self) -> bool:
        """Check if event loop is running.

        Returns:
            bool: Is event loop running.

        """
        thread = self._loop_thread
        return thread is not None and thread.is_alive()

    def is_connected(self) -> bool:
        """Check if event loop is connected to server.

        Returns:
            bool: Is event loop connected to server.

        """
        return self._loop_state.connected is True

    def get_connection_state(self) -> bool | None:
        """Connection state as was reported by events.

        Returns:
            bool | None: 'True' if connected, 'False' if disconnected and
                'None' if state is not known yet.

        """
        return self._loop_state.connected

    def is_auth_failed(self) -> bool:
        return self._loop_state.auth_failed

    def is_server_restarting(self) -> bool:
        return self._loop_state.server_is_restarting

    def add_callback(
        self,
        topic: str,
        callback: Callable | weakref_partial,
        order: int | None = None,
        *,
        connect: bool = True,
    ) -> EventCallback:
        """Register callback in event system.

        Args:
            topic (str): Topic for EventCallback.
            callback (Callable | weakref_partial): Function or method
                that will be called when topic is triggered.
            order (int | None): Order of callback. Lower number means
                higher priority.
            connect (bool): Create websocket connection if
                not already created.

        Returns:
            EventCallback: Created callback object which can be used to
                stop listening.

        """
        callback = EventCallback(topic, callback, order)
        self.add_callbacks(
            [callback], connect=connect
        )
        return callback

    def add_callbacks(
        self,
        callbacks: list[EventCallback],
        *,
        connect: bool = True,
    ) -> None:
        """Register callback in event system.

        Args:
            callbacks (list[EventCallback]): List of EventCallback
                objects to register.
            connect (bool): Create websocket connection if
                not already created.

        """
        with self._callbacks_lock:
            self._registered_callbacks.extend(callbacks)
            self._update_topics()
        if connect:
            self.start()

    def emit_event(self, event: Event) -> None:
        """Emit event object.

        Args:
            event (Event): Prepared event with topic and data.

        """
        self._process_event(event)

    def start(self) -> None:
        """Start event loop.

        Websocket connection is created in a daemon thread, this method
            does not block.

        """
        with self._thread_lock:
            if self.is_running():
                return

            stop_event = threading.Event()
            self._loop_state.stop_event = stop_event
            loop_thread = threading.Thread(
                target=self._thread_loop,
                args=(stop_event,),
                name="AYONEventHub",
                # Daemon thread must be used! Non-daemon threads are joined
                #   by the interpreter BEFORE 'atexit' callbacks are called,
                #   so the process would hang on exit.
                daemon=True,
            )
            self._loop_thread = loop_thread
            loop_thread.start()

    def stop(self) -> None:
        self._stop()

    def _stop(self) -> None:
        with self._thread_lock:
            loop_thread, self._loop_thread = self._loop_thread, None
            self._loop_state.stop_event.set()
            ws_con = self._ws_connection

        # Unblock 'recv' in the loop thread
        if ws_con is not None:
            _abort_ws(ws_con)

        if (
            loop_thread is not None
            and loop_thread is not threading.current_thread()
        ):
            loop_thread.join(_STOP_TIMEOUT)

    def _update_topics(self) -> None:
        """Subscribe to topics in server based on registered callbacks.

        Server does not allow wildcards in the topic but does validate
            start of the topic so 'entity.folder.*' is not allowed
            but 'entity.folder.' does work.

        In case the wildcard is used at the start of the topic we have to
            subscribe to all topics.

        """
        topics = set()
        with self._callbacks_lock:
            callbacks = list(self._registered_callbacks)

        for callback in callbacks:
            topic = callback.topic
            if topic == "*":
                topics.add(topic)
                continue
            parts = topic.split("*", maxsplit=1)
            if len(parts) == 1:
                topics.add(topic)
                continue

            part = parts[0]
            if part:
                topics.add(part)
            else:
                topics.add("*")

        if topics == self._loop_state.registered_topics:
            return

        self._loop_state.registered_topics = topics
        self._loop_state.auth_required = True

    def _get_ws_url(self, endpoint: str) -> str:
        endpoint = (endpoint or "").strip()
        base_url = self._connection.get_base_url()
        if base_url.startswith("https"):
            base_url = f"wss{base_url[5:]}"
        elif base_url.startswith("http"):
            base_url = f"ws{base_url[4:]}"
        else:
            raise ValueError(f"Invalid scheme in base URL: {base_url}")

        base_url = base_url.rstrip("/")
        endpoint = endpoint.lstrip("/")
        return f"{base_url}/{endpoint}"

    def _create_websocket(
        self,
        endpoint: str,
        *,
        timeout: float | None = None,
        headers: dict[str, Any] | None = None,
        sslopt: dict[str, Any] | None = None,
        **kwargs,
    ) -> WebSocket:
        """Create a websocket connection to AYON server."""
        con = self._connection
        if hasattr(con, "get_websocket_url"):
            ws_url = con.get_websocket_url(endpoint)
        else:
            ws_url = self._get_ws_url(endpoint)
        ws_headers = con.get_headers()
        ws_headers.pop("Content-Type", None)
        if headers:
            ws_headers.update(headers)

        ws_kwargs = copy.deepcopy(kwargs)
        if timeout is None:
            timeout = con.timeout
        if timeout:
            ws_kwargs["timeout"] = timeout

        if ws_headers:
            ws_kwargs["header"] = [
                f"{key}: {value}"
                for key, value in ws_headers.items()
                if value is not None
            ]

        prepared_sslopt = copy.deepcopy(sslopt) if sslopt else {}
        ssl_verify = con.get_ssl_verify()
        cert = con.get_cert()
        if ssl_verify is False:
            prepared_sslopt.setdefault("cert_reqs", ssl.CERT_NONE)
        elif isinstance(ssl_verify, str):
            prepared_sslopt.setdefault("ca_certs", ssl_verify)

        if cert:
            prepared_sslopt.setdefault("certfile", cert)

        if ws_url.startswith("wss://") and prepared_sslopt:
            ws_kwargs["sslopt"] = prepared_sslopt

        return create_connection(ws_url, **ws_kwargs)

    def _create_ws_connection(self) -> WebSocket:
        if hasattr(self._connection, "create_websocket"):
            ws_con = self._connection.create_websocket("ws")
        else:
            ws_con = self._create_websocket("ws", timeout=_CONNECT_TIMEOUT)
        # Server sends heartbeat periodically, so timeout on receive means
        #   that the connection is dead.
        ws_con.settimeout(_RECV_TIMEOUT)
        return ws_con

    def _close_ws_connection(self) -> None:
        with self._thread_lock:
            ws_con, self._ws_connection = self._ws_connection, None
        if ws_con is not None:
            _abort_ws(ws_con)

    def _check_token(self) -> bool | None:
        """Check if token is valid without affecting the server connection.

        Do NOT use 'ServerAPI.validate_token' here. It marks the token
            as invalid on any non-200 response (e.g. 502 while server is
            restarting) which would break all requests of the process.

        Returns:
            bool | None: 'True' if valid, 'False' if server rejected the
                token, 'None' if it is not possible to tell (server is
                not reachable).

        """
        token = self._connection.access_token
        if not token:
            return False

        ssl_verify = self._connection.get_ssl_verify()
        if ssl_verify is None:
            ssl_verify = True
        url = f"{self._connection.get_base_url()}/api/users/me"
        status_codes = set()
        for headers in (
            {"Authorization": f"Bearer {token}"},
            {"X-Api-Key": token},
        ):
            try:
                response = requests.get(
                    url,
                    headers=headers,
                    verify=ssl_verify,
                    cert=self._connection.get_cert(),
                    timeout=_CONNECT_TIMEOUT,
                )
            except Exception:
                return None
            if response.status_code == 200:
                return True
            status_codes.add(response.status_code)

        if status_codes <= {401, 403}:
            return False
        return None

    def _set_connected(self, connected: bool) -> None:
        state = self._loop_state
        if state.connected is connected:
            return
        state.connected = connected
        if connected:
            state.failed_attempts = 0
            state.server_is_restarting = False
            state.auth_failed = False
            self.emit_event(Event("connection.opened"))
        else:
            self.emit_event(Event("connection.closed"))

    def _on_connection_lost(self, stop_event: threading.Event) -> None:
        state = self._loop_state
        received_message = state.received_message
        state.received_message = False
        self._close_ws_connection()
        if stop_event.is_set():
            return

        self._set_connected(False)

        # Server closes unauthorized clients after few seconds without
        #   sending anything, authorized clients receive heartbeat.
        if not received_message and not state.auth_failed:
            if self._check_token() is False:
                state.auth_failed = True
                self.emit_event(Event("auth.failed"))

        if state.auth_failed:
            delay = _AUTH_FAILED_DELAY
        else:
            idx = min(state.failed_attempts, len(_RECONNECT_DELAYS) - 1)
            delay = _RECONNECT_DELAYS[idx]
        state.failed_attempts += 1
        stop_event.wait(delay)

    def _thread_loop(self, stop_event: threading.Event) -> None:
        try:
            self._loop(stop_event)
        except Exception:
            self._log.warning("AYON event hub loop crashed", exc_info=True)
        finally:
            self._close_ws_connection()
            self._loop_state.received_message = False

    def _loop(self, stop_event: threading.Event) -> None:
        state = self._loop_state
        while not stop_event.is_set():
            ws_con = self._ws_connection
            if ws_con is None:
                if not self._connection.access_token:
                    stop_event.wait(1.0)
                    continue

                try:
                    ws_con = self._create_ws_connection()
                except Exception:
                    # Server is not available (connection refused, timeout,
                    #   502 from proxy during restart, ssl error...)
                    self._on_connection_lost(stop_event)
                    continue

                with self._thread_lock:
                    if stop_event.is_set():
                        _abort_ws(ws_con)
                        break
                    self._ws_connection = ws_con
                state.received_message = False
                state.auth_required = True

            if state.auth_required:
                state.auth_required = False
                subscribe_payload = {
                    "topic": "auth",
                    "token": self._connection.access_token,
                    "subscribe": list(state.registered_topics),
                }
                try:
                    ws_con.send(json.dumps(subscribe_payload))
                except Exception:
                    self._on_connection_lost(stop_event)
                continue

            try:
                op_code, message = ws_con.recv_data()
            except Exception:
                # Timeout (no heartbeat), closed connection, socket error...
                self._on_connection_lost(stop_event)
                continue

            if op_code == ABNF.OPCODE_CLOSE:
                self._on_connection_lost(stop_event)
                continue

            if not state.received_message:
                state.received_message = True
                self._set_connected(True)

            if op_code != ABNF.OPCODE_TEXT or not message:
                continue

            try:
                event_data = json.loads(message)
            except ValueError:
                self._log.debug(
                    "Failed to parse websocket message", exc_info=True
                )
                continue

            if not isinstance(event_data, dict):
                continue

            event = Event.from_ws_message(event_data)
            if event is not None:
                self.emit_event(event)

    def _on_server_restart(self) -> None:
        self._loop_state.server_is_restarting = True

    def _process_event(self, event: Event) -> None:
        """Process event topic and trigger callbacks.

        Args:
            event (Event): Prepared event with topic and data.

        """
        with self._callbacks_lock:
            callbacks = tuple(sorted(
                self._registered_callbacks, key=lambda x: x.order
            ))

        removed = []
        for callback in callbacks:
            callback.process_event(event)
            if not callback.is_ref_valid:
                removed.append(callback)

        if not removed:
            return

        with self._callbacks_lock:
            for callback in removed:
                try:
                    self._registered_callbacks.remove(callback)
                except ValueError:
                    pass
            self._update_topics()


class _GlobalContext:
    event_hub: EventHub | None = None
    _lock = threading.Lock()

    @classmethod
    def get_event_hub(cls) -> EventHub:
        with cls._lock:
            if cls.event_hub is None:
                cls.event_hub = EventHub()
                atexit.register(cls._cleanup)
            return cls.event_hub

    @classmethod
    def _cleanup(cls):
        if cls.event_hub is None:
            return
        event_hub, cls.event_hub = cls.event_hub, None
        event_hub.stop()


class WSEventsModel:
    """Receive AYON server events in a tool controller.

    Callbacks of 'EventHub' are triggered in websocket thread. This model
        only queues them and the callbacks registered here are triggered
        from 'process_events', which should be called from main thread
        (e.g. using QTimer in UI). That way a callback can safely touch Qt
        widgets and the controller event system.

    When controller is passed, connection state changes are emitted as
        controller events (see 'CONNECTION_TOPICS'). Websocket connection
        is not created until 'process_events' is called for the first time,
        so headless usage of a controller does not connect.

    Args:
        controller (Any | None): Controller with 'emit_event' method.
        max_queue_size (int): Maximum number of queued events. Oldest events
            are dropped if events are not processed.

    """
    # Event hub topic -> controller event topic
    CONNECTION_TOPICS: dict[str, str] = {
        "connection.opened": "ayon.connection.opened",
        "connection.closed": "ayon.connection.closed",
        "auth.failed": "ayon.auth.failed",
        "server.restart_requested": "ayon.server.restart",
    }

    def __init__(
        self, controller: object, max_queue_size: int = 1000
    ) -> None:
        self._controller = controller
        self._connection_callbacks_registered: bool = False
        self._hub_callbacks: list[EventCallback] = []
        self._queue: collections.deque[tuple[EventCallback, Event]] = (
            collections.deque(maxlen=max_queue_size)
        )

    def reset(self) -> None:
        callbacks, self._hub_callbacks = self._hub_callbacks, []
        for callback in callbacks:
            callback.deregister()
        self._queue.clear()
        self._connection_callbacks_registered = False

    def register_ayon_event_callback(
        self, topic: str, callback: Callable
    ) -> None:
        """Register callback triggered from 'process_events'.

        Args:
            topic (str): Event topic, can contain '*'.
            callback (Callable): Callback function. Is stored as weak
                reference.

        """
        main_thread_callback = EventCallback(topic, callback)
        event_hub = _GlobalContext.get_event_hub()
        hub_callback = event_hub.add_callback(
            topic, weakref_partial(self._enqueue, main_thread_callback)
        )
        self._hub_callbacks.append(hub_callback)

    def process_events(self) -> None:
        """Trigger callbacks for queued events in current thread.

        First call also registers connection callbacks, which starts
            websocket connection.

        """
        self._register_connection_callbacks()
        while True:
            try:
                callback, event = self._queue.popleft()
            except IndexError:
                break
            callback.process_event(event)

    def get_connection_state(self) -> bool | None:
        """Current connection state.

        Returns:
            bool | None: 'True' if connected, 'False' if disconnected and
                'None' if state is not known yet.

        """
        return _GlobalContext.get_event_hub().get_connection_state()

    def is_auth_failed(self) -> bool:
        return _GlobalContext.get_event_hub().is_auth_failed()

    def is_server_restarting(self) -> bool:
        return _GlobalContext.get_event_hub().is_server_restarting()

    def _register_connection_callbacks(self) -> None:
        if self._connection_callbacks_registered:
            return
        self._connection_callbacks_registered = True
        for hub_topic, topic in self.CONNECTION_TOPICS.items():
            self.register_ayon_event_callback(
                hub_topic,
                weakref_partial(self._emit_controller_event, topic),
            )

    def _emit_controller_event(self, topic: str) -> None:
        self._controller.emit_event(topic)

    def _enqueue(self, callback: EventCallback, event: Event) -> None:
        # 'deque.append' is thread safe
        self._queue.append((callback, event))
