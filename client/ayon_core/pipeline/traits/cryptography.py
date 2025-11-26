"""Cryptography traits."""
from __future__ import annotations

from dataclasses import dataclass
from typing import ClassVar, Optional

from .trait import TraitBase


@dataclass
class DigitallySigned(TraitBase):
    """Digitally signed trait.

    This type trait means that the data is digitally signed.

    Attributes:
        signature (str): Digital signature.
    """

    id: ClassVar[str] = "ayon.cryptography.DigitallySigned.v1"
    name: ClassVar[str] = "DigitallySigned"
    description: ClassVar[str] = "Digitally signed trait."
    persistent: ClassVar[bool] = True


@dataclass
class PGPSigned(DigitallySigned):
    """PGP signed trait.

    This trait holds PGP (RFC-4880) signed data.

    Attributes:
        signed_data (str): Signed data.
        clear_text (str): Clear text.
    """

    id: ClassVar[str] = "ayon.cryptography.PGPSigned.v1"
    name: ClassVar[str] = "PGPSigned"
    description: ClassVar[str] = "PGP signed trait."
    persistent: ClassVar[bool] = True
    signed_data: str
    clear_text: Optional[str] = None
