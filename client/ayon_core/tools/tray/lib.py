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

import requests
from ayon_api.utils import get_default_settings_variant

from ayon_core.lib import (
    Logger,
    get_ayon_launcher_args,
    run_detached_process,
    get_ayon_username,
)
from ayon_core.lib.local_settings import get_launcher_local_dir


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
    return get_default_settings_variant()


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
    return get_launcher_local_dir("tray")


def _get_tray_info_filepath(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> str:
    hash_dir = get_tray_storage_dir()
    server_url, variant = _get_server_and_variant(server_url, variant)
    filename = _create_tray_hash(server_url, variant)
    return os.path.join(hash_dir, filename)


def _get_tray_file_info(
    server_url: Optional[str] = None,
    variant: Optional[str] = None
) -> Tuple[Optional[Dict[str, Any]], Optional[float]]:
    filepath = _get_tray_info_filepath(server_url, variant)
    if not os.path.exists(filepath):
        return None, None
    file_modified = os.path.getmtime(filepath)
    try:
        with open(filepath, "r") as stream:
            data = json.load(stream)
    except Exception:
        return None, file_modified

    return data, file_modified


def _remove_tray_server_url(
    server_url: Optional[str],
    variant: Optional[str],
    file_modified: Optional[float],
):
    """Remove tray information file.

    Called from tray logic, do not use on your own.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        file_modified (Optional[float]): File modified timestamp. Is validated
            against current state of file.

    """
    filepath = _get_tray_info_filepath(server_url, variant)
    if not os.path.exists(filepath):
        return

    if (
        file_modified is not None
        and os.path.getmtime(filepath) != file_modified
    ):
        return
    os.remove(filepath)


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
    file_info, _ = _get_tray_file_info(server_url, variant)
    return file_info


def _get_tray_rest_information(tray_url: str) -> Optional[Dict[str, Any]]:
    if not tray_url:
        return None
    try:
        response = requests.get(f"{tray_url}/tray")
        response.raise_for_status()
        return response.json()
    except (requests.HTTPError, requests.ConnectionError):
        return None


class TrayInfo:
    def __init__(
        self,
        server_url: str,
        variant: str,
        timeout: Optional[int] = None
    ):
        self.server_url = server_url
        self.variant = variant

        if timeout is None:
            timeout = 10

        self._timeout = timeout

        self._file_modified = None
        self._file_info = None
        self._file_info_cached = False
        self._tray_info = None
        self._tray_info_cached = False
        self._file_state = None
        self._state = None

    @classmethod
    def new(
        cls,
        server_url: Optional[str] = None,
        variant: Optional[str] = None,
        timeout: Optional[int] = None,
        wait_to_start: Optional[bool] = True
    ) -> "TrayInfo":
        server_url, variant = _get_server_and_variant(server_url, variant)
        obj = cls(server_url, variant, timeout=timeout)
        if wait_to_start:
            obj.wait_to_start()
        return obj

    def get_pid(self) -> Optional[int]:
        file_info = self.get_file_info()
        if file_info:
            return file_info.get("pid")
        return None

    def reset(self):
        self._file_modified = None
        self._file_info = None
        self._file_info_cached = False
        self._tray_info = None
        self._tray_info_cached = False
        self._state = None
        self._file_state = None

    def get_file_info(self) -> Optional[Dict[str, Any]]:
        if not self._file_info_cached:
            file_info, file_modified = _get_tray_file_info(
                self.server_url, self.variant
            )
            self._file_info = file_info
            self._file_modified = file_modified
            self._file_info_cached = True
        return self._file_info

    def get_file_url(self) -> Optional[str]:
        file_info = self.get_file_info()
        if file_info:
            return file_info.get("url")
        return None

    def get_tray_url(self) -> Optional[str]:
        info = self.get_tray_info()
        if info:
            return self.get_file_url()
        return None

    def get_tray_info(self) -> Optional[Dict[str, Any]]:
        if self._tray_info_cached:
            return self._tray_info

        tray_url = self.get_file_url()
        tray_info = None
        if tray_url:
            tray_info = _get_tray_rest_information(tray_url)

        self._tray_info = tray_info
        self._tray_info_cached = True
        return self._tray_info

    def get_file_state(self) -> int:
        if self._file_state is not None:
            return self._file_state

        state = TrayState.NOT_RUNNING
        file_info = self.get_file_info()
        if file_info:
            state = TrayState.STARTING
            if file_info.get("started") is True:
                state = TrayState.RUNNING
        self._file_state = state
        return self._file_state

    def get_state(self) -> int:
        if self._state is not None:
            return self._state

        state = self.get_file_state()
        if state == TrayState.RUNNING and not self.get_tray_info():
            state = TrayState.NOT_RUNNING
            pid = self.pid
            if pid:
                _kill_tray_process(pid)
            # Remove the file as tray is not running anymore and update
            #    the state of this object.
            _remove_tray_server_url(
                self.server_url, self.variant, self._file_modified
            )
            self.reset()

        self._state = state
        return self._state

    def get_ayon_username(self) -> Optional[str]:
        tray_info = self.get_tray_info()
        if tray_info:
            return tray_info.get("username")
        return None

    def wait_to_start(self) -> bool:
        _wait_for_starting_tray(
            self.server_url, self.variant, self._timeout
        )
        self.reset()
        return self.get_file_state() == TrayState.RUNNING

    pid = property(get_pid)
    state = property(get_state)


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
    tray_info = TrayInfo.new(
        server_url, variant, timeout, wait_to_start=True
    )
    if validate:
        return tray_info.get_tray_url()
    return tray_info.get_file_url()


def set_tray_server_url(tray_url: Optional[str], started: bool):
    """Add tray server information file.

    Called from tray logic, do not use on your own.

    Args:
        tray_url (Optional[str]): Webserver url with port.
        started (bool): If tray is started. When set to 'False' it means
            that tray is starting up.

    """
    info = TrayInfo.new(wait_to_start=False)
    if (
        info.pid
        and info.pid != os.getpid()
        and info.state in (TrayState.RUNNING, TrayState.STARTING)
    ):
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
    variant: Optional[str] = None,
    timeout: Optional[int] = None,
) -> TrayInfo:
    """Get information about tray.

    Args:
        server_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        timeout (Optional[int]): Timeout for tray start-up.

    Returns:
        TrayInfo: Tray information.

    """
    return TrayInfo.new(server_url, variant, timeout)


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
    tray_info = get_tray_information(server_url, variant)
    return tray_info.state


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
    username: Optional[str] = None,
    env: Optional[Dict[str, str]] = None
):
    """Make sure that tray for AYON url and variant is running.

    Args:
        ayon_url (Optional[str]): AYON server url.
        variant (Optional[str]): Settings variant.
        username (Optional[str]): Username under which should be tray running.
        env (Optional[Dict[str, str]]): Environment variables for the process.

    """
    tray_info = TrayInfo.new(
        ayon_url, variant, wait_to_start=False
    )
    if tray_info.state == TrayState.STARTING:
        tray_info.wait_to_start()

    if tray_info.state == TrayState.RUNNING:
        if not username:
            username = get_ayon_username()
        if tray_info.get_ayon_username() == username:
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

    tray_info = TrayInfo.new(wait_to_start=False)

    file_state = tray_info.get_file_state()
    if force and file_state in (TrayState.RUNNING, TrayState.STARTING):
        pid = tray_info.pid
        if pid is not None:
            _kill_tray_process(pid)
        remove_tray_server_url(force=True)
        file_state = TrayState.NOT_RUNNING

    if file_state in (TrayState.RUNNING, TrayState.STARTING):
        expected_username = get_ayon_username()
        username = tray_info.get_ayon_username()
        # TODO probably show some message to the user???
        if expected_username != username:
            pid = tray_info.pid
            if pid is not None:
                _kill_tray_process(pid)
            remove_tray_server_url(force=True)
            file_state = TrayState.NOT_RUNNING

    if file_state == TrayState.RUNNING:
        if tray_info.get_state() == TrayState.RUNNING:
            show_message_in_tray(
                "Tray is already running",
                "Your AYON tray application is already running."
            )
            print("Tray is already running.")
            return
        file_state = tray_info.get_file_state()

    if file_state == TrayState.STARTING:
        print("Tray is starting. Waiting for it to start.")
        tray_info.wait_to_start()
        file_state = tray_info.get_file_state()
        if file_state == TrayState.RUNNING:
            print("Tray started. Exiting.")
            return

        if file_state == TrayState.STARTING:
            print(
                "Tray did not start in expected time."
                " Killing the process and starting new."
            )
            pid = tray_info.pid
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

