"""Cryptography traits."""
from __future__ import annotations

from typing import ClassVar, Optional

from pydantic import Field

from .trait import TraitBase


class DigitallySigned(TraitBase):
    """Digitally signed trait.

    This type trait means that the data is digitally signed.

    Attributes:
        signature (str): Digital signature.
    """
    id: ClassVar[str] = "ayon.cryptography.DigitallySigned.v1"
    name: ClassVar[str] = "DigitallySigned"
    description: ClassVar[str] = "Digitally signed trait."


class GPGSigned(DigitallySigned):
    """GPG signed trait.

    This trait holds GPG signed data.

    Attributes:
        signature (str): GPG signature.
    """
    id: ClassVar[str] = "ayon.cryptography.GPGSigned.v1"
    name: ClassVar[str] = "GPGSigned"
    description: ClassVar[str] = "GPG signed trait."
    signed_data: str = Field(
        ...,
        description="Signed data."
    )
    clear_text: Optional[str] = Field(
        None,
        description="Clear text."
    )
