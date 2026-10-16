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


def to_json_bytes(data: dict[str, Any]) -> bytes:
    """Serialize the message to JSON bytes."""
    return json.dumps(data, cls=DataEncoder).encode(encoding="utf-8")


def from_json_bytes(content: bytes) -> dict[str, Any]:
    json_str = content.decode(encoding="utf-8")
    return json.loads(json_str, cls=DataDecoder)


def content_to_pages(content: bytes) -> bytes:
    pages = []
    while len(content) > MAX_PAGE_SIZE:
        pages.append(content[:MAX_PAGE_SIZE])
        content = content[MAX_PAGE_SIZE:]

    if content:
        pages.append(content)

    output = bytearray()

    output.extend(struct.pack(">Q", len(pages)))
    for page in pages:
        output.extend(struct.pack(">Q", len(page)))
        output.extend(page)
    return bytes(output)


def strings_to_bytes(*args: str) -> bytes:
    if not args:
        return b""

    output = bytearray()
    output.extend(struct.pack(">H", len(args)))
    for arg in args:
        output.extend(struct.pack(">H", len(arg)))
        output.extend(arg.encode(encoding="utf-8"))

    return bytes(output)


def strings_from_sock(sock: socket.socket) -> tuple[str] | None:
    lengths_b = _recv_exact(sock, 2)
    if lengths_b is None:
        return None
    num_strings = struct.unpack(">H", lengths_b)[0]

    strings = []
    for _ in range(num_strings):
        length_b = _recv_exact(sock, 2)
        if length_b is None:
            return None
        length = struct.unpack(">H", length_b)[0]

        string_b = _recv_exact(sock, length)
        if string_b is None:
            return None
        strings.append(string_b.decode(encoding="utf-8"))

    return tuple(strings)


def bytes_from_sock(sock: socket.socket) -> list[bytes] | None:
    lengths_b = _recv_exact(sock, 2)
    if lengths_b is None:
        return None
    num_strings = struct.unpack(">H", lengths_b)[0]

    output = []
    for _ in range(num_strings):
        length_b = _recv_exact(sock, 2)
        if length_b is None:
            return None
        length = struct.unpack(">H", length_b)[0]

        string_b = _recv_exact(sock, length)
        if string_b is None:
            return None
        output.append(string_b)

    return output


class MessageType(int, Enum):
    """Message types in the IPC protocol."""
    HELLO = 1
    HELLO_ACK = 2
    PING = 3
    PONG = 4
    REQUEST = 5
    RESPONSE = 6
    ERROR = 7

    @classmethod
    def from_socket(cls, sock: socket.socket) -> MessageType | None:
        """Read the message type from a socket."""
        msg_type_b = _recv_exact(sock, 2)
        if msg_type_b is None:
            return None
        msg_type_value = struct.unpack(">H", msg_type_b)[0]
        return cls(msg_type_value)


class ContentType(int, Enum):
    """Message types in the IPC protocol."""
    RAW = 1
    JSON = 2

    @classmethod
    def from_socket(cls, sock: socket.socket) -> ContentType | None:
        """Read the content type from a socket."""
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
        output = bytearray()
        output.extend(super().to_bytes())
        output.extend(strings_to_bytes(
            self.session_token,
            self.version,
            self.session_id,
        ))
        return bytes(output)

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""
        output = strings_from_sock(sock)
        if output is None:
            return None

        return cls(*output)


class HelloAckMessage(Message):
    """Acknowledgement of session."""

    def __init__(self, session_id: str):
        super().__init__(MessageType.HELLO_ACK)
        self.session_id = session_id

    def to_bytes(self) -> bytes:
        output = bytearray()
        output.extend(super().to_bytes())
        output.extend(strings_to_bytes(self.session_id))
        return bytes(output)

    @classmethod
    def from_socket(cls, sock: socket.socket) -> HelloAckMessage | None:
        output = strings_from_sock(sock)
        if output is None:
            return None

        return cls(*output)


