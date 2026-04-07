"""Icon definitions.

There are multiple places where icons are defined for UI.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
import io
import urllib.request
from typing import ClassVar

import ayon_api

from .log import Logger

DEFAULT_WEB_ICON_COLOR = "#f4f5f5"

log = Logger.get_logger(__name__)


class IconBase(ABC):
    """Base class for icon definition.

    The base class is meant to be used for type validation of icon definition
        passed to functions.
    """

    @property
    @abstractmethod
    def type(self) -> str:
        pass

    @abstractmethod
    def get_unique_id(self) -> str:
        pass


@dataclass
class PathIcon(IconBase):
    """Path to image file on disk."""
    type: ClassVar[str] = "path"
    path: str

    def get_unique_id(self) -> str:
        return f"{self.type}|{self.path}"


@dataclass
class MaterialSymbolsIcon(IconBase):
    """Material Symbols icon."""
    type: ClassVar[str] = "material-symbols"
    name: str
    color: str = field(default=DEFAULT_WEB_ICON_COLOR)

    def get_unique_id(self) -> str:
        return f"{self.type}|{self.name}|{self.color}"


@dataclass
class AwesomeFontIcon(IconBase):
    """Awesome Font icon."""
    type: ClassVar[str] = "awesome-font"
    name: str
    color: str = field(default=DEFAULT_WEB_ICON_COLOR)

    def get_unique_id(self) -> str:
        return f"{self.type}|{self.name}|{self.color}"


@dataclass
class UrlIcon(IconBase):
    """Url to an image file."""
    type: ClassVar[str] = "url"
    url: str

    def get_unique_id(self) -> str:
        return f"{self.type}|{self.url}"

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
    type: ClassVar[str] = "ayon_url"
    url: str

    def __post_init__(self):
        self.url = self.url.lstrip("/")

    def get_unique_id(self) -> str:
        return f"{self.type}|{self.url}"

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
    type: ClassVar[str] = "transparent"
    size: int = 256

    def get_unique_id(self):
        return f"{self.type}|{self.size}"


def get_icon_def_from_data(icon_data: dict) -> IconBase:
    icon_type = icon_data["type"]
    if icon_type == "path":
        return PathIcon(path=icon_data["path"])

    if icon_type == "material-symbols":
        kwargs = {}
        color = icon_data.get("color")
        if color:
            kwargs["color"] = color
        return MaterialSymbolsIcon(icon_data["name"], **kwargs)

    if icon_type == "awesome-font":
        kwargs = {}
        color = icon_data.get("color")
        if color:
            kwargs["color"] = color
        return AwesomeFontIcon(icon_data["name"], **kwargs)

    if icon_type == "url":
        return UrlIcon(url=icon_data["url"])

    if icon_type == "ayon_url":
        return AYONUrlIcon(url=icon_data["url"])

    if icon_type == "transparent":
        return TransparentIcon(size=icon_data["size"])

    raise ValueError(f"Unknown icon type: {icon_type}")
