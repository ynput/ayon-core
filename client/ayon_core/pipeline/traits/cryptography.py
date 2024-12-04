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


class PGPSigned(DigitallySigned):
    """PGP signed trait.

    This trait holds PGP (RFC-4880) signed data.

    Attributes:
        signature (str): PGP signature.
    """
    id: ClassVar[str] = "ayon.cryptography.PGPSigned.v1"
    name: ClassVar[str] = "PGPSigned"
    description: ClassVar[str] = "PGP signed trait."
    signed_data: str = Field(
        ...,
        description="Signed data."
    )
    clear_text: Optional[str] = Field(
        None,
        description="Clear text."
    )