def read_pages_from_socket(sock: socket.socket) -> bytes | None:
    """Read content from socket in pages."""
    pages_len_b = _recv_exact(sock, 8)
    if pages_len_b is None:
        return None
    pages_len, = struct.unpack(">Q", pages_len_b)
    value = bytearray()
    for _ in range(pages_len):
        page_len_b = _recv_exact(sock, 8)
        if page_len_b is None:
            return None
        page_len, = struct.unpack(">Q", page_len_b)

        page_b = _recv_exact(sock, page_len)
        if page_b is None:
            return None
        value.extend(page_b)
    return bytes(value)


class RequestMessage(Message):
    """Request message from client to DCC."""

    def __init__(
        self,
        channel: str,
        method: str,
        params: dict[str, Any] | bytes | None = None,
        request_id: str | None = None,
    ) -> None:
        if request_id is None:
            request_id = uuid.uuid4().hex
        if params is None:
            params = {}

        self.id: str = request_id
        self.channel: str = channel
        self.method: str = method
        self.params: dict[str, Any] | bytes = params

        super().__init__(MessageType.REQUEST)

    def __str__(self) -> str:
        return (
            f"RequestMessage(id={self.id}, channel={self.channel},"
            f" method={self.method})"
        )

    def get_content_type(self) -> ContentType:
        """Return the content type of the message."""
        return (
            ContentType.RAW
            if isinstance(self.params, bytes)
            else ContentType.JSON
        )

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        output = bytearray()
        output.extend(super().to_bytes())
        content_type = self.get_content_type()
        output.extend(struct.pack(">H", content_type.value))
        output.extend(strings_to_bytes(
            self.id, self.channel, self.method
        ))

        if content_type == ContentType.RAW:
            content = self.params
        else:
            content = to_json_bytes(self.params)
        output.extend(content_to_pages(content))
        return bytes(output)

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the request message from bytes."""
        content_type_b = _recv_exact(sock, 2)
        if content_type_b is None:
            return None
        content_type_value = struct.unpack(">H", content_type_b)[0]
        content_type = ContentType(content_type_value)

        output = strings_from_sock(sock)
        if output is None:
            return None

        request_id, channel, method = output
        params = read_pages_from_socket(sock)
        if content_type == ContentType.JSON:
            params = from_json_bytes(params)

        return cls(channel, method, params=params, request_id=request_id)


class ResponseMessage(Message):
    """Response message from DCC to client."""

    def __init__(
        self,
        request_id: str,
        ok: bool = True,
        result: Any = None,
        error: str | None = None,
    ) -> None:
        if error is None:
            error = ""
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

    def get_content_type(self) -> ContentType:
        """Return the content type of the message."""
        return (
            ContentType.RAW
            if isinstance(self.result, bytes)
            else ContentType.JSON
        )

    def to_bytes(self) -> bytes:
        """Serialize the message to JSON bytes."""
        output = bytearray()
        output.extend(super().to_bytes())
        content_type = self.get_content_type()
        output.extend(struct.pack(">H", content_type.value))
        output.extend(struct.pack("?", self.ok))
        output.extend(strings_to_bytes(
            self.request_id, self.error
        ))

        if content_type == ContentType.RAW:
            content = self.result
        else:
            content = to_json_bytes(self.result)
        output.extend(content_to_pages(content))
        return bytes(output)

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the request message from bytes."""
        content_type_b = _recv_exact(sock, 2)
        if content_type_b is None:
            return None
        content_type_value = struct.unpack(">H", content_type_b)[0]
        content_type = ContentType(content_type_value)
        ok_b = _recv_exact(sock, 1)
        ok, = struct.unpack("?", ok_b)

        output = strings_from_sock(sock)
        if output is None:
            return None

        request_id, error = output
        params = read_pages_from_socket(sock)
        if content_type == ContentType.JSON:
            params = from_json_bytes(params)

        return cls(request_id, ok=ok, error=error, result=params)


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
        content = super().to_bytes()
        content += strings_to_bytes(self.error)
        return content

    @classmethod
    def from_socket(cls, sock: socket.socket):
        """Deserialize the message from JSON bytes."""
        output = strings_from_sock(sock)
        if output is None:
            return None
        return cls(*output)


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
