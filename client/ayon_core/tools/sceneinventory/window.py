from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core import style, resources
from ayon_core.tools.utils import PlaceholderLineEdit

from ayon_core.tools.sceneinventory import SceneInventoryController

from .view import SceneInventoryView


class SceneInventoryWindow(QtWidgets.QDialog):
    """Scene Inventory window"""

    def __init__(self, controller=None, parent=None):
        super().__init__(parent)

        if controller is None:
            controller = SceneInventoryController()

        project_name = controller.get_current_project_name()
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setWindowTitle("Scene Inventory - {}".format(project_name))
        self.setObjectName("SceneInventory")

        self.resize(1100, 480)

        filter_label = QtWidgets.QLabel("Search", self)
        text_filter = PlaceholderLineEdit(self)
        text_filter.setPlaceholderText("Filter by name...")

        outdated_only_checkbox = QtWidgets.QCheckBox(
            "Filter to outdated", self
        )
        outdated_only_checkbox.setToolTip("Show outdated files only")
        outdated_only_checkbox.setChecked(False)

        update_all_icon = qtawesome.icon("fa.arrow-up", color="white")
        update_all_button = QtWidgets.QPushButton(self)
        update_all_button.setToolTip("Update all outdated to latest version")
        update_all_button.setIcon(update_all_icon)

        refresh_icon = qtawesome.icon("fa.refresh", color="white")
        refresh_button = QtWidgets.QPushButton(self)
        refresh_button.setToolTip("Refresh")
        refresh_button.setIcon(refresh_icon)

        headers_widget = QtWidgets.QWidget(self)
        headers_layout = QtWidgets.QHBoxLayout(headers_widget)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        headers_layout.addWidget(filter_label, 0)
        headers_layout.addWidget(text_filter, 1)
        headers_layout.addWidget(outdated_only_checkbox, 0)
        headers_layout.addWidget(update_all_button, 0)
        headers_layout.addWidget(refresh_button, 0)

        view = SceneInventoryView(controller, self)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(headers_widget, 0)
        main_layout.addWidget(view, 1)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(0)
        show_timer.setSingleShot(False)

        # signals
        show_timer.timeout.connect(self._on_show_timer)
        text_filter.textChanged.connect(self._on_text_filter_change)
        outdated_only_checkbox.stateChanged.connect(
            self._on_outdated_state_change
        )
        view.hierarchy_view_changed.connect(
            self._on_hierarchy_view_change
        )
        view.data_changed.connect(self._on_refresh_request)
        refresh_button.clicked.connect(self._on_refresh_request)
        update_all_button.clicked.connect(self._on_update_all)

        self._show_timer = show_timer
        self._show_counter = 0
        self._controller = controller
        self._update_all_button = update_all_button
        self._outdated_only_checkbox = outdated_only_checkbox
        self._view = view

        self._first_show = True

    def showEvent(self, event):
        super(SceneInventoryWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())

        self._show_counter = 0
        self._show_timer.start()

    def keyPressEvent(self, event):
        """Custom keyPressEvent.

        Override keyPressEvent to do nothing so that Maya's panels won't
        take focus when pressing "SHIFT" whilst mouse is over viewport or
        outliner. This way users don't accidentally perform Maya commands
        whilst trying to name an instance.

        """
        pass

    def _on_refresh_request(self):
        """Signal callback to trigger 'refresh' without any arguments."""

        self.refresh()

    def refresh(self):
        self._controller.reset()
        self._view.refresh()

    def _on_show_timer(self):
        if self._show_counter < 3:
            self._show_counter += 1
            return
        self._show_timer.stop()
        self.refresh()

    def _on_hierarchy_view_change(self, enabled):
        self._view.set_hierarchy_view(enabled)

    def _on_text_filter_change(self, text_filter):
        self._view.set_text_filter(text_filter)

    def _on_outdated_state_change(self):
        self._view.set_filter_outdated(
            self._outdated_only_checkbox.isChecked()
        )

    def _on_update_all(self):
        self._view.update_all()
