"""Icon definitions.

There are multiple places where icons are defined for UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import io
import urllib.request

import ayon_api

from .log import Logger

DEFAULT_WEB_ICON_COLOR = "#f4f5f5"

log = Logger.get_logger(__name__)


class IconBase(ABC):
    """Base class for icon definition.

    The base class is meant to be used for type validation of icon definition
        passed to functions.
    """

    @abstractmethod
    def get_unique_id(self) -> str:
        return ""


@dataclass
class PathIcon(IconBase):
    """Path to image file on disk."""
    path: str

    def get_unique_id(self):
        return f"path|{self.path}"


@dataclass
class MaterialSymbolsIcon(IconBase):
    """Material Symbols icon."""
    name: str
    color: str = field(default=DEFAULT_WEB_ICON_COLOR)

    def get_unique_id(self):
        return f"material-symbols|{self.name}|{self.color}"


@dataclass
class AwesomeFontIcon(IconBase):
    """Awesome Font icon."""
    name: str
    color: str = field(default=DEFAULT_WEB_ICON_COLOR)

    def get_unique_id(self):
        return f"awesome-font|{self.name}|{self.color}"


@dataclass
class UrlIcon(IconBase):
    """Url to an image file."""
    url: str

    def get_unique_id(self):
        return f"url|{self.url}"

    def get_content(self) -> bytes | None:
        try:
            return urllib.request.urlopen(self.url).read()
        except Exception:
            log.warning(
                "Failed to download image '%s'", self.url, exc_info=True
            )
            return b""


@dataclass
class AYONUrlIcon(IconBase):
    """Relative url to an image file on AYON server.

    Instead of using full url use relative path to image file on AYON server.
    - 'https://studio.ayon.app/addons/1.0.0/public/icon.png'
    - 'addons/1.0.0/public/icon.png'

    The main difference from 'UrlIcon' is that this approach also has access
        to endpoints that do require authentication.

    """
    url: str

    def __post_init__(self):
        self.url = self.url.lstrip("/")

    def get_unique_id(self):
        return f"ayon_url|{self.url}"

    def get_content(self) -> bytes:
        url = f"{ayon_api.get_base_url()}/{self.url}"
        try:
            stream = io.BytesIO()
            ayon_api.download_file_to_stream(url, stream)
            return stream.getvalue()
        except Exception:
            log.warning(
                "Failed to download image '%s'", url, exc_info=True
            )
            return b""


@dataclass
class TransparentIcon(IconBase):
    """Transparent icon."""
    size: int = 256

    def get_unique_id(self):
        return f"transparent-{self.size}"
