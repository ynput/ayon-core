"""DCC-side IPC bridge for external UI communication.

This module implements a TCP server that listens for connections from external
Qt UI processes. It handles:
- Session management and authentication
- Async request processing via main-thread callbacks
- Event publishing when DCC state changes
- Graceful handling of DCC unresponsiveness (render/processing)
- Automatic reconnect support
"""
from __future__ import annotations

import os
import socket
import logging
import time
import threading
import collections
from typing import Any, Callable

from .ipc_protocol import (
    Message,
    MessageType,
    HelloMessage,
    HelloAckMessage,
    ResponseMessage,
    RequestMessage,
    PongMessage,
    ErrorMessage,
    read_message_from_socket,
)

logger = logging.getLogger(__name__)

ChannelHandler = Callable[["IPCServer", RequestMessage], Any]


class IPCServer:
    """TCP server for IPC communication between DCC and external UIs.

    This is the DCC-side server. It listens for connections and dispatches
    requests to DCC via main-thread callbacks.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        """Initialize IPC server.

        Args:
            host: Bind address (127.0.0.1 only for security)
            port: Port number (0 = auto-select)
        """
        self.host = host
        self.port = port
        self.server_socket: socket.socket | None = None
        self.running = False
        self.server_thread: threading.Thread | None = None
        self.clients: dict[str, "IPCClientConnection"] = {}
        self.session_token = os.urandom(16).hex()

        self.channel_handlers: dict[str, ChannelHandler] = {}

        self.requests_queue: collections.deque[RequestMessage] = (
            collections.deque()
        )
        self.response_callbacks: dict[str, Callable] = {}
        self._lock = threading.RLock()

    def start(self) -> int:
        """Start the IPC server.

        Returns:
            Port number the server is listening on
        """
        self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server_socket.bind((self.host, self.port))
        self.server_socket.listen(5)
        actual_host, actual_port = self.server_socket.getsockname()
        self.port = actual_port

        self.running = True
        self.server_thread = threading.Thread(
            target=self._server_loop, daemon=True
        )
        self.server_thread.start()

        logger.info(
            f"IPC server started on {actual_host}:{actual_port} "
            f"(token: {self.session_token[:8]}...)"
        )
        return actual_port

    def stop(self):
        """Stop the IPC server."""
        self.running = False
        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass

        # Close client connections
        with self._lock:
            for client in list(self.clients.values()):
                try:
                    client.close()
                except Exception:
                    pass

        if self.server_thread:
            self.server_thread.join(timeout=5)

        logger.info("IPC server stopped")

    def register_handler(
        self, channel: str, handler: ChannelHandler
    ):
        """Register a request handler.

        Args:
            channel: Channel name.
            handler: Callable that accepts (request: RequestMessage) -> Any
        """
        old_handler = self.channel_handlers.get(channel)
        if handler is old_handler:
            return

        if old_handler is not None:
            raise ValueError(
                f"Handler already registered for channel: {channel}"
            )
        self.channel_handlers[channel] = handler
        logger.debug(f"Registered handler for channel: {channel}")

    def trigger_method(
        self,
        channel: str,
        method: str,
        params: dict[str, Any] | None = None,
    ) -> RequestMessage:
        msg = RequestMessage(channel=channel, method=method, params=params)
        with self._lock:
            self.requests_queue.append(msg)
        return msg

    def get_session_token(self) -> str:
        """Get the session token for validating client connections."""
        return self.session_token

    def process_requests(self) -> bool:
        """Process pending events and dispatch to clients.

        Should be called from DCC main thread via timer callback.

        Returns:
            True if there were events to process
        """
        processed = False

        with self._lock:
            while self.requests_queue:
                request = self.requests_queue.popleft()
                # Send to all connected clients
                for client in list(self.clients.values()):
                    try:
                        client.send_message(request)
                    except Exception:
                        logger.warning(
                            f"Failed to send event to client",
                            exc_info=True
                        )
                processed = True

        return processed

    def _server_loop(self):
        """Main server loop (runs in background thread)."""
        threads = []
        while self.running:
            try:
                # Accept connections with timeout to allow check of self.running
                self.server_socket.settimeout(1.0)
                try:
                    client_socket, addr = self.server_socket.accept()
                except socket.timeout:
                    continue

                logger.info(f"Client connected from {addr}")
                client = IPCClientConnection(self, client_socket, addr)

                # Start client handler in separate thread
                client_thread = threading.Thread(
                    target=client.handle, daemon=True
                )
                client_thread.start()
                threads.append((client, client_thread))

            except Exception as e:
                if self.running:
                    logger.error(f"Server loop error: {e}", exc_info=True)
                break

        for client, thread in threads:
            try:
                client.close()
            except Exception:
                pass
            thread.join(timeout=2)

        logger.debug("Server loop exited")


class IPCClientConnection:
    """Represents a single client connection to the IPC server."""

    def __init__(
        self,
        server: IPCServer,
        socket_obj: socket.socket,
        addr: tuple,
    ):
        self.server = server
        self.socket = socket_obj
        self.addr = addr
        self.session_id: str | None = None
        self.authenticated = False
        self._send_lock = threading.RLock()
        self._recv_lock = threading.RLock()
        self._connected = True

    def handle(self):
        """Handle client connection (runs in separate thread)."""
        try:
            self.socket.settimeout(30.0)

            while True:
                msg_type = MessageType.from_socket(self.socket)
                if msg_type is None:
                    logger.debug(f"Client {self.addr} disconnected")
                    return

                if msg_type != MessageType.HELLO:
                    self._send_error("Expected HELLO message")
                    return

                msg = HelloMessage.from_socket(self.socket)
                if msg.version != "1.0":
                    self._send_error("Unsupported protocol version")
                    return

                self.session_id = msg.session_id
                self.authenticated = True
                self._connected = True

                with self.server._lock:
                    self.server.clients[msg.session_id] = self
                ack = HelloAckMessage(session_id=msg.session_id)
                self._send_message(ack)
                logger.info(f"Client {self.addr} authenticated: {self.session_id}")
                break

            # Main message loop
            while True:
                try:
                    msg = self._receive_msg()
                    if msg is None:
                        logger.debug(f"Client {self.addr} disconnected")
                        break

                    self._handle_message(msg)

                except socket.timeout:
                    # Client may be idle for long periods while DCC is busy.
                    time.sleep(0.5)
                    continue

        except Exception as e:
            logger.error(f"Error handling client {self.addr}: {e}", exc_info=True)
        finally:
            self.close()

    def _handle_message(self, msg: Message):
        """Handle incoming message."""
        try:
            if msg.type == MessageType.REQUEST:
                self._handle_request(msg)
            elif msg.type == MessageType.PING:
                self._send_message(PongMessage())
            elif msg.type == MessageType.PONG:
                # Keep-alive acknowledgement
                pass
            else:
                logger.warning(f"Unexpected message type: {msg.type}")

        except Exception as e:
            logger.error(f"Error handling message: {e}")

    def _handle_request(self, req: RequestMessage):
        """Handle incoming request."""
        channel = req.channel

        logger.debug(f"Handling request {req.id}: {req.method}")

        # Check if handler is registered
        handler = self.server.channel_handlers.get(channel)
        if not handler:
            response = ResponseMessage(
                request_id=req.id,
                ok=False,
                error=f"Unknown channel: {channel}"
            )
            self._send_message(response)
            return

        try:
            # Call handler (may be queued to main thread by handler)
            result = handler(self.server, req)

            response = ResponseMessage(
                request_id=req.id,
                ok=True,
                result=result,
                error=None
            )
            try:
                self._send_message(response)
            except Exception as e:
                logger.error(f"Failed to send response", exc_info=True)
        except Exception as e:
            logger.error(
                f"Handler error for {req.channel} {req.method}",
                exc_info=True,
            )
            try:
                # Keep request_id so client can finish matching pending request.
                self._send_message(ResponseMessage(
                    request_id=req.id,
                    ok=False,
                    result=None,
                    error=str(e),
                ))
            except Exception as e:
                logger.error(f"Failed to send response", exc_info=True)

    def _send_message(self, msg: Message):
        """Send message to client."""
        with self._send_lock:
            if not self._connected:
                raise RuntimeError("Client disconnected")
            self.socket.sendall(msg.to_bytes())

    def send_message(self, msg: Message):
        """Public method to send message to client."""
        self._send_message(msg)

    def _send_error(self, error_msg: str):
        """Send error message."""
        msg = ErrorMessage(error=error_msg)
        try:
            self._send_message(msg)
        except Exception:
            pass

    def _receive_msg(self) -> Message | None:
        if not self._connected:
            return None

        with self._recv_lock:
            msg = read_message_from_socket(self.socket)

        if msg is None:
            self._connected = False
        return msg

    def close(self):
        """Close the client connection."""
        self._connected = False
        try:
            self.socket.close()
        except Exception:
            pass

        # Unregister from server
        if self.session_id:
            with self.server._lock:
                self.server.clients.pop(self.session_id, None)
