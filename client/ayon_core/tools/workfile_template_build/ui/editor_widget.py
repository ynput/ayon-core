"""Editor of placeholder options with a live preview of the outcome."""

from __future__ import annotations

import copy
from typing import Any, Optional

from qtpy import QtCore, QtWidgets

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsWidget
from ayon_core.ui.components import AYButton, AYContainer, AYLabel
from ayon_core.ui.components.scroll_area import AYScrollArea

from ..abstract import (
    PlaceholderDynamicData,
    PlaceholderItemInfo,
    PlaceholderOptionsError,
    PlaceholderPluginItem,
)
from ..control import WorkfileTemplateBuilderController
from .options_polish import _polish_options
from .placeholder_header import PlaceholderHeaderWidget
from .placeholder_icons import (
    CREATE_ICON,
    DELETE_ICON,
    RUN_ICON,
    SELECT_ICON,
    get_placeholder_icon,
)
from .preview_widget import PreviewWidget
from .preview_worker import PreviewWorker, create_preview_worker
from .utils import get_warning_color

# Delay between last change of an option and re-calculation of preview and
#   completions. Both may query the AYON server so they are not calculated
#   on every keystroke.
DYNAMIC_UPDATE_DELAY_MS = 400

# Object names used by the window stylesheet
OPTIONS_SCROLL_OBJECT_NAME = "PlaceholderOptionsScroll"
OPTIONS_CONTENT_OBJECT_NAME = "PlaceholderOptionsContent"

CREATE_MODE = "create"
EDIT_MODE = "edit"


