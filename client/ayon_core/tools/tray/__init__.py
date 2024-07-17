import os
from typing import Optional, Dict, Any

import ayon_api


def _get_default_server_url() -> str:
    return os.getenv("AYON_SERVER_URL")


def _get_default_variant() -> str:
    return ayon_api.get_default_settings_variant()


def get_tray_store_dir() -> str:
    pass


def get_tray_information(
    sever_url: str, variant: str
) -> Optional[Dict[str, Any]]:
    pass


def validate_tray_server(server_url: str) -> bool:
    tray_info = get_tray_information(server_url)
    if tray_info is None:
        return False
    return True


def get_tray_server_url(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Optional[str]:
    if not server_url:
        server_url = _get_default_server_url()
    if not variant:
        variant = _get_default_variant()


def is_tray_running(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> bool:
    server_url = get_tray_server_url(server_url, variant)
    if server_url and validate_tray_server(server_url):
        return True
    return False
