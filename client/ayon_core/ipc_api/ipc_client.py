"""Qt-side IPC client for communicating with Blender.

This module provides a client for Qt UI processes to communicate with Blender
via the IPC bridge. Features:
- Automatic reconnection with backoff
- Request queuing and idempotency
- Connection state tracking
- Event subscription and callbacks
- Graceful handling of Blender unresponsiveness
"""
from __future__ import annotations

from dataclasses import dataclass
import socket
import time
import logging
import threading
import uuid
from typing import Any, Callable

from ayon_blender.ipc_communication.ipc_protocol import (
    Message,
    MessageType,
    HelloMessage,
    RequestMessage,
    ResponseMessage,
    PongMessage,
    read_message_from_socket,
)

logger = logging.getLogger(__name__)

ClientChannelHandler = Callable[[RequestMessage], None]


class WaitCallback:
    def __init__(self):
        self._event = threading.Event()
        self.response: ResponseMessage | None = None

    def __call__(self, response: ResponseMessage) -> None:
        self.response = response
        self._event.set()

    def is_done(self) -> bool:
        return self._event.is_set()

    def wait(self, timeout: float | None = None) -> bool:
        return self._event.wait(timeout)


class ConnectionState:
    """Tracks connection state and provides status info."""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    BLENDER_BUSY = "blender_busy"


class PendingRequest:
    """Tracks a pending request with timeout and callback."""

    def __init__(
        self,
        request_id: str,
        method: str,
        callback: Callable[[ResponseMessage], Any] | None = None
    ):
        self.request_id = request_id
        self.method = method
        self.submitted_at = time.time()
        self.callback: Callable[[ResponseMessage], Any] | None = callback
        self.done = False

    def mark_done(self):
        """Mark request as completed."""
        self.done = True


@dataclass
class RequestWaitData:
    ok: bool = False
    result: Any = None
    error: str | None = None


