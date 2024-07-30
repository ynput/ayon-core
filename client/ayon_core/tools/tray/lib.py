import os
import sys
import json
import hashlib
import platform
import subprocess
import csv
import time
import signal
import locale
from typing import Optional, Dict, Tuple, Any

import ayon_api
import requests

from ayon_core.lib import Logger, get_ayon_launcher_args, run_detached_process
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
    encoding = locale.getpreferredencoding()
    csv_content = csv.DictReader(output.decode(encoding).splitlines())
    # if "PID" not in csv_content.fieldnames:
    #     return False
    for _ in csv_content:
        return True
    return False


def _is_process_running(pid: int) -> bool:
    """Check whether process with pid is running."""
    if platform.system().lower() == "windows":
        return _windows_pid_is_running(pid)

    if pid == 0:
        return True

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _kill_tray_process(pid: int):
    if _is_process_running(pid):
        os.kill(pid, signal.SIGTERM)


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


def _wait_for_starting_tray(
    server_url: Optional[str] = None,
    variant: Optional[str] = None,
    timeout: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Wait for tray to start.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        timeout (Optional[int]): Timeout for tray validation.

    Returns:
        Optional[Dict[str, Any]]: Tray file information.

    """
    if timeout is None:
        timeout = 10
    started_at = time.time()
    while True:
        data = get_tray_file_info(server_url, variant)
        if data is None:
            return None

        if data.get("started") is True:
            return data

        pid = data.get("pid")
        if pid and not _is_process_running(pid):
            remove_tray_server_url()
            return None

        if time.time() - started_at > timeout:
            return None
        time.sleep(0.1)


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
    timeout: Optional[int] = None
) -> Optional[str]:
    """Get tray server url.

    Does not validate if tray is running.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        validate (Optional[bool]): Validate if tray is running.
            By default, does not validate.
        timeout (Optional[int]): Timeout for tray start-up.

    Returns:
        Optional[str]: Tray server url.

    """
    data = get_tray_file_info(server_url, variant)
    if data is None:
        return None

    if data.get("started") is False:
        data = _wait_for_starting_tray(server_url, variant, timeout)
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


def set_tray_server_url(tray_url: Optional[str], started: bool):
    """Add tray server information file.

    Called from tray logic, do not use on your own.

    Args:
        tray_url (Optional[str]): Webserver url with port.
        started (bool): If tray is started. When set to 'False' it means
            that tray is starting up.

    """
    file_info = get_tray_file_info()
    if file_info and file_info["pid"] != os.getpid():
        if not file_info["started"] or _get_tray_information(file_info["url"]):
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


def remove_tray_server_url(force: Optional[bool] = False):
    """Remove tray information file.

    Called from tray logic, do not use on your own.

    Args:
        force (Optional[bool]): Force remove tray information file.

    """
    filepath = _get_tray_info_filepath()
    if not os.path.exists(filepath):
        return

    try:
        with open(filepath, "r") as stream:
            data = json.load(stream)
    except BaseException:
        data = {}

    if (
        force
        or not data
        or data.get("pid") == os.getpid()
        or not _is_process_running(data.get("pid"))
    ):
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
        remove_tray_server_url(force=True)
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


def show_message_in_tray(
    title, message, icon=None, msecs=None, tray_url=None
):
    """Show message in tray.

    Args:
        title (str): Message title.
        message (str): Message content.
        icon (Optional[Literal["information", "warning", "critical"]]): Icon
            for the message.
        msecs (Optional[int]): Duration of the message.
        tray_url (Optional[str]): Tray server url.

    """
    if not tray_url:
        tray_url = get_tray_server_url()

    # TODO handle this case, e.g. raise an error?
    if not tray_url:
        return

    # TODO handle response, can fail whole request or can fail on status
    requests.post(
        f"{tray_url}/tray/message",
        json={
            "title": title,
            "message": message,
            "icon": icon,
            "msecs": msecs
        }
    )


def make_sure_tray_is_running(
    ayon_url: Optional[str] = None,
    variant: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
):
    """Make sure that tray for AYON url and variant is running.

    Args:
        ayon_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        env (Optional[Dict[str, str]]): Environment variables for the process.

    """
    state = get_tray_state(ayon_url, variant)
    if state == TrayState.RUNNING:
        return

    if state == TrayState.STARTING:
        _wait_for_starting_tray(ayon_url, variant)
        state = get_tray_state(ayon_url, variant)
        if state == TrayState.RUNNING:
            return

    args = get_ayon_launcher_args("tray", "--force")
    if env is None:
        env = os.environ.copy()
    
    # Make sure 'QT_API' is not set
    env.pop("QT_API", None)

    if ayon_url:
        env["AYON_SERVER_URL"] = ayon_url

    # TODO maybe handle variant in a better way
    if variant:
        if variant == "staging":
            args.append("--use-staging")

    run_detached_process(args, env=env)


def main(force=False):
    from ayon_core.tools.tray.ui import main

    Logger.set_process_name("Tray")

    state = get_tray_state()
    if force and state in (TrayState.RUNNING, TrayState.STARTING):
        file_info = get_tray_file_info() or {}
        pid = file_info.get("pid")
        if pid is not None:
            _kill_tray_process(pid)
        remove_tray_server_url(force=True)
        state = TrayState.NOT_RUNNING

    if state == TrayState.RUNNING:
        show_message_in_tray(
            "Tray is already running",
            "Your AYON tray application is already running."
        )
        print("Tray is already running.")
        return

    if state == TrayState.STARTING:
        print("Tray is starting. Waiting for it to start.")
        _wait_for_starting_tray()
        state = get_tray_state()
        if state == TrayState.RUNNING:
            print("Tray started. Exiting.")
            return

        if state == TrayState.STARTING:
            print(
                "Tray did not start in expected time."
                " Killing the process and starting new."
            )
            file_info = get_tray_file_info() or {}
            pid = file_info.get("pid")
            if pid is not None:
                _kill_tray_process(pid)
            remove_tray_server_url(force=True)

    # Prepare the file with 'pid' information as soon as possible
    try:
        set_tray_server_url(None, False)
    except TrayIsRunningError:
        print("Tray is running")
        sys.exit(1)

    main()

