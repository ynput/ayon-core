from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core import style, resources
from ayon_core.tools.utils import PlaceholderLineEdit

from ayon_core.tools.sceneinventory import SceneInventoryController

from .view import SceneInventoryView
from .version_history import VersionHistoryWidget


class SceneInventoryWindow(QtWidgets.QDialog):
    """Scene Inventory window"""

    def __init__(self, controller=None, parent=None):
        if controller is None:
            controller = SceneInventoryController()

        title = "AYON Scene Inventory"
        subtitle = controller.get_window_subtitle()
        if subtitle:
            title += f" - {subtitle}"

        super().__init__(parent)

        self.setWindowTitle(title)
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

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

        # Checked state is hardly visible on the button itself
        history_icon = qtawesome.icon(
            "fa.history", color="white", color_on="#8fceff"
        )
        history_button = QtWidgets.QPushButton(self)
        history_button.setToolTip(
            "Show version history of the selected item"
        )
        history_button.setIcon(history_icon)
        history_button.setCheckable(True)

        headers_widget = QtWidgets.QWidget(self)
        headers_layout = QtWidgets.QHBoxLayout(headers_widget)
        headers_layout.setContentsMargins(0, 0, 0, 0)
        headers_layout.addWidget(filter_label, 0)
        headers_layout.addWidget(text_filter, 1)
        headers_layout.addWidget(outdated_only_checkbox, 0)
        headers_layout.addWidget(update_all_button, 0)
        headers_layout.addWidget(history_button, 0)
        headers_layout.addWidget(refresh_button, 0)

        # Version history shares the height of the window with the view
        #   and is hidden by default, so it never makes the window wider.
        body_splitter = QtWidgets.QSplitter(QtCore.Qt.Vertical, self)
        view = SceneInventoryView(controller, body_splitter)
        history_widget = VersionHistoryWidget(
            controller, parent=body_splitter
        )
        history_widget.setVisible(False)
        body_splitter.addWidget(view)
        body_splitter.addWidget(history_widget)
        body_splitter.setStretchFactor(0, 1)
        body_splitter.setStretchFactor(1, 0)
        body_splitter.setCollapsible(0, False)
        body_splitter.setCollapsible(1, False)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(headers_widget, 0)
        main_layout.addWidget(body_splitter, 1)

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
        view.selection_changed.connect(self._on_selection_change)
        history_button.toggled.connect(self._on_history_toggle)
        refresh_button.clicked.connect(self._on_refresh_request)
        update_all_button.clicked.connect(self._on_update_all)

        self._show_timer = show_timer
        self._show_counter = 0
        self._controller = controller
        self._update_all_button = update_all_button
        self._outdated_only_checkbox = outdated_only_checkbox
        self._view = view
        self._body_splitter = body_splitter
        self._history_button = history_button
        self._history_widget = history_widget

        self._first_show = True
        self._history_first_show = True

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
        # Container item ids are new after each refresh
        self._history_widget.set_selected_item_ids(
            self._view.get_selection_item_ids()
        )
        self._history_widget.refresh()

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

    def _on_selection_change(self):
        self._history_widget.set_selected_item_ids(
            self._view.get_selection_item_ids()
        )

    def _on_history_toggle(self, enabled):
        self._history_widget.setVisible(enabled)
        if enabled and self._history_first_show:
            # Split the height about evenly
            self._history_first_show = False
            height = self._body_splitter.height()
            self._body_splitter.setSizes([height // 2, height // 2])

    def _on_update_all(self):
        self._view.update_all()
