"""Validation helpers for Workfiles Subversion (anatomy ``{comment}`` token)."""

from __future__ import annotations

import re
from typing import Optional

WORKFILE_SUBVERSION_ALLOWED_SYMBOLS = "a-zA-Z0-9_.-"

WORKFILE_SUBVERSION_PATTERN = re.compile(
    rf"^[{WORKFILE_SUBVERSION_ALLOWED_SYMBOLS}]*$"
)

# GraphQL ``project/products`` filter (AYON server).
AYON_PRODUCT_NAME_PATTERN = re.compile(
    r"^[a-zA-Z0-9_]([a-zA-Z0-9_\.\-]*[a-zA-Z0-9_])?$"
)

_INVALID_CHAR_PATTERN = re.compile(
    rf"[^{WORKFILE_SUBVERSION_ALLOWED_SYMBOLS}]"
)

_COLLAPSE_UNDERSCORES = re.compile(r"_+")

INVALID_FIELD_QSS = (
    "QLineEdit {"
    " border: 1px solid #c0392b;"
    " border-radius: 2px;"
    " padding: 2px;"
    "}"
)

_SUBVERSION_HINT = (
    "Subversion may only contain letters, numbers, and the characters "
    "- (dash), _ (underscore), and . (dot)."
)


class WorkfileSubversionError(ValueError):
    """Raised when a workfile Subversion value is not allowed."""


def is_valid_workfile_subversion(value: Optional[str]) -> bool:
    """Return whether ``value`` is allowed for Workfiles Subversion."""
    if value is None:
        return True
    return bool(WORKFILE_SUBVERSION_PATTERN.match(str(value)))


def is_valid_ayon_product_name(name: Optional[str]) -> bool:
    """Return whether ``name`` satisfies server GraphQL product name rules."""
    if name is None:
        return True
    text = str(name).strip()
    if not text:
        return True
    return bool(AYON_PRODUCT_NAME_PATTERN.match(text))


def sanitize_workfile_subversion(value: str) -> str:
    """Map disallowed characters to underscores for repair saves."""
    if not value:
        return ""
    sanitized = _INVALID_CHAR_PATTERN.sub("_", str(value))
    sanitized = _COLLAPSE_UNDERSCORES.sub("_", sanitized)
    return sanitized.strip("_")


def workfile_subversion_error_message(value: str) -> str:
    """Human-readable validation message for publisher/UI."""
    return (
        f"Workfile Subversion {value!r} contains characters that are not "
        f"allowed. {_SUBVERSION_HINT}"
    )


def require_valid_workfile_subversion(comment: Optional[str]) -> None:
    """Raise :class:`WorkfileSubversionError` if ``comment`` is non-empty and invalid."""
    if comment is None:
        return
    text = str(comment)
    if not text.strip():
        return
    if not is_valid_workfile_subversion(text):
        raise WorkfileSubversionError(
            workfile_subversion_error_message(text)
        )
