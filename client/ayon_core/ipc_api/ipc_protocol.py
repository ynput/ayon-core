"""IPC protocol definitions for DCC<->Qt UI communication.

This module defines the message protocol used for inter-process communication
between DCC (server) and external Qt UI processes (clients).

Protocol is JSON-based with message types:
- hello: Session negotiation
- hello_ack: Acknowledgement of session
- request: Async request from client to DCC
- response: Response to request
- event: Event published by DCC
- ping/pong: Keep-alive
"""
from __future__ import annotations

import json
import uuid
import socket
import struct
from typing import Any
from enum import Enum

from .json_encoding import DataEncoder, DataDecoder

MAX_PAGE_SIZE, = struct.unpack(">Q", b'\xff\xff\xff\xff\xff\xff\xff\xff')


def _recv_exact(sock: socket.socket, size: int) -> bytes | None:
    """Read exactly specific length of bytes from socket."""
    if size == 0:
        return b""

    data = bytearray()
    while len(data) < size:
        chunk = sock.recv(size - len(data))
        if not chunk:
            return None
        data.extend(chunk)
    return bytes(data)


class MessageType(int, Enum):
    """Message types in the IPC protocol."""
    HELLO = 1
    HELLO_ACK = 2
    PING = 3
    PONG = 4
    ERROR = 5
    REQUEST = 6
    RESPONSE = 7

    @classmethod
    def from_socket(cls, sock: socket.socket) -> MessageType | None:
        """Read the message type from a socket."""
        msg_type_b = _recv_exact(sock, 2)
        if msg_type_b is None:
            return None
        msg_type_value = struct.unpack(">H", msg_type_b)[0]
        return cls(msg_type_value)


class Message:
    """Base class for IPC messages."""

    def __init__(self, msg_type: MessageType):
        self.type = msg_type

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        return struct.pack(">H", self.type.value)


class HelloMessage(Message):
    """Session negotiation message."""

    def __init__(
        self,
        session_token: str,
        version: str = "1.0",
        session_id: str = "",
    ):
        super().__init__(MessageType.HELLO)
        self.session_token = session_token
        self.version = version
        self.session_id = session_id

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        st_bytes = self.session_token.encode(encoding="utf-8")
        version_bytes = self.version.encode(encoding="utf-8")
        session_id_bytes = self.session_id.encode(encoding="utf-8")
        content = super().to_bytes()
        content += struct.pack(
            ">III",
            len(st_bytes),
            len(version_bytes),
            len(session_id_bytes)
        )
        content += st_bytes + version_bytes + session_id_bytes
        return content

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""

        lengths_b = _recv_exact(sock, 12)
        if lengths_b is None:
            return None
        st_len, version_len, session_id_len = struct.unpack(">III", lengths_b)

        session_token_b = _recv_exact(sock, st_len)
        if session_token_b is None:
            return None
        version_b = _recv_exact(sock, version_len)
        if version_b is None:
            return None
        session_id_b = _recv_exact(sock, session_id_len)
        if session_id_b is None:
            return None

        return cls(
            session_token_b.decode(encoding="utf-8"),
            version_b.decode(encoding="utf-8"),
            session_id_b.decode(encoding="utf-8"),
        )


class HelloAckMessage(Message):
    """Acknowledgement of session."""

    def __init__(self, session_id: str):
        super().__init__(MessageType.HELLO_ACK)
        self.session_id = session_id

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        session_id_b = self.session_id.encode(encoding="utf-8")
        content = super().to_bytes()
        content += struct.pack(">I", len(session_id_b)) + session_id_b
        return content

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""

        sid_len_b = _recv_exact(sock, 4)
        if sid_len_b is None:
            return None
        sid_len = struct.unpack(">I", sid_len_b)[0]

        session_id_b = _recv_exact(sock, sid_len)
        if session_id_b is None:
            return None

        return cls(session_id_b.decode(encoding="utf-8"))


