from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import style, resources

from ayon_core.tools.launcher.control import BaseLauncherController
from ayon_core.tools.utils import MessageOverlayObject

from .projects_widget import ProjectsWidget
from .hierarchy_page import HierarchyPage
from .actions_widget import ActionsWidget


class LauncherWindow(QtWidgets.QWidget):
    """Launcher interface"""
    message_interval = 5000
    refresh_interval = 10000
    page_side_anim_interval = 250

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)

        if controller is None:
            controller = BaseLauncherController()

        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setWindowTitle("Launcher")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        self.setStyleSheet(style.load_stylesheet())

        # Allow minimize
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.CustomizeWindowHint
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )

        self._controller = controller

        overlay_object = MessageOverlayObject(self)

        # Main content - Pages & Actions
        content_body = QtWidgets.QSplitter(self)

        # Pages
        pages_widget = QtWidgets.QWidget(content_body)

        # - First page - Projects
        projects_page = ProjectsWidget(controller, pages_widget)

        # - Second page - Hierarchy (folders & tasks)
        hierarchy_page = HierarchyPage(controller, pages_widget)

        pages_layout = QtWidgets.QHBoxLayout(pages_widget)
        pages_layout.setContentsMargins(0, 0, 0, 0)
        pages_layout.addWidget(projects_page, 1)
        pages_layout.addWidget(hierarchy_page, 1)

        # Actions
        actions_widget = ActionsWidget(controller, content_body)

        # Vertically split Pages and Actions
        content_body.setContentsMargins(0, 0, 0, 0)
        content_body.setSizePolicy(
            QtWidgets.QSizePolicy.Expanding,
            QtWidgets.QSizePolicy.Expanding
        )
        content_body.setOrientation(QtCore.Qt.Vertical)
        content_body.addWidget(pages_widget)
        content_body.addWidget(actions_widget)

        # Set useful default sizes and set stretch
        # for the pages so that is the only one that
        # stretches on UI resize.
        content_body.setStretchFactor(0, 10)
        content_body.setSizes([580, 160])

        # Footer
        # footer_widget = QtWidgets.QWidget(self)
        #
        # action_history = ActionHistory(footer_widget)
        # action_history.setStatusTip("Show Action History")
        #
        # footer_layout = QtWidgets.QHBoxLayout(footer_widget)
        # footer_layout.setContentsMargins(0, 0, 0, 0)
        # footer_layout.addWidget(action_history, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(content_body, 1)
        # layout.addWidget(footer_widget, 0)

        actions_refresh_timer = QtCore.QTimer()
        actions_refresh_timer.setInterval(self.refresh_interval)

        page_slide_anim = QtCore.QVariantAnimation(self)
        page_slide_anim.setDuration(self.page_side_anim_interval)
        page_slide_anim.setStartValue(0.0)
        page_slide_anim.setEndValue(1.0)
        page_slide_anim.setEasingCurve(QtCore.QEasingCurve.OutQuad)

        projects_page.refreshed.connect(self._on_projects_refresh)
        actions_refresh_timer.timeout.connect(
            self._on_actions_refresh_timeout)
        page_slide_anim.valueChanged.connect(
            self._on_page_slide_value_changed)
        page_slide_anim.finished.connect(self._on_page_slide_finished)

        controller.register_event_callback(
            "selection.project.changed",
            self._on_project_selection_change,
        )
        controller.register_event_callback(
            "action.trigger.started",
            self._on_action_trigger_started,
        )
        controller.register_event_callback(
            "action.trigger.finished",
            self._on_action_trigger_finished,
        )
        controller.register_event_callback(
            "webaction.trigger.started",
            self._on_webaction_trigger_started,
        )
        controller.register_event_callback(
            "webaction.trigger.finished",
            self._on_webaction_trigger_finished,
        )

        self._overlay_object = overlay_object

        self._controller = controller

        self._is_on_projects_page = True
        self._window_is_active = False
        self._refresh_on_activate = False
        self._selected_project_name = None

        self._pages_widget = pages_widget
        self._pages_layout = pages_layout
        self._projects_page = projects_page
        self._hierarchy_page = hierarchy_page
        self._actions_widget = actions_widget
        # self._action_history = action_history

        self._actions_refresh_timer = actions_refresh_timer
        self._page_slide_anim = page_slide_anim

        hierarchy_page.setVisible(not self._is_on_projects_page)
        self.resize(520, 740)

    def showEvent(self, event):
        super().showEvent(event)
        self._window_is_active = True
        if not self._actions_refresh_timer.isActive():
            self._actions_refresh_timer.start()
        self._controller.refresh()

    def closeEvent(self, event):
        super().closeEvent(event)
        self._window_is_active = False
        self._actions_refresh_timer.stop()

    def changeEvent(self, event):
        if event.type() in (
            QtCore.QEvent.Type.WindowStateChange,
            QtCore.QEvent.ActivationChange,
        ):
            is_active = self.isActiveWindow() and not self.isMinimized()
            self._window_is_active = is_active
            if is_active and self._refresh_on_activate:
                self._refresh_on_activate = False
                self._on_actions_refresh_timeout()
                self._actions_refresh_timer.start()

        super().changeEvent(event)

    def _on_actions_refresh_timeout(self):
        # Stop timer if widget is not visible
        if self._window_is_active:
            self._controller.refresh_actions()
        else:
            self._refresh_on_activate = True

    def _on_project_selection_change(self, event):
        project_name = event["project_name"]
        self._selected_project_name = project_name
        if not project_name:
            self._go_to_projects_page()

        elif self._is_on_projects_page:
            self._go_to_hierarchy_page(project_name)

    def _on_projects_refresh(self):
        # Refresh only actions on projects page
        if self._is_on_projects_page:
            self._actions_widget.refresh()
            return

        # No projects were found -> go back to projects page
        if not self._projects_page.has_content():
            self._go_to_projects_page()
            return

        self._hierarchy_page.refresh()
        self._actions_widget.refresh()

    def _show_toast_message(self, message, success=True, message_id=None):
        message_type = None
        if not success:
            message_type = "error"

        self._overlay_object.add_message(
            message, message_type, message_id=message_id
        )

    def _on_action_trigger_started(self, event):
        self._show_toast_message(
            "Running action: {}".format(event["full_label"]),
            message_id=event["trigger_id"],
        )

    def _on_action_trigger_finished(self, event):
        action_label = event["full_label"]
        if event["failed"]:
            message = f"Failed to run action: {action_label}"
        else:
            message = f"Action finished: {action_label}"
        self._show_toast_message(
            message,
            not event["failed"],
            message_id=event["trigger_id"],
        )

    def _on_webaction_trigger_started(self, event):
        self._show_toast_message(
            "Running webaction: {}".format(event["full_label"]),
            message_id=event["trigger_id"],
        )

    def _on_webaction_trigger_finished(self, event):
        clipboard_text = event["clipboard_text"]
        if clipboard_text:
            clipboard = QtWidgets.QApplication.clipboard()
            clipboard.setText(clipboard_text)

        action_label = event["full_label"]
        # Avoid to show exception message
        if event["trigger_failed"]:
            self._show_toast_message(
                f"Failed to run action: {action_label}",
                message_id=event["trigger_id"]
            )
            return

        # Failed to run webaction, e.g. because of missing webaction handling
        # - not reported by server
        if event["error_message"]:
            self._show_toast_message(
                event["error_message"],
                success=False,
                message_id=event["trigger_id"]
            )
            return

        if event["message"]:
            self._show_toast_message(event["message"])

        if event["form"]:
            self._actions_widget.handle_webaction_form_event(event)

    def _is_page_slide_anim_running(self):
        return (
            self._page_slide_anim.state() == QtCore.QAbstractAnimation.Running
        )

    def _go_to_projects_page(self):
        if self._is_on_projects_page:
            return
        self._is_on_projects_page = True
        self._hierarchy_page.set_page_visible(False)

        self._start_page_slide_animation()

    def _go_to_hierarchy_page(self, project_name):
        if not self._is_on_projects_page:
            return
        self._is_on_projects_page = False
        self._hierarchy_page.set_page_visible(True, project_name)

        self._start_page_slide_animation()

    def _start_page_slide_animation(self):
        if self._is_on_projects_page:
            direction = QtCore.QAbstractAnimation.Backward
        else:
            direction = QtCore.QAbstractAnimation.Forward
        self._page_slide_anim.setDirection(direction)
        if self._is_page_slide_anim_running():
            return

        layout_spacing = self._pages_layout.spacing()
        if self._is_on_projects_page:
            hierarchy_geo = self._hierarchy_page.geometry()
            projects_geo = QtCore.QRect(hierarchy_geo)
            projects_geo.moveRight(
                hierarchy_geo.left() - (layout_spacing + 1))

            self._projects_page.setVisible(True)

        else:
            projects_geo = self._projects_page.geometry()
            hierarchy_geo = QtCore.QRect(projects_geo)
            hierarchy_geo.moveLeft(projects_geo.right() + layout_spacing)
            self._hierarchy_page.setVisible(True)

        while self._pages_layout.count():
            self._pages_layout.takeAt(0)

        self._projects_page.setGeometry(projects_geo)
        self._hierarchy_page.setGeometry(hierarchy_geo)

        self._page_slide_anim.start()

    def _on_page_slide_value_changed(self, value):
        layout_spacing = self._pages_layout.spacing()
        content_width = self._pages_widget.width() - layout_spacing
        content_height = self._pages_widget.height()

        # Visible widths of other widgets
        hierarchy_width = int(content_width * value)

        hierarchy_geo = QtCore.QRect(
            content_width - hierarchy_width, 0, content_width, content_height
        )
        projects_geo = QtCore.QRect(hierarchy_geo)
        projects_geo.moveRight(hierarchy_geo.left() - (layout_spacing + 1))

        self._projects_page.setGeometry(projects_geo)
        self._hierarchy_page.setGeometry(hierarchy_geo)

    def _on_page_slide_finished(self):
        self._pages_layout.addWidget(self._projects_page, 1)
        self._pages_layout.addWidget(self._hierarchy_page, 1)
        self._projects_page.setVisible(self._is_on_projects_page)
        self._hierarchy_page.setVisible(not self._is_on_projects_page)

    # def _on_history_action(self, history_data):
    #     action, session = history_data
    #     app = QtWidgets.QApplication.instance()
    #     modifiers = app.keyboardModifiers()
    #
    #     is_control_down = QtCore.Qt.ControlModifier & modifiers
    #     if is_control_down:
    #         # Revert to that "session" location
    #         self.set_session(session)
    #     else:
    #         # User is holding control, rerun the action
    #         self.run_action(action, session=session)