class PlaceholderEditorWidget(AYContainer):
    """Editor of placeholder options.

    Used both to create a new placeholder and to change an existing one.

    Signals:
        create_requested: Create placeholder of plugin identifier (str) with
            options (dict).
        save_requested: Save options (dict) to placeholder scene identifier
            (str).
        cancel_requested: Leave create mode without creating anything.
        run_requested: Run placeholder with the scene identifier (str).
        remove_requested: Remove placeholder with the scene identifier (str).
        select_in_scene_requested: Select the placeholder with the scene
            identifier (str) in the host scene.
        unsaved_changes_changed: Edited placeholder got or lost unsaved
            changes (bool).

    """
    create_requested = QtCore.Signal(str, object)
    save_requested = QtCore.Signal(str, object)
    cancel_requested = QtCore.Signal()
    run_requested = QtCore.Signal(str)
    remove_requested = QtCore.Signal(str)
    select_in_scene_requested = QtCore.Signal(str)
    unsaved_changes_changed = QtCore.Signal(bool)

    def __init__(
        self,
        controller: WorkfileTemplateBuilderController,
        parent: Optional[QtWidgets.QWidget] = None,
    ):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            layout_spacing=10,
        )

        self._controller = controller

        # --- Header ---
        header_widget = PlaceholderHeaderWidget(self)
        actions_widget = header_widget.get_actions_widget()
        # Actions of the placeholder sit next to its name, so they don't read
        #   as actions of the whole template.
        select_btn = AYButton(
            "Select in scene",
            parent=actions_widget,
            variant=AYButton.Variants.Surface,
            icon=SELECT_ICON,
        )
        run_btn = AYButton(
            "Populate this placeholder",
            parent=actions_widget,
            variant=AYButton.Variants.Surface,
            icon=RUN_ICON,
        )
        # Icon only, kept apart from the other actions so it is not
        #   clicked by accident.
        remove_btn = AYButton(
            parent=actions_widget,
            variant=AYButton.Variants.Surface,
            icon=DELETE_ICON,
        )
        actions_widget.add_widget(select_btn)
        actions_widget.add_widget(run_btn)
        actions_widget.addStretch(1)
        actions_widget.layout().addSpacing(6)
        actions_widget.add_widget(remove_btn)

        # --- Options ---
        attrs_scroll = AYScrollArea(self)
        attrs_scroll.setObjectName(OPTIONS_SCROLL_OBJECT_NAME)
        attrs_scroll.setWidgetResizable(True)
        attrs_scroll.setHorizontalScrollBarPolicy(
            QtCore.Qt.ScrollBarAlwaysOff
        )

        attrs_wrapper = QtWidgets.QWidget(attrs_scroll)
        attrs_wrapper.setObjectName(OPTIONS_CONTENT_OBJECT_NAME)
        attrs_wrapper_layout = QtWidgets.QVBoxLayout(attrs_wrapper)
        attrs_wrapper_layout.setContentsMargins(0, 0, 8, 0)
        attrs_wrapper_layout.addStretch(1)
        attrs_scroll.setWidget(attrs_wrapper)

        # Error shown in the options area when the options cannot be loaded
        options_error_widget = AYContainer(
            attrs_wrapper,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=8,
        )
        options_error_icon = AYLabel(
            parent=options_error_widget,
            icon="warning",
            icon_color=get_warning_color(),
            icon_size=16,
        )
        options_error_label = AYLabel(
            parent=options_error_widget,
            flexible=True,
        )
        options_error_label.setWordWrap(True)
        options_retry_btn = AYButton(
            "Retry",
            parent=options_error_widget,
            variant=AYButton.Variants.Surface,
            icon="refresh",
        )
        options_error_widget.add_widget(options_error_icon)
        options_error_widget.add_widget(options_error_label, stretch=1)
        options_error_widget.add_widget(options_retry_btn)
        options_error_widget.setVisible(False)
        attrs_wrapper_layout.insertWidget(0, options_error_widget, 0)

        # --- Preview ---
        preview_widget = PreviewWidget(self)

        # --- Footer ---
        btns_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        unsaved_label = AYLabel(
            "Unsaved changes",
            parent=btns_widget,
            icon="circle",
            icon_fill=True,
            icon_size=10,
            icon_color=get_warning_color(),
            text_color=get_warning_color(),
        )
        unsaved_label.setVisible(False)
        cancel_btn = AYButton(
            "Cancel",
            parent=btns_widget,
            variant=AYButton.Variants.Surface,
            icon="close",
        )
        confirm_btn = AYButton(
            "Create placeholder",
            parent=btns_widget,
            variant=AYButton.Variants.Filled,
            icon=CREATE_ICON,
        )
        btns_widget.add_widget(unsaved_label)
        btns_widget.addStretch(1)
        btns_widget.add_widget(cancel_btn)
        btns_widget.add_widget(confirm_btn)

        self.add_widget(header_widget)
        self.add_widget(attrs_scroll, stretch=1)
        self.add_widget(btns_widget)

        dynamic_timer = QtCore.QTimer(self)
        dynamic_timer.setInterval(DYNAMIC_UPDATE_DELAY_MS)
        dynamic_timer.setSingleShot(True)

        dynamic_timer.timeout.connect(self._on_dynamic_timer)
        select_btn.clicked.connect(self._on_select_click)
        confirm_btn.clicked.connect(self._on_confirm_click)
        cancel_btn.clicked.connect(self._on_cancel_click)
        run_btn.clicked.connect(self._on_run_click)
        remove_btn.clicked.connect(self._on_remove_click)
        options_retry_btn.clicked.connect(self._on_options_retry)

        self._header_widget = header_widget
        self._select_btn = select_btn
        self._attrs_scroll = attrs_scroll
        self._attrs_wrapper = attrs_wrapper
        self._attrs_wrapper_layout = attrs_wrapper_layout
        self._preview_widget = preview_widget
        self._confirm_btn = confirm_btn
        self._cancel_btn = cancel_btn
        self._unsaved_label = unsaved_label
        self._run_btn = run_btn
        self._remove_btn = remove_btn
        self._dynamic_timer = dynamic_timer
        self._options_error_widget = options_error_widget
        self._options_error_label = options_error_label

        self._mode = CREATE_MODE
        self._plugin_identifier: Optional[str] = None
        self._scene_identifier: Optional[str] = None
        self._attrs_widget: Optional[AttributeDefinitionsWidget] = None
        self._original_values: dict[str, Any] = {}
        self._default_values: dict[str, Any] = {}
        self._last_dynamic_values: Optional[dict[str, Any]] = None
        self._had_unsaved_changes = False
        self._options_source_data: Optional[dict[str, Any]] = None

        # Preview/completions run in a worker; generation drops stale
        #   results when the options change again while a query is running.
        self._preview_generation = 0
        self._preview_worker: Optional[PreviewWorker] = None
        self._pending_dynamic_request = None
        self._last_good_preview: Optional[PlaceholderPreview] = None
        self._preview_thread_pool = QtCore.QThreadPool.globalInstance()

    # --- Public API ---------------------------------------------------
    def set_create_mode(self, plugin_item: PlaceholderPluginItem) -> None:
        """Show options of a placeholder that is not created yet.

        Args:
            plugin_item (PlaceholderPluginItem): Plugin used to create the
                placeholder.

        """
        self._mode = CREATE_MODE
        self._scene_identifier = None

        self._set_header(
            plugin_item.icon,
            "New placeholder",
            "{} - fill in the options and create it in the scene".format(
                plugin_item.label
            ),
        )
        self._header_widget.set_actions_visible(False)
        self._confirm_btn.setText("Create placeholder")
        self._confirm_btn.set_icon(CREATE_ICON)
        self._cancel_btn.setText("Cancel")
        self._cancel_btn.set_icon("close")

        self._set_plugin(plugin_item.identifier, None)

    def set_edit_mode(
        self,
        placeholder_item: PlaceholderItemInfo,
        select_supported: bool = False,
    ) -> None:
        """Show options of an existing placeholder.

        Args:
            placeholder_item (PlaceholderItemInfo): Placeholder to edit.
            select_supported (bool): Placeholder can be selected in the
                host scene.

        """
        self._mode = EDIT_MODE
        self._scene_identifier = placeholder_item.scene_identifier

        # Show the scene identifier only when the label does not already
        #   show it, which is the default label of a placeholder.
        subtitle = placeholder_item.plugin_label
        if placeholder_item.label != placeholder_item.scene_identifier:
            subtitle = "{} - {}".format(
                subtitle, placeholder_item.scene_identifier
            )
        self._set_header(
            placeholder_item.icon, placeholder_item.label, subtitle
        )
        self._confirm_btn.setText("Save changes")
        self._confirm_btn.set_icon("save")
        self._cancel_btn.setText("Discard changes")
        self._cancel_btn.set_icon("undo")
        self._set_placeholder_action_state(placeholder_item, select_supported)

        self._set_plugin(
            placeholder_item.plugin_identifier,
            copy.deepcopy(placeholder_item.data),
        )

    def set_build_context_label(self, label: str) -> None:
        """Show the context the preview is calculated for.

        Args:
            label (str): Label of the context.

        """
        self._preview_widget.set_context_label(label)

    def refresh_preview(self) -> None:
        """Calculate preview and completions again.

        Used when something else than the options changed, e.g. the context
        the preview is calculated for.
        """
        self._last_dynamic_values = None
        self._request_dynamic_update()

    def stop_dynamic_timer(self) -> None:
        """Stop pending and in-flight preview/completions calculations."""
        self._dynamic_timer.stop()
        self._invalidate_dynamic_request()

    def is_create_mode(self) -> bool:
        """The editor shows a placeholder that is not created yet."""
        return self._mode == CREATE_MODE

    @property
    def preview_widget(self) -> PreviewWidget:
        """Preview panel shown next to the editor."""
        return self._preview_widget

    def revert_to_original(self) -> None:
        """Restore the values the editor was opened with."""
        if self._attrs_widget is None:
            return
        if self._mode == CREATE_MODE:
            values = self._default_values
        else:
            values = self._original_values
        self._attrs_widget.set_value(copy.deepcopy(values))
        self._last_dynamic_values = None
        self._update_confirm_state()
        self._request_dynamic_update()

    def has_unsaved_changes(self) -> bool:
        """Options were changed since they were last stored.

        Returns:
            bool: There are changes that would be lost.

        """
        if self._attrs_widget is None:
            return False
        values = self._attrs_widget.current_value()
        if self._mode == CREATE_MODE:
            return values != self._default_values
        return values != self._original_values

    def save(self) -> None:
        """Save or create the placeholder if that is possible now."""
        if self._confirm_btn.isEnabled():
            self._on_confirm_click()

    def save_changes(self) -> bool:
        """Apply pending editor changes before an action such as a test build.

        Returns:
            bool: True when there are no unsaved changes left.
        """
        if not self.has_unsaved_changes():
            return True
        self.save()
        return not self.has_unsaved_changes()

    def focus_first_option(self) -> None:
        """Focus the first editable option input."""
        if self._attrs_widget is None:
            return
        input_types = (
            QtWidgets.QLineEdit,
            QtWidgets.QComboBox,
            QtWidgets.QAbstractSpinBox,
            QtWidgets.QPlainTextEdit,
            QtWidgets.QTextEdit,
        )
        for widget in self._attrs_widget.findChildren(QtWidgets.QWidget):
            if (
                isinstance(widget, input_types)
                and widget.isVisible()
                and widget.isEnabled()
            ):
                widget.setFocus()
                return

    def get_scene_identifier(self) -> Optional[str]:
        """Scene identifier of the edited placeholder.

        Returns:
            Optional[str]: Scene identifier, None in create mode.

        """
        return self._scene_identifier

    # --- Implementation -----------------------------------------------
    def _set_header(
        self,
        icon_def: Optional[dict[str, Any]],
        title: str,
        subtitle: str,
    ) -> None:
        self._header_widget.set_header(
            get_placeholder_icon(icon_def), title, subtitle
        )

    def _set_placeholder_action_state(
        self,
        placeholder_item: PlaceholderItemInfo,
        select_supported: bool,
    ) -> None:
        """Show the placeholder actions its plugin supports.

        Args:
            placeholder_item (PlaceholderItemInfo): The edited placeholder.
            select_supported (bool): Placeholder can be selected in the
                host scene.

        """
        self._header_widget.set_actions_visible(True)
        self._select_btn.setEnabled(select_supported)
        self._select_btn.setToolTip(
            "Select placeholder in the scene"
            if select_supported
            else (
                "Selecting placeholders in the scene is not implemented"
                " for this placeholder type."
            )
        )

        self._run_btn.setEnabled(placeholder_item.run_supported)
        self._run_btn.setToolTip(
            (
                "Populate only this placeholder in the open scene for the"
                " test context. Use \"Test build\" to populate"
                " all of them."
            )
            if placeholder_item.run_supported
            else (
                "Running a single placeholder is not implemented for"
                " this placeholder type."
            )
        )

        self._remove_btn.setEnabled(placeholder_item.delete_supported)
        self._remove_btn.setToolTip(
            "Remove placeholder from the scene"
            if placeholder_item.delete_supported
            else (
                "Removing placeholders is not implemented for this"
                " placeholder type."
            )
        )

    def _set_plugin(
        self,
        plugin_identifier: str,
        placeholder_data: Optional[dict[str, Any]],
    ) -> None:
        """Build option widgets for a plugin.

        Args:
            plugin_identifier (str): Plugin to show options of.
            placeholder_data (Optional[dict[str, Any]]): Values to fill in.

        """
        self._plugin_identifier = plugin_identifier
        self._options_source_data = copy.deepcopy(placeholder_data)
        self._remove_attrs_widget()

        self._preview_widget.set_preview(None)
        self._last_dynamic_values = None
        self._last_good_preview = None
        self._dynamic_timer.stop()
        self._invalidate_dynamic_request()

        try:
            attr_defs = self._controller.get_placeholder_options(
                plugin_identifier, placeholder_data
            )
        except PlaceholderOptionsError as exc:
            self._show_options_error(str(exc))
            return

        self._hide_options_error()
        attrs_widget = AttributeDefinitionsWidget(
            attr_defs, self._attrs_wrapper
        )
        if placeholder_data:
            attrs_widget.set_value(placeholder_data)
        attrs_widget.value_changed.connect(self._on_value_change)
        _polish_options(attrs_widget)

        # Keep the stretch at the end of the layout
        self._attrs_wrapper_layout.insertWidget(0, attrs_widget, 0)

        self._attrs_widget = attrs_widget
        current_values = attrs_widget.current_value()
        if self._mode == CREATE_MODE:
            self._default_values = copy.deepcopy(current_values)
        else:
            self._original_values = current_values

        self._update_confirm_state()
        self._request_dynamic_update()

    def _show_options_error(self, message: str) -> None:
        """Show why the options of a plugin could not be loaded."""
        self._options_error_label.setText(
            "Could not load placeholder options.\n{}".format(message)
        )
        self._options_error_widget.setVisible(True)
        self._preview_widget.set_preview(None)
        self._update_confirm_state()

    def _hide_options_error(self) -> None:
        self._options_error_widget.setVisible(False)

    def _on_options_retry(self) -> None:
        """Try to load the options again."""
        if self._plugin_identifier is None:
            return
        self._set_plugin(
            self._plugin_identifier, self._options_source_data
        )

    def _remove_attrs_widget(self) -> None:
        self._hide_options_error()
        if self._attrs_widget is None:
            return
        self._attrs_wrapper_layout.removeWidget(self._attrs_widget)
        self._attrs_widget.setVisible(False)
        self._attrs_widget.deleteLater()
        self._attrs_widget = None
        self._original_values = {}

    def _update_confirm_state(self) -> None:
        has_changes = self.has_unsaved_changes()
        self._unsaved_label.setVisible(has_changes)
        if has_changes != self._had_unsaved_changes:
            self._had_unsaved_changes = has_changes
            self.unsaved_changes_changed.emit(has_changes)

        if self._mode == CREATE_MODE:
            self._confirm_btn.setEnabled(self._attrs_widget is not None)
            self._cancel_btn.setEnabled(True)
            return

        self._confirm_btn.setEnabled(has_changes)
        self._cancel_btn.setEnabled(has_changes)

    def _invalidate_dynamic_request(self) -> None:
        """Drop in-flight and queued preview results."""
        self._preview_generation += 1
        self._pending_dynamic_request = None

    def _request_dynamic_update(self) -> None:
        self._invalidate_dynamic_request()
        self._dynamic_timer.start()

    def _on_value_change(self, value=None, attr_id=None) -> None:
        self._update_confirm_state()
        self._request_dynamic_update()

    def _on_dynamic_timer(self) -> None:
        if self._attrs_widget is None or self._plugin_identifier is None:
            return

        values = self._attrs_widget.current_value()
        if values == self._last_dynamic_values:
            return
        self._last_dynamic_values = copy.deepcopy(values)

        self._preview_widget.set_calculating()
        if self._preview_worker is not None:
            # Keep only the newest request; starting it when the active
            #   query finishes avoids piling up slow server queries.
            self._pending_dynamic_request = (
                self._preview_generation,
                self._plugin_identifier,
                copy.deepcopy(values),
            )
            return

        self._start_dynamic_worker(
            self._preview_generation, self._plugin_identifier, values
        )

    def _start_dynamic_worker(
        self,
        generation: int,
        plugin_identifier: str,
        values: dict[str, Any],
    ) -> None:
        worker = create_preview_worker(
            self._controller, plugin_identifier, values, generation
        )
        worker.signals.finished.connect(self._on_dynamic_data)
        self._preview_worker = worker
        self._preview_thread_pool.start(worker)

    def _on_dynamic_data(self, generation: int, data) -> None:
        self._preview_worker = None

        if generation == self._preview_generation:
            self._apply_dynamic_data(data)

        pending = self._pending_dynamic_request
        self._pending_dynamic_request = None
        if pending is not None:
            pending_generation, plugin_identifier, values = pending
            self._start_dynamic_worker(
                pending_generation, plugin_identifier, values
            )

    def _apply_dynamic_data(self, data: PlaceholderDynamicData) -> None:
        if data is None:
            return

        if self._attrs_widget is not None:
            self._attrs_widget.set_completions(data.completions or {})

        preview = data.preview
        if data.completions_error is not None:
            # The preview is still useful; show it with a warning instead of
            #   hiding the completion failure.
            if preview is None:
                preview = copy.deepcopy(self._last_good_preview)
            if preview is None:
                preview = PlaceholderPreview(
                    title="Preview unavailable",
                    hint=data.completions_error,
                    is_error=True,
                )
            else:
                hint = preview.hint
                preview.hint = (
                    "{}\n\n{}".format(hint, data.completions_error)
                    if hint else data.completions_error
                )
                preview.is_error = True

        if preview is None:
            # Keep the last good preview instead of hiding the panel.
            preview = copy.deepcopy(self._last_good_preview)
        if preview is not None:
            if not preview.is_error:
                self._last_good_preview = copy.deepcopy(preview)
            self._preview_widget.set_preview(preview)
        else:
            self._preview_widget.set_preview(None)

    def _on_confirm_click(self) -> None:
        if self._attrs_widget is None or self._plugin_identifier is None:
            return

        values = self._attrs_widget.current_value()
        if self._mode == CREATE_MODE:
            self.create_requested.emit(self._plugin_identifier, values)
        elif self._scene_identifier is not None:
            self.save_requested.emit(self._scene_identifier, values)

    def _on_cancel_click(self) -> None:
        if self._mode == CREATE_MODE:
            self.cancel_requested.emit()
            return

        self.revert_to_original()

    def _on_select_click(self) -> None:
        if self._scene_identifier is not None:
            self.select_in_scene_requested.emit(self._scene_identifier)

    def _on_run_click(self) -> None:
        if self._scene_identifier is not None:
            self.run_requested.emit(self._scene_identifier)

    def _on_remove_click(self) -> None:
        if self._scene_identifier is not None:
            self.remove_requested.emit(self._scene_identifier)