class JsonMessage(Message):
    def to_data(self) -> dict[str, Any]:
        raise NotImplementedError("Subclasses must implement to_data method.")

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        content = super().to_bytes()
        data = self.to_data()
        value = json.dumps(data, cls=DataEncoder).encode(encoding="utf-8")
        pages = []
        while len(value) > MAX_PAGE_SIZE:
            pages.append(value[:MAX_PAGE_SIZE])
            value = value[MAX_PAGE_SIZE:]

        if value:
            pages.append(value)

        content += struct.pack(">Q", len(pages))
        for page in pages:
            content += struct.pack(">Q", len(page)) + page

        return content

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""
        pages_len_b = _recv_exact(sock, 8)
        if pages_len_b is None:
            return None
        pages_len, = struct.unpack(">Q", pages_len_b)
        value = b""
        for _ in range(pages_len):
            page_len_b = _recv_exact(sock, 8)
            if page_len_b is None:
                return None
            page_len, = struct.unpack(">Q", page_len_b)

            page_b = _recv_exact(sock, page_len)
            if page_b is None:
                return None
            value += page_b

        json_str = value.decode(encoding="utf-8")
        data = json.loads(json_str, cls=DataDecoder)
        return cls(**data)


class RequestMessage(JsonMessage):
    """Request message from client to DCC."""

    def __init__(
        self,
        channel: str,
        method: str,
        params: dict[str, Any] | None = None,
        request_id: str | None = None,
    ) -> None:
        if request_id is None:
            request_id = uuid.uuid4().hex
        if params is None:
            params = {}

        self.id: str = request_id
        self.channel: str = channel
        self.method: str = method
        self.params: dict[str, Any] = params

        super().__init__(MessageType.REQUEST)

    def __str__(self) -> str:
        return (
            f"RequestMessage(id={self.id}, channel={self.channel},"
            f" method={self.method}, params={self.params})"
        )

    def to_data(self) -> dict[str, Any]:
        """Serialize the message to JSON bytes."""
        return {
            "request_id": self.id,
            "channel": self.channel,
            "method": self.method,
            "params": self.params,
        }


class ResponseMessage(JsonMessage):
    """Response message from DCC to client."""

    def __init__(
        self,
        request_id: str,
        ok: bool = True,
        result: Any = None,
        error: str | None = None,
    ):
        self.request_id = request_id
        self.ok = ok
        self.result = result
        self.error = error

        super().__init__(MessageType.RESPONSE)

    def __str__(self) -> str:
        return (
            f"ResponseMessage(request_id={self.request_id}, ok={self.ok},"
            f" result={self.result}, error={self.error})"
        )

    def to_data(self) -> dict[str, Any]:
        """Serialize the message to JSON bytes."""
        return {
            "request_id": self.request_id,
            "ok": self.ok,
            "result": self.result,
            "error": self.error,
        }


class PingMessage(Message):
    """Keep-alive ping message."""

    def __init__(self):
        super().__init__(MessageType.PING)


class PongMessage(Message):
    """Keep-alive pong message."""

    def __init__(self):
        super().__init__(MessageType.PONG)


class ErrorMessage(Message):
    """Error message."""

    def __init__(self, error: str):
        super().__init__(MessageType.ERROR)
        self.error = error

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        error_bytes = self.error.encode(encoding="utf-8")
        content = super().to_bytes()
        content += struct.pack(">I", len(error_bytes)) + error_bytes
        return content

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""
        error_len_b = _recv_exact(sock, 4)
        if error_len_b is None:
            return None
        error_len = struct.unpack(">I", error_len_b)[0]

        error_b = _recv_exact(sock, error_len)
        if error_b is None:
            return None
        return cls(error_b.decode(encoding="utf-8"))


def read_message_from_socket(sock: socket.socket) -> Message | None:
    """Read one full message from stream in a thread-safe way."""
    msg_type = MessageType.from_socket(sock)
    if msg_type is None:
        return None

    if msg_type == MessageType.PING:
        return PingMessage()

    if msg_type == MessageType.PONG:
        return PongMessage()

    if msg_type == MessageType.HELLO:
        return HelloMessage.from_socket(sock)

    if msg_type == MessageType.HELLO_ACK:
        return HelloAckMessage.from_socket(sock)

    if msg_type == MessageType.REQUEST:
        return RequestMessage.from_socket(sock)

    if msg_type == MessageType.RESPONSE:
        return ResponseMessage.from_socket(sock)

    if msg_type == MessageType.ERROR:
        return ErrorMessage.from_socket(sock)

    raise ValueError(f"Unknown message type: {msg_type}")
