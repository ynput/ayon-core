"""Main window of workfile template builder tool."""

from __future__ import annotations

import traceback
from typing import Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core import resources, style
from ayon_core.ui.components import AYButton, AYContainer

from ..abstract import (
    BUILD_CONTEXT_CHANGED_TOPIC,
    PLACEHOLDERS_REFRESHED_TOPIC,
    ActionResult,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from ..control import WorkfileTemplateBuilderController
from .window_actions import WindowActionsMixin
from .constants import EDITOR_PAGE, HINT_PAGE
from .context_bar import ContextBarWidget
from .editor_widget import (
    OPTIONS_CONTENT_OBJECT_NAME,
    OPTIONS_SCROLL_OBJECT_NAME,
    PlaceholderEditorWidget,
)
from .guide_widget import PlaceholderGuideWidget
from .placeholders_widget import PlaceholdersWidget
from .utils import (
    DIVIDER_COLOR,
    INPUT_COLOR,
    PANEL_COLOR,
    get_palette_color,
)


SPLITTER_OBJECT_NAME = "WorkfileTemplateBuilderSplitter"
PAGES_OBJECT_NAME = "WorkfileTemplateBuilderPages"
DIVIDER_OBJECT_NAME = "WorkfileTemplateBuilderDivider"

# Margin inside of the panels
PANEL_MARGIN = 10
# Width of the splitter handle between the panels
SPLITTER_HANDLE_WIDTH = 6

# Input widgets of the placeholder options
OPTION_INPUT_TYPES = (
    "QAbstractSpinBox",
    "QLineEdit",
    "QPlainTextEdit",
    "QTextEdit",
    "QComboBox",
)


def _get_window_stylesheet() -> str:
    """Rules applied on top of the AYON stylesheet.

    The AYON stylesheet paints every widget with a background color, widgets
    between the panel and the option inputs should show the panel instead.
    Option inputs use the same color as the inputs of the AYON components,
    e.g. the placeholders filter. Separators of the options are as thin as
    the divider below the context bar.

    Returns:
        str: Stylesheet.

    """
    content = "#{}".format(OPTIONS_CONTENT_OBJECT_NAME)
    inputs_selector = ",\n".join(
        "{} {}".format(content, widget_type)
        for widget_type in OPTION_INPUT_TYPES
    )
    disabled_selector = ",\n".join(
        "{} {}:disabled".format(content, widget_type)
        for widget_type in OPTION_INPUT_TYPES
    )
    return """
#{splitter},
#{pages},
#{scroll},
#{scroll} > QWidget,
{content} {{
    background: transparent;
}}
#{divider},
{content} #Separator {{
    background: {divider_color};
}}
{content} #Separator {{
    min-height: 1px;
    max-height: 1px;
}}
{inputs_selector} {{
    background: {input_color};
}}
{disabled_selector} {{
    background: {panel_color};
}}
""".format(
        splitter=SPLITTER_OBJECT_NAME,
        pages=PAGES_OBJECT_NAME,
        scroll=OPTIONS_SCROLL_OBJECT_NAME,
        content=content,
        divider=DIVIDER_OBJECT_NAME,
        divider_color=get_palette_color(DIVIDER_COLOR),
        inputs_selector=inputs_selector,
        input_color=get_palette_color(INPUT_COLOR),
        disabled_selector=disabled_selector,
        panel_color=get_palette_color(PANEL_COLOR),
    )


class WorkfileTemplateBuilderWindow(WindowActionsMixin, AYContainer):
    """Manage placeholders of a workfile template.

    Args:
        controller (WorkfileTemplateBuilderController): Backend of the tool.
        parent (Optional[QtWidgets.QWidget]): Parent widget.

    """

    def __init__(
        self,
        controller: WorkfileTemplateBuilderController,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_margin=0,
        )

        self.setWindowTitle("AYON Workfile Template Builder - {}".format(
            controller.get_host_name()
        ))
        self.setWindowIcon(QtGui.QIcon(resources.get_ayon_icon_filepath()))
        self.setObjectName("WorkfileTemplateBuilderWindow")
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.Window)

        # --- Workfile and context ---
        context_bar = ContextBarWidget(PANEL_MARGIN, self)
        divider_widget = QtWidgets.QWidget(self)
        divider_widget.setObjectName(DIVIDER_OBJECT_NAME)
        divider_widget.setFixedHeight(1)

        # --- Placeholders panel ---
        placeholders_panel = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_margin=PANEL_MARGIN,
            layout_spacing=8,
        )
        placeholders_widget = PlaceholdersWidget(placeholders_panel)
        build_status_btn = AYButton(
            "",
            parent=placeholders_panel,
            variant=AYButton.Variants.Text,
            icon="description",
        )
        build_status_btn.setVisible(False)
        build_progress_bar = QtWidgets.QProgressBar(placeholders_panel)
        build_progress_bar.setRange(0, 0)
        build_progress_bar.setTextVisible(False)
        build_progress_bar.setFixedHeight(3)
        build_progress_bar.setVisible(False)
        placeholders_panel.add_widget(placeholders_widget, stretch=1)
        placeholders_panel.layout().addWidget(
            build_status_btn, 0, QtCore.Qt.AlignLeft
        )
        placeholders_panel.layout().addWidget(build_progress_bar)

        # --- Editor panel ---
        editor_panel = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_margin=PANEL_MARGIN,
        )
        pages_widget = QtWidgets.QStackedWidget(editor_panel)
        pages_widget.setObjectName(PAGES_OBJECT_NAME)
        hint_widget = PlaceholderGuideWidget(pages_widget)
        hint_widget.set_add_target(placeholders_widget._create_btn)
        editor_widget = PlaceholderEditorWidget(controller, pages_widget)
        # The guide has no left margin, so its arrow gets closer to the
        #   "Add" button. The editor keeps the margin of the panel.
        editor_panel.layout().setContentsMargins(
            0, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN
        )
        editor_widget.setContentsMargins(PANEL_MARGIN, 0, 0, 0)
        pages_widget.addWidget(hint_widget)
        pages_widget.addWidget(editor_widget)
        editor_panel.add_widget(pages_widget, stretch=1)

        # Preview is its own third pane so options and result can be read
        #   side by side instead of scrolling past the preview.
        preview_widget = editor_widget.preview_widget
        preview_widget.setContentsMargins(
            PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN, PANEL_MARGIN
        )
        preview_widget.setVisible(False)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.setObjectName(SPLITTER_OBJECT_NAME)
        splitter.setHandleWidth(SPLITTER_HANDLE_WIDTH)
        splitter.setChildrenCollapsible(False)
        splitter.addWidget(placeholders_panel)
        splitter.addWidget(editor_panel)
        splitter.addWidget(preview_widget)
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        splitter.setStretchFactor(2, 0)
        splitter.setSizes([400, 600, 300])

        self.add_widget(context_bar)
        self.add_widget(divider_widget)
        self.add_widget(splitter, stretch=1)

        context_bar.context_change_requested.connect(
            self._on_context_change_request
        )
        context_bar.context_reset_requested.connect(
            self._on_context_reset_request
        )
        context_bar.test_build_requested.connect(
            self._on_run_template_build_request
        )
        context_bar.open_template_requested.connect(
            self._on_open_template_request
        )
        context_bar.build_from_template_requested.connect(
            self._on_build_from_template_request
        )
        placeholders_widget.selection_changed.connect(
            self._on_selection_change
        )
        placeholders_widget.create_requested.connect(self._on_create_request)
        placeholders_widget.select_in_scene_requested.connect(
            self._on_select_in_scene_request
        )
        placeholders_widget.run_requested.connect(self._on_run_request)
        placeholders_widget.delete_requested.connect(self._on_remove_request)
        placeholders_widget.refresh_requested.connect(self._on_refresh_request)
        pages_widget.currentChanged.connect(self._update_add_highlight)
        pages_widget.currentChanged.connect(self._update_preview_pane)
        editor_widget.create_requested.connect(self._on_create_confirmed)
        editor_widget.save_requested.connect(self._on_save_confirmed)
        editor_widget.cancel_requested.connect(self._on_create_cancelled)
        editor_widget.run_requested.connect(self._on_run_request)
        editor_widget.remove_requested.connect(self._on_remove_request)
        editor_widget.select_in_scene_requested.connect(
            self._on_select_in_scene_request
        )
        editor_widget.unsaved_changes_changed.connect(
            self._on_unsaved_changes_change
        )
        build_status_btn.clicked.connect(self._on_show_build_report)

        self._event_callbacks = [
            controller.register_event_callback(
                PLACEHOLDERS_REFRESHED_TOPIC,
                self._on_placeholders_refreshed,
            ),
            controller.register_event_callback(
                BUILD_CONTEXT_CHANGED_TOPIC,
                self._on_build_context_changed,
            ),
        ]

        self._controller = controller
        self._context_bar = context_bar
        self._placeholders_widget = placeholders_widget
        self._pages_widget = pages_widget
        self._hint_widget = hint_widget
        self._editor_widget = editor_widget
        self._preview_widget = preview_widget
        self._splitter = splitter
        self._build_status_btn = build_status_btn
        self._build_progress_bar = build_progress_bar

        self._first_show = True
        self._ignore_selection_change = False
        self._current_identifier: Optional[str] = None
        self._plugin_items: list[PlaceholderPluginItem] = []
        self._placeholder_items_by_id: dict[str, PlaceholderItemInfo] = {}
        self._hint_notice: Optional[str] = None
        self._busy = False
        self._busy_previous_status = ("", False)

        self._setup_shortcuts()
        self._setup_tab_order()
        self._editor_widget._confirm_btn.setAutoDefault(True)
        self._editor_widget._confirm_btn.setDefault(True)
        self._update_build_state()
        self._update_build_context()
        self._update_preview_pane()
        self.resize(1250, 720)

    def _setup_shortcuts(self):
        save_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence.Save, self
        )
        save_shortcut.activated.connect(self._on_save_shortcut)
        refresh_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence.Refresh, self
        )
        refresh_shortcut.activated.connect(self._on_refresh_request)
        escape_shortcut = QtWidgets.QShortcut(
            QtGui.QKeySequence(QtCore.Qt.Key_Escape), self
        )
        escape_shortcut.activated.connect(self._on_escape)
        # Keep a reference so the shortcuts are not garbage collected.
        self._shortcuts = [
            save_shortcut,
            refresh_shortcut,
            escape_shortcut,
        ]

    def _setup_tab_order(self):
        QtWidgets.QWidget.setTabOrder(
            self._placeholders_widget._filter_input,
            self._placeholders_widget._view,
        )
        QtWidgets.QWidget.setTabOrder(
            self._placeholders_widget._view,
            self._editor_widget._confirm_btn,
        )

    # --- Qt overrides -------------------------------------------------
    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(
                style.load_stylesheet() + _get_window_stylesheet()
            )
            self._refresh_guarded()
        elif (
            not self._editor_widget.has_unsaved_changes()
            and not self._busy
        ):
            # Re-showing a hidden window must not show stale scene data.
            self._refresh_guarded()

    def closeEvent(self, event):
        if not self._confirm_discard_changes():
            event.ignore()
            return

        self._editor_widget.stop_dynamic_timer()
        for callback in self._event_callbacks:
            deregister = getattr(callback, "deregister", None)
            if deregister is not None:
                deregister()
        self._controller.close()
        super().closeEvent(event)

    def hideEvent(self, event):
        # Do not keep a preview/completion timer running while hidden.
        self._editor_widget.stop_dynamic_timer()
        super().hideEvent(event)

    # --- Public API ---------------------------------------------------
    def refresh(self):
        """Collect placeholders from the scene and update the UI."""
        self._controller.reset()

    def select_placeholder(self, scene_identifier: str) -> bool:
        """Select a placeholder and show its options.

        Hosts can use it to show the placeholder that is selected in the
        scene when the tool is opened.

        Args:
            scene_identifier (str): Scene identifier of the placeholder.

        Returns:
            bool: Placeholder was found and selected.

        """
        if scene_identifier not in self._placeholder_items_by_id:
            return False
        self._placeholders_widget.select_identifier(scene_identifier)
        return self._current_identifier == scene_identifier

    # --- Implementation -----------------------------------------------
    def _on_placeholders_refreshed(self):
        try:
            self._context_bar.set_workfile(
                self._controller.get_workfile_name(),
                self._controller.get_host_name(),
            )
            self._update_template_path()
            self._update_placeholders()
        except Exception:
            self._show_unexpected_error(
                "Failed to update the placeholder list"
            )

    def _on_build_context_changed(self):
        try:
            self._update_build_context()
            if self._pages_widget.currentIndex() == EDITOR_PAGE:
                self._editor_widget.refresh_preview()
        except Exception:
            self._show_unexpected_error("Failed to update the build context")

    def _update_build_context(self):
        context_item = self._controller.get_build_context()
        self._context_bar.set_build_context(context_item)
        self._context_bar.set_context_enabled(
            self._controller.is_builder_available()
        )
        self._editor_widget.set_build_context_label(context_item.label)
        self._update_template_path()

    def _update_template_path(self):
        self._context_bar.set_template_path(
            self._controller.get_template_path()
        )

    def _update_placeholders(self):
        try:
            self._update_placeholders_impl()
        except Exception:
            self._show_unexpected_error("Failed to update placeholders")

    def _update_placeholders_impl(self):
        self._plugin_items = self._controller.get_placeholder_plugin_items()
        placeholder_items = self._controller.get_placeholder_items()
        self._placeholder_items_by_id = {
            item.scene_identifier: item for item in placeholder_items
        }
        self._update_build_state()

        self._ignore_selection_change = True
        self._placeholders_widget.set_plugin_items(self._plugin_items)
        self._placeholders_widget.set_placeholder_items(placeholder_items)
        self._placeholders_widget.set_error(
            self._controller.get_placeholders_error()
        )
        self._placeholders_widget.select_identifier(self._current_identifier)
        self._ignore_selection_change = False

        # Placeholder that was edited may be gone from the scene
        if self._current_identifier not in self._placeholder_items_by_id:
            self._current_identifier = None

        if self._pages_widget.currentIndex() == EDITOR_PAGE:
            editor_identifier = self._editor_widget.get_scene_identifier()
            if (
                editor_identifier is not None
                and editor_identifier not in self._placeholder_items_by_id
            ):
                self._hint_notice = (
                    "The placeholder that was being edited is no longer in"
                    " the scene. It may have been removed outside of the"
                    " tool."
                )
                if self._editor_widget.has_unsaved_changes():
                    # Keep the form so unsaved values are not lost.
                    return
                self._show_hint_page()
                return
            self._hint_notice = None
            if (
                editor_identifier is not None
                and not self._editor_widget.has_unsaved_changes()
            ):
                # Rebuild the editor from the refreshed scene data, so
                #   changes made outside the tool are visible.
                self._show_editor_page(editor_identifier)

        if self._pages_widget.currentIndex() == HINT_PAGE:
            self._update_hint_message()

    def _update_build_state(self):
        """Enable building only when the host supports it and there is
        something to build."""
        builder_available = self._controller.is_builder_available()
        has_placeholders = bool(self._placeholder_items_by_id)
        supports_run = any(
            plugin_item.run_supported for plugin_item in self._plugin_items
        )
        enabled = has_placeholders and builder_available and supports_run
        reason = None
        if not builder_available:
            reason = "Template build is not available in this host."
        elif not has_placeholders:
            reason = (
                "No placeholders in the current scene. Add a placeholder"
                " first."
            )
        elif not supports_run:
            reason = (
                "No placeholder type in this host supports re-running"
                " placeholders."
            )
        self._context_bar.set_test_build_enabled(enabled, reason)

    def _update_hint_message(self):
        if not self._controller.is_builder_available():
            self._hint_widget.set_unavailable(
                "Template build is not available",
                (
                    "Host \"{}\" does not implement workfile template"
                    " build.".format(self._controller.get_host_name())
                ),
            )
            return

        placeholders_error = self._controller.get_placeholders_error()
        if placeholders_error:
            self._hint_widget.set_unavailable(
                "Could not read placeholders",
                placeholders_error,
            )
            return

        if self._hint_notice:
            self._hint_widget.set_unavailable(
                "Placeholder no longer exists",
                self._hint_notice,
            )
            return

        if not self._plugin_items:
            self._hint_widget.set_unavailable(
                "No placeholder types available",
                (
                    "Host \"{}\" does not have any placeholder plugins"
                    " registered.".format(self._controller.get_host_name())
                ),
            )
            return

        self._hint_widget.set_guide(bool(self._placeholder_items_by_id))
        self._update_add_highlight()

    def _update_add_highlight(self):
        """Highlight "Add" while the guide points at it."""
        self._placeholders_widget.set_add_highlighted(
            self._pages_widget.currentIndex() == HINT_PAGE
            and not self._placeholder_items_by_id
        )

    def _update_preview_pane(self, _index=None):
        """Show the preview pane only while editing a placeholder."""
        is_editor = self._pages_widget.currentIndex() == EDITOR_PAGE
        self._preview_widget.setVisible(is_editor)
        if not is_editor:
            return

        sizes = self._splitter.sizes()
        if len(sizes) != 3 or sizes[2] < 100:
            self._splitter.setSizes([400, 500, 300])

    def _show_hint_page(self):
        self._current_identifier = None
        self._set_pending_item(None)
        self._update_hint_message()
        self._pages_widget.setCurrentIndex(HINT_PAGE)

    def _get_plugin_item(
        self, plugin_identifier: Optional[str]
    ) -> Optional[PlaceholderPluginItem]:
        for plugin_item in self._plugin_items:
            if plugin_item.identifier == plugin_identifier:
                return plugin_item
        return None

    def _show_editor_page(self, scene_identifier):
        placeholder_item = self._placeholder_items_by_id.get(scene_identifier)
        if placeholder_item is None:
            self._show_hint_page()
            return

        plugin_item = self._get_plugin_item(placeholder_item.plugin_identifier)
        focus_widget = QtWidgets.QApplication.focusWidget()
        restore_focus = (
            focus_widget is not None
            and self._editor_widget.isAncestorOf(focus_widget)
        )
        self._hint_notice = None
        self._current_identifier = scene_identifier
        self._set_pending_item(None)
        self._editor_widget.set_edit_mode(
            placeholder_item,
            select_supported=(
                plugin_item is not None and plugin_item.select_supported
            ),
        )
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)
        if restore_focus:
            self._editor_widget.focus_first_option()

    def _show_create_page(self, plugin_item: PlaceholderPluginItem):
        self._hint_notice = None
        self._current_identifier = None
        self._set_pending_item(plugin_item)
        self._editor_widget.set_create_mode(plugin_item)
        self._pages_widget.setCurrentIndex(EDITOR_PAGE)

    def _set_pending_item(
        self, plugin_item: Optional[PlaceholderPluginItem]
    ) -> None:
        """Show the placeholder that is being created in the list."""
        self._ignore_selection_change = True
        self._placeholders_widget.set_pending_item(plugin_item)
        self._ignore_selection_change = False

    def _select_silently(self, scene_identifier):
        self._ignore_selection_change = True
        self._placeholders_widget.select_identifier(scene_identifier)
        self._ignore_selection_change = False

    def _confirm_discard_changes(self):
        """Ask the user before losing changed options.

        Returns:
            bool: Changes can be discarded.

        """
        if self._pages_widget.currentIndex() != EDITOR_PAGE:
            return True
        if not self._editor_widget.has_unsaved_changes():
            return True

        if self._editor_widget.is_create_mode():
            title = "Discard new placeholder?"
            message = (
                "The new placeholder has options filled in but is not"
                " created yet.\nDo you want to discard it?"
            )
        else:
            title = "Discard changes?"
            message = (
                "Placeholder options were changed and are not saved."
                "\nDo you want to discard the changes?"
            )

        answer = QtWidgets.QMessageBox.question(
            self,
            title,
            message,
            QtWidgets.QMessageBox.Discard | QtWidgets.QMessageBox.Cancel,
            QtWidgets.QMessageBox.Cancel,
        )
        return answer == QtWidgets.QMessageBox.Discard

    def _show_action_error(self, result: ActionResult) -> bool:
        """Show a message box when an action failed.

        Args:
            result (ActionResult): Result of the action.

        Returns:
            bool: Action failed.

        """
        if result.success:
            return False

        dialog = QtWidgets.QMessageBox(self)
        dialog.setWindowTitle("Workfile Template Builder")
        dialog.setIcon(QtWidgets.QMessageBox.Warning)
        dialog.setText(result.error_title or "Action failed")
        if result.error_detail:
            dialog.setDetailedText(result.error_detail)
        dialog.exec_()
        return True

    def _show_unexpected_error(self, title: str) -> None:
        """Show an error that happened outside an action result."""
        self._show_action_error(ActionResult(
            success=False,
            error_title=title,
            error_detail=traceback.format_exc(),
        ))

    def _refresh_guarded(self) -> None:
        try:
            self.refresh()
        except Exception:
            self._show_unexpected_error("Failed to refresh the placeholders")

    def _set_busy(self, busy: bool, message: Optional[str] = None) -> None:
        """Disable actions while a host operation is running."""
        self._busy = busy
        self._context_bar.setEnabled(not busy)
        self._placeholders_widget.setEnabled(not busy)
        if busy:
            self._busy_previous_status = (
                self._build_status_btn.text(),
                self._build_status_btn.isVisible(),
            )
            self._editor_widget.stop_dynamic_timer()
            self._build_status_btn.setText(message or "Working...")
            self._build_status_btn.setVisible(True)
            self._build_progress_bar.setVisible(True)
        else:
            self._build_progress_bar.setVisible(False)
            text, visible = self._busy_previous_status
            self._build_status_btn.setText(text)
            self._build_status_btn.setVisible(visible)
            self._update_build_state()

    def _set_status_text(self, text: str) -> None:
        self._build_status_btn.setText(text)
        self._build_status_btn.setVisible(bool(text))

    def _on_build_progress(self, count: int, event_data: dict) -> None:
        """Show progress between populated placeholders."""
        self._build_status_btn.setText(
            "Test building... {} placeholder(s)".format(count)
        )
        # Let the status paint while the host operation keeps running.
        QtWidgets.QApplication.processEvents(
            QtCore.QEventLoop.ExcludeUserInputEvents
        )

    def _on_save_shortcut(self) -> None:
        if self._busy:
            return
        if self._pages_widget.currentIndex() == EDITOR_PAGE:
            self._editor_widget.save()

    def _on_escape(self) -> None:
        if self._busy:
            return
        if self._pages_widget.currentIndex() != EDITOR_PAGE:
            self.close()
            return

        if self._editor_widget.is_create_mode():
            self._on_create_cancelled()
        elif self._editor_widget.has_unsaved_changes():
            self._editor_widget.revert_to_original()
        else:
            self.close()
