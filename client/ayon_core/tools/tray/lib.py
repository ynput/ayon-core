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
    return os.getenv("AYON_SERVER_URL")


def _get_default_variant() -> str:
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
    data = f"{server_url}|{variant}"
    return hashlib.sha256(data.encode()).hexdigest()


def get_tray_storage_dir() -> str:
    return get_ayon_appdirs("tray")


def _get_tray_information(tray_url: str) -> Optional[Dict[str, Any]]:
    # TODO implement server side information
    response = requests.get(f"{tray_url}/tray")
    try:
        response.raise_for_status()
    except requests.HTTPError:
        return None
    return response.json()


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
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Optional[str]:
    data = get_tray_file_info(server_url, variant)
    if data is None:
        return None
    return data.get("url")


def set_tray_server_url(tray_url: str, started: bool):
    filepath = _get_tray_info_filepath()
    if os.path.exists(filepath):
        info = get_tray_file_info()
        if info.get("pid") != os.getpid():
            raise TrayIsRunningError("Tray is already running.")
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    data = {
        "url": tray_url,
        "pid": os.getpid(),
        "started": started
    }
    with open(filepath, "w") as stream:
        json.dump(data, stream)


def remove_tray_server_url():
    filepath = _get_tray_info_filepath()
    if not os.path.exists(filepath):
        return
    with open(filepath, "r") as stream:
        data = json.load(stream)
    if data.get("pid") != os.getpid():
        return
    os.remove(filepath)


def get_tray_information(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Optional[Dict[str, Any]]:
    tray_url = get_tray_server_url(server_url, variant)
    return _get_tray_information(tray_url)


def get_tray_state(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
):
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

