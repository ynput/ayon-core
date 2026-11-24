"""Host-facing helpers to open the workfile template builder UI.

Host contract:

- Implement ``AbstractTemplateBuilder`` and create one instance per tool
  launch.
- Call ``show_workfile_template_builder(builder, parent)`` from the host menu
  or operator; the helper owns the per-process window.
- Use ``get_workfile_template_builder_window`` when the host operator must
  perform the single show itself (e.g. to avoid double-show flicker).
- Use ``open_template_ui`` for the destructive "open template" confirmation.
- Keep the Qt objects in the main thread; the controller backend does not
  require Qt.
"""

import traceback
import weakref

from qtpy import QtCore, QtWidgets, shiboken

from ayon_core.tools.utils.dialogs import show_message_dialog

# Only one template builder window per host process. A weak reference keeps
#   the module from owning the Qt widget.
_WINDOW_REF = None


def open_template_ui(builder, main_window):
    """Open template from `builder`

    Asks user about overwriting current scene and feedback exceptions.
    """
    result = QtWidgets.QMessageBox.question(
        main_window,
        "Opening template",
        "Caution! You will lose unsaved changes.\nDo you want to continue?",
        QtWidgets.QMessageBox.Yes | QtWidgets.QMessageBox.No
    )
    if result == QtWidgets.QMessageBox.Yes:
        try:
            builder.open_template()
        except Exception:
            show_message_dialog(
                title="Template Load Failed",
                message="".join(traceback.format_exc()),
                parent=main_window,
                level="critical"
            )


def _is_window_valid(window) -> bool:
    """Check that the Python wrapper still has a live C++ object."""
    if window is None:
        return False
    try:
        return shiboken.isValid(window)
    except RuntimeError:
        return False


def get_workfile_template_builder_window(builder, parent=None):
    """Get the single template builder window of the process.

    Reuses and refreshes the existing window when its C++ object is still
    alive. If the window was deleted, a new controller and window are
    created. The window is not shown; use ``show_workfile_template_builder``
    or let a host operator show it.

    Args:
        builder (AbstractTemplateBuilder): Template builder implementation.
        parent (Optional[QtWidgets.QWidget]): Parent window.

    Returns:
        WorkfileTemplateBuilderWindow: Window for the builder.

    """
    global _WINDOW_REF

    window = _WINDOW_REF() if _WINDOW_REF is not None else None
    if _is_window_valid(window):
        try:
            window.refresh()
            return window
        except RuntimeError:
            pass
    _WINDOW_REF = None

    from .control import WorkfileTemplateBuilderController
    from .ui import WorkfileTemplateBuilderWindow

    controller = WorkfileTemplateBuilderController(builder)
    window = WorkfileTemplateBuilderWindow(controller, parent=parent)
    window.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    _WINDOW_REF = weakref.ref(window)
    return window


def show_workfile_template_builder(builder, parent=None):
    """Show workfile template builder tool for a host.

    A single window is reused per host process. The window is deleted when
        closed, so a new one is created afterwards.

    Args:
        builder (AbstractTemplateBuilder): Template builder implementation
            of the host.
        parent (Optional[QtWidgets.QWidget]): Parent window, usually the
            main window of the host.

    Returns:
        WorkfileTemplateBuilderWindow: Shown window.

    """
    window = get_workfile_template_builder_window(builder, parent=parent)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