class IPCClient:
    """Client for connecting to Blender IPC bridge from Qt processes.

    Handles:
    - Connection and reconnection with exponential backoff
    - Async requests with optional callbacks
    - Event subscriptions
    - Blender busy state detection
    - Graceful disconnection handling
    """

    # Reconnection backoff: 0.5s -> 1s -> 2s -> 5s (cap)
    RECONNECT_DELAYS = [0.5, 1.0, 2.0, 5.0]

    def __init__(
        self,
        host: str = "127.0.0.1",
        port: int = 0,
        session_token: str = "",
        session_id: str | None = None,
    ):
        """Initialize IPC client.

        Args:
            host: Server host (should be 127.0.0.1)
            port: Server port
            session_token: Authentication token from Blender
            session_id: Optional session identifier
        """
        self.host = host
        self.port = port
        self.session_token = session_token
        self.session_id = session_id or str(uuid.uuid4())[:8]

        self.socket: socket.socket | None = None
        self.state = ConnectionState.DISCONNECTED
        self.connected = False

        self.pending_requests: dict[str, PendingRequest] = {}
        self.channel_handlers: dict[str, ClientChannelHandler] = {}

        self.reconnect_attempts = 0
        self.last_heartbeat = time.time()
        self.blender_unresponsive_since: float | None = None

        self._lock = threading.RLock()
        self._receiver_thread: threading.Thread | None = None
        self._running = False

    def connect(self) -> bool:
        """Establish connection to Blender IPC server.

        Returns:
            True if connection successful, False otherwise
        """
        if self.connected:
            return True

        try:
            logger.info(
                f"Connecting to Blender IPC at {self.host}:{self.port} "
                f"(session: {self.session_id})"
            )

            # If previous receiver thread died, allow it to be recreated.
            if self._receiver_thread and not self._receiver_thread.is_alive():
                self._receiver_thread = None
                self._running = False

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(10.0)
            self.socket.connect((self.host, self.port))

            self.state = ConnectionState.CONNECTING

            # Send HELLO message
            hello = HelloMessage(
                session_token=self.session_token,
                session_id=self.session_id
            )
            self._send_message(hello)

            # Receive HELLO_ACK
            msg = self._receive_msg()
            if msg is None:
                raise RuntimeError("No HELLO_ACK received")

            if msg.type != MessageType.HELLO_ACK:
                raise RuntimeError(f"Expected HELLO_ACK, got {msg.type}")

            self.connected = True
            self.state = ConnectionState.CONNECTED
            self.reconnect_attempts = 0
            self.blender_unresponsive_since = None
            self.last_heartbeat = time.time()

            logger.info(f"Connected to Blender (session: {self.session_id})")

            # Start receiver thread if needed (e.g. after reconnect).
            if self._receiver_thread is None or not self._receiver_thread.is_alive():
                self._running = True
                self._receiver_thread = threading.Thread(
                    target=self._receiver_loop, daemon=True
                )
                self._receiver_thread.start()

            return True

        except Exception as e:
            logger.error(f"Failed to connect: {e}")
            self.connected = False
            self.state = ConnectionState.DISCONNECTED
            if self.socket:
                try:
                    self.socket.close()
                except Exception:
                    pass
                self.socket = None
            return False

    def disconnect(self):
        """Disconnect from Blender."""
        self._running = False
        self.connected = False
        self.state = ConnectionState.DISCONNECTED

        if self.socket:
            try:
                self.socket.close()
            except Exception:
                pass
            self.socket = None

        if self._receiver_thread and self._receiver_thread is not threading.current_thread():
            self._receiver_thread.join(timeout=5)
        self._receiver_thread = None

    def reconnect_with_backoff(self):
        """Attempt reconnection with exponential backoff."""
        if self.connected:
            return

        delay_index = min(self.reconnect_attempts, len(self.RECONNECT_DELAYS) - 1)
        delay = self.RECONNECT_DELAYS[delay_index]

        logger.info(
            f"Reconnecting (attempt {self.reconnect_attempts + 1}, "
            f"delay {delay}s)..."
        )

        time.sleep(delay)
        success = self.connect()
        if success:
            self.reconnect_attempts = 0
        else:
            self.reconnect_attempts += 1

    def register_channel_handler(
        self, channel: str, handler: ClientChannelHandler
    ):
        """Register a request handler.

        Args:
            channel: Channel name.
            handler: Callable that accepts (request: RequestMessage) -> Any
        """
        if channel in self.channel_handlers:
            raise ValueError(
                f"Handler already registered for channel: {channel}"
            )
        self.channel_handlers[channel] = handler
        logger.debug(f"Registered handler for channel: {channel}")

    def send_request(
        self,
        channel: str,
        method: str,
        params: dict[str, Any] | None = None,
        callback: Callable[[ResponseMessage], None] | None = None,
    ) -> str:
        """Send an async request to Blender.

        Args:
            channel: Channel to which the method belongs.
            method: Method name to call in Blender.
            params: Parameters for the method.
            callback: Optional callback(ok, result, error_msg).

        Returns:
            Request ID
        """
        if not self.connected:
            error_msg = "Not connected to Blender"
            if callback:
                callback(
                    ResponseMessage(
                        ok=False,
                        result=None,
                        error=error_msg,
                        request_id=uuid.uuid4().hex,
                    )
                )
            raise RuntimeError(error_msg)

        if params is None:
            params = {}

        req = RequestMessage(
            channel=channel,
            method=method,
            params=params,
        )
        request_id = req.id

        with self._lock:
            self.pending_requests[request_id] = PendingRequest(
                request_id=request_id,
                method=method,
                callback=callback,
            )

        try:
            self._send_message(req)
            logger.debug(f"Sent request {request_id}: {method}")
            return request_id
        except Exception as e:
            logger.error(f"Failed to send request", exc_info=True)
            with self._lock:
                self.pending_requests.pop(request_id, None)
            if callback is not None:
                callback(
                    ResponseMessage(
                        request_id=req.id,
                        ok=False,
                        result=None,
                        error=str(e),
                    )
                )
            raise

    def get_state(self) -> str:
        """Get current connection state."""
        return self.state

    def is_connected(self) -> bool:
        """Check if connected."""
        return self.connected

    def is_blender_busy(self) -> bool:
        """Check if Blender is detected as busy (unresponsive)."""
        return self.state == ConnectionState.BLENDER_BUSY

    def _send_message(self, msg: Message):
        """Send message to server."""
        if not self.socket:
            raise RuntimeError("Not connected")

        self.socket.sendall(msg.to_bytes())
        self.last_heartbeat = time.time()

    def _receive_msg(self) -> Message | None:
        if self.socket is None:
            return None

        return read_message_from_socket(self.socket)

    def _receiver_loop(self):
        """Receive and process messages (runs in background thread)."""
        try:
            while self._running and self.connected:
                try:
                    if self.socket is None:
                        break

                    self.socket.settimeout(5.0)
                    msg = self._receive_msg()

                    if msg is None:
                        logger.info("Parent process disconnected")
                        self.connected = False
                        self.state = ConnectionState.DISCONNECTED
                        break

                    self._handle_message(msg)

                except socket.timeout:
                    # Check for pending request timeouts

                    # Check heartbeat (detect Blender busy)
                    if time.time() - self.last_heartbeat > 60:
                        if self.state != ConnectionState.BLENDER_BUSY:
                            logger.warning("Blender unresponsive for 60s, marking busy")
                            self.state = ConnectionState.BLENDER_BUSY
                            self.blender_unresponsive_since = time.time()
                    continue

                except Exception as e:
                    if self._running:
                        logger.error(f"Receiver loop error: {e}", exc_info=True)
                    self.connected = False
                    self.state = ConnectionState.DISCONNECTED
                    break
        finally:
            # Ensure reconnect can spawn a fresh receiver thread.
            self._running = False
            self._receiver_thread = None

    def _handle_message(self, msg: Message):
        """Handle incoming message."""
        try:
            if msg.type == MessageType.REQUEST:
                self._handle_request(msg)
            elif msg.type == MessageType.RESPONSE:
                self._handle_response(msg)
            elif msg.type == MessageType.PING:
                self._send_message(PongMessage())
            elif msg.type == MessageType.PONG:
                # Mark as responsive
                if self.state == ConnectionState.BLENDER_BUSY:
                    logger.info("Blender responsive again")
                    self.state = ConnectionState.CONNECTED
                    self.blender_unresponsive_since = None
                self.last_heartbeat = time.time()
            elif msg.type == MessageType.ERROR:
                self._handle_error(msg)
            else:
                logger.warning(f"Unexpected message type: {msg.type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_request(self, req: RequestMessage):
        """Handle incoming request message."""
        channel = req.channel
        handler = self.channel_handlers.get(channel)

        if not handler:
            logger.warning(f"No handler registered for channel: {channel}")
            return

        try:
            handler(req)
        except Exception as e:
            logger.error(f"Error in request handler for channel {channel}: {e}")

    def _handle_response(self, resp: ResponseMessage):
        """Handle response message."""
        request_id = resp.request_id

        logger.debug(f"Response for request {request_id}: ok={resp.ok}")

        with self._lock:
            callback = None
            pr = self.pending_requests.pop(request_id, None)
            if pr is not None:
                callback = pr.callback

        if callback is not None:
            try:
                callback(resp)
            except Exception as e:
                logger.error(f"Error in response callback: {e}")






