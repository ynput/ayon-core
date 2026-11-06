import traceback

from qtpy import QtWidgets

from ayon_core.tools.utils.dialogs import show_message_dialog


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

    Note:
        Returned window must be kept alive by the caller, otherwise it is
            garbage collected right away.

    Args:
        builder (AbstractTemplateBuilder): Template builder implementation
            of the host.
        parent (Optional[QtWidgets.QWidget]): Parent window, usually the
            main window of the host.

    Returns:
        WorkfileTemplateBuilderWindow: Shown window.

    """
    from .control import WorkfileTemplateBuilderController
    from .ui import WorkfileTemplateBuilderWindow

    controller = WorkfileTemplateBuilderController(builder)
    window = WorkfileTemplateBuilderWindow(controller, parent=parent)
    window.show()
    window.raise_()
    window.activateWindow()
    return window
