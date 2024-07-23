import os
import json
import hashlib
import subprocess
import csv
import time
import signal
from typing import Optional, Dict, Tuple, Any

import ayon_api
import requests

from ayon_core.lib import Logger
from ayon_core.lib.local_settings import get_ayon_appdirs


class TrayState:
    NOT_RUNNING = 0
    STARTING = 1
    RUNNING = 2


class TrayIsRunningError(Exception):
    pass


def _get_default_server_url() -> str:
    """Get default AYON server url."""
    return os.getenv("AYON_SERVER_URL")


def _get_default_variant() -> str:
    """Get default settings variant."""
    return ayon_api.get_default_settings_variant()


def _get_server_and_variant(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Tuple[str, str]:
    if not server_url:
        server_url = _get_default_server_url()
    if not variant:
        variant = _get_default_variant()
    return server_url, variant


def _windows_pid_is_running(pid: int) -> bool:
    args = ["tasklist.exe", "/fo", "csv", "/fi", f"PID eq {pid}"]
    output = subprocess.check_output(args)
    csv_content = csv.DictReader(output.decode("utf-8").splitlines())
    # if "PID" not in csv_content.fieldnames:
    #     return False
    for _ in csv_content:
        return True
    return False


def _create_tray_hash(server_url: str, variant: str) -> str:
    """Create tray hash for metadata filename.

    Args:
        server_url (str): AYON server url.
        variant (str): Settings variant.

    Returns:
        str: Hash for metadata filename.

    """
    data = f"{server_url}|{variant}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_tray_storage_dir() -> str:
    """Get tray storage directory.

    Returns:
        str: Tray storage directory where metadata files are stored.

    """
    return get_ayon_appdirs("tray")


def _get_tray_information(tray_url: str) -> Optional[Dict[str, Any]]:
    if not tray_url:
        return None
    try:
        response = requests.get(f"{tray_url}/tray")
        response.raise_for_status()
        return response.json()
    except (requests.HTTPError, requests.ConnectionError):
        return None


def _get_tray_info_filepath(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> str:
    hash_dir = get_tray_storage_dir()
    server_url, variant = _get_server_and_variant(server_url, variant)
    filename = _create_tray_hash(server_url, variant)
    return os.path.join(hash_dir, filename)


def get_tray_file_info(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get tray information from file.

    Metadata information about running tray that should contain tray
        server url.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.

    Returns:
        Optional[Dict[str, Any]]: Tray information.

    """
    filepath = _get_tray_info_filepath(server_url, variant)
    if not os.path.exists(filepath):
        return None
    try:
        with open(filepath, "r") as stream:
            data = json.load(stream)
    except Exception:
        return None
    return data


def get_tray_server_url(
    validate: Optional[bool] = False,
    server_url: Optional[str] = None,
    variant: Optional[str] = None,
) -> Optional[str]:
    """Get tray server url.

    Does not validate if tray is running.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        validate (Optional[bool]): Validate if tray is running.
            By default, does not validate.

    Returns:
        Optional[str]: Tray server url.

    """
    data = get_tray_file_info(server_url, variant)
    if data is None:
        return None
    url = data.get("url")
    if not url:
        return None

    if not validate:
        return url

    if _get_tray_information(url):
        return url
    return None


def set_tray_server_url(tray_url: str, started: bool):
    """Add tray server information file.

    Called from tray logic, do not use on your own.

    Args:
        tray_url (str): Webserver url with port.
        started (bool): If tray is started. When set to 'False' it means
            that tray is starting up.

    """
    file_info = get_tray_file_info()
    if file_info and file_info.get("pid") != os.getpid():
        tray_url = file_info.get("url")
        if _get_tray_information(tray_url):
            raise TrayIsRunningError("Tray is already running.")

    filepath = _get_tray_info_filepath()
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "url": tray_url,
        "pid": os.getpid(),
        "started": started
    }
    with open(filepath, "w") as stream:
        json.dump(data, stream)


def remove_tray_server_url():
    """Remove tray information file.

    Called from tray logic, do not use on your own.
    """
    filepath = _get_tray_info_filepath()
    if not os.path.exists(filepath):
        return

    with open(filepath, "r") as stream:
        data = json.load(stream)

    if data.get("pid") == os.getpid():
        os.remove(filepath)


def get_tray_information(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    """Get information about tray.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.

    Returns:
        Optional[Dict[str, Any]]: Tray information.

    """
    tray_url = get_tray_server_url(server_url, variant)
    return _get_tray_information(tray_url)


def get_tray_state(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> int:
    """Get tray state for AYON server and variant.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.

    Returns:
        int: Tray state.

    """
    file_info = get_tray_file_info(server_url, variant)
    if file_info is None:
        return TrayState.NOT_RUNNING

    if file_info.get("started") is False:
        return TrayState.STARTING

    tray_url = file_info.get("url")
    info = _get_tray_information(tray_url)
    if not info:
        # Remove the information as the tray is not running
        remove_tray_server_url()
        return TrayState.NOT_RUNNING
    return TrayState.RUNNING


def is_tray_running(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> bool:
    """Check if tray is running.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.

    Returns:
        bool: True if tray is running

    """
    state = get_tray_state(server_url, variant)
    return state != TrayState.NOT_RUNNING


def main():
    from ayon_core.tools.tray.ui import main

    Logger.set_process_name("Tray")

    state = get_tray_state()
    if state == TrayState.RUNNING:
        # TODO send some information to tray?
        print("Tray is already running.")
        return

    if state == TrayState.STARTING:
        print("Tray is starting.")
        return
        # TODO try to handle stuck tray?
        time.sleep(5)
        state = get_tray_state()
        if state == TrayState.RUNNING:
            return
        if state == TrayState.STARTING:
            file_info = get_tray_file_info() or {}
            pid = file_info.get("pid")
            if pid is not None:
                os.kill(pid, signal.SIGTERM)
            remove_tray_server_url()

    main()

