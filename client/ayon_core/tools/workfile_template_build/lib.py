import traceback
import weakref

from qtpy import QtCore, QtWidgets

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
    global _WINDOW_REF

    if _WINDOW_REF is not None:
        window = _WINDOW_REF()
        if window is not None:
            window.show()
            window.raise_()
            window.activateWindow()
            return window

    from .control import WorkfileTemplateBuilderController
    from .ui import WorkfileTemplateBuilderWindow

    controller = WorkfileTemplateBuilderController(builder)
    window = WorkfileTemplateBuilderWindow(controller, parent=parent)
    window.setAttribute(QtCore.Qt.WA_DeleteOnClose, True)
    _WINDOW_REF = weakref.ref(window)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
