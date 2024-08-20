import os
import sys
import contextlib
import tempfile
import json
import traceback
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

    Todos:
        Make this functionality with the dialog as unified function, so it can
            be used elsewhere.

    Args:
        process_context (ProcessContext): The context in which the
            error occurred.
        message (str): The message to show.
        detail (Optional[str]): The detail message to show (usually
            traceback).

    """
    if process_context.headless:
        if detail:
            print(detail)
        print(f"{10*'*'}\n{message}\n{10*'*'}")
        return

    current_dir = os.path.dirname(os.path.abspath(__file__))
    script_path = os.path.join(current_dir, "ui", "process_ready_error.py")
    with tempfile.NamedTemporaryFile("w", delete=False) as tmp:
        tmp_path = tmp.name
        json.dump(
            {"message": message, "detail": detail},
            tmp.file
        )

    try:
        run_ayon_launcher_process(
            "--skip-bootstrap",
            script_path,
            tmp_path,
            add_sys_paths=True,
            creationflags=0,
        )

    finally:
        os.remove(tmp_path)


def _start_tray():
    from ayon_core.tools.tray import make_sure_tray_is_running

    make_sure_tray_is_running()


def ensure_addons_are_process_context_ready(
    process_context: ProcessContext,
    addons_manager: Optional[AddonsManager] = None,
    exit_on_failure: bool = True,
) -> bool:
    """Ensure all enabled addons are ready to be used in the given context.

    Call this method only in AYON launcher process and as first thing
        to avoid possible clashes with preparation. For example 'QApplication'
        should not be created.

    Todos:
        Run all preparations and allow to "ignore" failed preparations.
            Right now single addon can block using certain actions.

    Args:
        process_context (ProcessContext): The context in which the
            addons should be prepared.
        addons_manager (Optional[AddonsManager]): The addons
            manager to use. If not provided, a new one will be created.
        exit_on_failure (bool, optional): If True, the process will exit
            if an error occurs. Defaults to True.

    Returns:
        bool: True if all addons are ready, False otherwise.

    """
    if addons_manager is None:
        addons_manager = AddonsManager()

    message = None
    failed = False
    use_detail = False
    # Wrap the output in StringIO to capture it for details on fail
    # - but in case stdout was invalid on start of process also store
    #   the tracebacks
    tracebacks = []
    output = StringIO()
    with contextlib.redirect_stdout(output):
        with contextlib.redirect_stderr(output):
            for addon in addons_manager.get_enabled_addons():
                addon_failed = True
                try:
                    addon.ensure_is_process_ready(process_context)
                    addon_failed = False
                except ProcessPreparationError as exc:
                    message = str(exc)
                    print(f"Addon preparation failed: '{addon.name}'")
                    print(message)

                except BaseException:
                    use_detail = True
                    message = "An unexpected error occurred."
                    formatted_traceback = "".join(traceback.format_exception(
                        *sys.exc_info()
                    ))
                    tracebacks.append(formatted_traceback)
                    print(f"Addon preparation failed: '{addon.name}'")
                    print(message)
                    # Print the traceback so it is in the stdout
                    print(formatted_traceback)

                if addon_failed:
                    failed = True
                    break

    output_str = output.getvalue()
    # Print stdout/stderr to console as it was redirected
    print(output_str)
    if not failed:
        if not process_context.headless:
            _start_tray()
        return True

    detail = None
    if use_detail:
        # In case stdout was not captured, use the tracebacks as detail
        if not output_str:
            output_str = "\n".join(tracebacks)
        detail = output_str

    _handle_error(process_context, message, detail)
    if exit_on_failure:
        sys.exit(1)
    return False


def ensure_addons_are_process_ready(
    addon_name: str,
    addon_version: str,
    project_name: Optional[str] = None,
    headless: Optional[bool] = None,
    *,
    addons_manager: Optional[AddonsManager] = None,
    exit_on_failure: bool = True,
    **kwargs,
) -> bool:
    """Ensure all enabled addons are ready to be used in the given context.

    Call this method only in AYON launcher process and as first thing
        to avoid possible clashes with preparation. For example 'QApplication'
        should not be created.

    Args:
        addon_name (str): Addon name which triggered process.
        addon_version (str): Addon version which triggered process.
        project_name (Optional[str]): Project name. Can be filled in case
            process is triggered for specific project. Some addons can have
            different behavior based on project. Value is NOT autofilled.
        headless (Optional[bool]): Is process running in headless mode. Value
            is filled with value based on state set in AYON launcher.
        addons_manager (Optional[AddonsManager]): The addons
            manager to use. If not provided, a new one will be created.
        exit_on_failure (bool, optional): If True, the process will exit
            if an error occurs. Defaults to True.
        kwargs: The keyword arguments to pass to the ProcessContext.

    Returns:
        bool: True if all addons are ready, False otherwise.

    """
    context: ProcessContext = ProcessContext(
        addon_name,
        addon_version,
        project_name,
        headless,
        **kwargs
    )
    return ensure_addons_are_process_context_ready(
        context, addons_manager, exit_on_failure
    )
