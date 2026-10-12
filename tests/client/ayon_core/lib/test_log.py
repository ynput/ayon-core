"""Unit tests for the AYON log stream handler."""

from __future__ import annotations

import logging

import pytest
from ayon_core.lib.log import LogStreamHandler


class _BrokenStream:
    """Stream which fails on every write, like some host streams do."""

    def write(self, _text: str) -> None:
        raise SystemError("<built-in function write> returned a result")

    def flush(self) -> None:
        pass


def _make_logger(name: str, stream: _BrokenStream) -> logging.Logger:
    logger = logging.getLogger(name)
    logger.propagate = False
    logger.setLevel(logging.DEBUG)
    logger.handlers = [LogStreamHandler(stream)]
    return logger


def test_emit_does_not_raise_on_broken_stream(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failing stream must not break the code that is logging."""
    stream = _BrokenStream()
    # The host replaces the standard streams too, so neither printing
    # nor the 'handleError' report to 'sys.stderr' can succeed.
    monkeypatch.setattr("sys.stdout", stream)
    monkeypatch.setattr("sys.stderr", stream)

    logger = _make_logger("test_log.broken_stream", stream)

    logger.debug("message %s", "value")
    try:
        raise ValueError("boom")
    except ValueError:
        logger.exception("failed")


def test_emit_propagates_keyboard_interrupt() -> None:
    """Interrupts raised while writing are not swallowed."""

    class _InterruptedStream(_BrokenStream):
        def write(self, _text: str) -> None:
            raise KeyboardInterrupt

    logger = _make_logger("test_log.interrupted", _InterruptedStream())

    with pytest.raises(KeyboardInterrupt):
        logger.debug("message")
