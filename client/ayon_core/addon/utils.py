import os
import sys
import contextlib
import tempfile
import json
from io import StringIO
from typing import Optional

from ayon_core.lib import run_ayon_launcher_process

from .base import AddonsManager, ProcessContext, ProcessPreparationError


def _handle_error(
    process_context: ProcessContext,
    message: str,
    detail: Optional[str],
):
    """Handle error in process ready preparation.

    Shows UI to inform user about the error, or prints the message
        to stdout if running in headless mode.

    Args:
        process_context (ProcessContext): The context in which the
            error occurred.
        message (str): The message to show.
        detail (Optional[str]): The detail message to show (usually
            traceback).

    """
    if process_context.headless:
        print(detail)
        print(f"{10*'*'}\n{message}\n{10*'*'}")
        return

    current_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_dir, "ui", "process_ready_error.py")
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp_path = tmp.name

    try:
        with open(tmp_path, "w") as stream:
            json.dump(
                {"message": message, "detail": detail},
                stream
            )

        run_ayon_launcher_process(
            "run", script_path, tmp_path
        )

    finally:
        os.remove(tmp_path)


def ensure_addons_are_process_ready(
    process_context: ProcessContext,
    addons_manager: Optional[AddonsManager] = None,
    exit_on_failure: bool = True,
):
    """Ensure all enabled addons are ready to be used in the given context.

    Call this method only in AYON launcher process and as first thing
        to avoid possible clashes with preparation. For example 'QApplication'
        should not be created.

    Args:
        process_context (ProcessContext): The context in which the
            addons should be prepared.
        addons_manager (Optional[AddonsManager]): The addons
            manager to use. If not provided, a new one will be created.
        exit_on_failure (bool, optional): If True, the process will exit
            if an error occurs. Defaults to True.

    Returns:
        Optional[Exception]: The exception that occurred during the
            preparation, if any.

    """
    if addons_manager is None:
        addons_manager = AddonsManager()

    exc = None
    message = None
    failed = False
    use_detail = False
    with contextlib.redirect_stdout(StringIO()) as stdout:
        for addon in addons_manager.get_enabled_addons():
            failed = True
            try:
                addon.ensure_is_process_ready(process_context)
                failed = False
            except ProcessPreparationError as exc:
                message = str(exc)

            except BaseException as exc:
                message = "An unexpected error occurred."
                use_detail = True

            if failed:
                break

    if failed:
        detail = None
        if use_detail:
            detail = stdout.get_value()

        _handle_error(process_context, message, detail)
        if not exit_on_failure:
            return exc
        sys.exit(1)
