"""Editor of placeholder options with a live preview of the outcome."""

from __future__ import annotations

import copy
from typing import Any, Optional

from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.pipeline.workfile.workfile_template_builder import (
    PlaceholderPreview,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsWidget
from ayon_core.tools.attribute_defs.widgets import LabelAttrWidget
from ayon_core.ui.components import (
    AYButton,
    AYContainer,
    AYLabel,
    AYTreeView,
)
from ayon_core.ui.components.scroll_area import AYScrollArea

from ..abstract import (
    AbstractTemplateBuilderController,
    PlaceholderItemInfo,
    PlaceholderPluginItem,
)
from .placeholders_widget import (
    COLUMN_PADDING,
    CREATE_ICON,
    DELETE_ICON,
    RUN_ICON,
    SELECT_ICON,
    get_placeholder_icon,
)
from .utils import INPUT_COLOR, PANEL_COLOR, get_palette_color

# Delay between last change of an option and re-calculation of preview and
#   completions. Both may query the AYON server so they are not calculated
#   on every keystroke.
DYNAMIC_UPDATE_DELAY_MS = 400

# Maximum height of the preview entries view
MAX_PREVIEW_HEIGHT = 200

# Space between the icon, name and actions of the edited placeholder
HEADER_SPACING = 10

WARNING_COLOR = "#ffc671"

# Object names used by the window stylesheet
OPTIONS_SCROLL_OBJECT_NAME = "PlaceholderOptionsScroll"
OPTIONS_CONTENT_OBJECT_NAME = "PlaceholderOptionsContent"

CREATE_MODE = "create"
EDIT_MODE = "edit"


class _HintingFilter(QtCore.QObject):
    """Keep the default font hinting of a widget.

    The AYON style sets its font again whenever the widget is polished,
    so the hinting is set again after each font change.
    """

    @classmethod
    def install(cls, widget: QtWidgets.QWidget) -> None:
        """Use the default hinting for the widget font.

        Args:
            widget (QtWidgets.QWidget): Widget to change.

        """
        hinting_filter = cls(widget)
        widget.installEventFilter(hinting_filter)
        cls._set_hinting(widget)

    @staticmethod
    def _set_hinting(widget: QtWidgets.QWidget) -> None:
        hinting = QtGui.QFont.HintingPreference.PreferDefaultHinting
        font = widget.font()
        if font.hintingPreference() == hinting:
            return
        font = QtGui.QFont(font)
        font.setHintingPreference(hinting)
        widget.setFont(font)

    def eventFilter(self, obj, event):
        if event.type() in (
            QtCore.QEvent.Type.Polish,
            QtCore.QEvent.Type.FontChange,
        ):
            self._set_hinting(obj)
        return False


def _polish_options(attrs_widget: AttributeDefinitionsWidget) -> None:
    """Fix how option widgets look in the tool.

    - The AYON font disables hinting. Qt on Windows then renders bold rich
        text, like the bold section labels of the options, with the regular
        weight. Labels of the options use the default hinting instead.
    - Multiline text inputs paint their text on a viewport which the
        stylesheet of the window does not reach, so they would show no
        background at all. The viewport gets the color of the other inputs.

    Args:
        attrs_widget (AttributeDefinitionsWidget): Widget with the options.

    """
    for label_widget in attrs_widget.findChildren(LabelAttrWidget):
        for label in label_widget.findChildren(QtWidgets.QLabel):
            _HintingFilter.install(label)

    viewport_stylesheet = (
        "QWidget {{ background: {}; }}"
        " QWidget:disabled {{ background: {}; }}"
    ).format(
        get_palette_color(INPUT_COLOR), get_palette_color(PANEL_COLOR)
    )
    multiline_inputs = (
        attrs_widget.findChildren(QtWidgets.QPlainTextEdit)
        + attrs_widget.findChildren(QtWidgets.QTextEdit)
    )
    for input_widget in multiline_inputs:
        input_widget.viewport().setStyleSheet(viewport_stylesheet)


class PreviewWidget(AYContainer):
    """Shows what a placeholder would do when the template is built."""

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.VBox,
            variant=AYContainer.Variants.Low,
            layout_margin=10,
            layout_spacing=6,
        )

        title_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=8,
        )
        title_label = AYLabel("Preview", parent=title_widget, bold=True)
        context_label = AYLabel(
            parent=title_widget, dim=True, elide_mode=QtCore.Qt.ElideLeft
        )
        title_widget.add_widget(title_label)
        title_widget.add_widget(context_label, stretch=1)

        warning_label = AYLabel(
            parent=self,
            icon="warning",
            icon_color=WARNING_COLOR,
            icon_size=16,
        )
        hint_label = AYLabel(parent=self, dim=True, flexible=True)
        hint_label.setWordWrap(True)

        hint_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            variant=AYContainer.Variants.Low,
            layout_spacing=6,
        )
        hint_widget.add_widget(warning_label)
        hint_widget.add_widget(hint_label, stretch=1)

        items_model = QtGui.QStandardItemModel()
        items_model.setColumnCount(2)

        items_view = AYTreeView(self, variant=AYTreeView.Variants.Low)
        items_view.setModel(items_model)
        items_view.setHeaderHidden(True)
        items_view.setRootIsDecorated(False)
        items_view.setIndentation(0)
        items_view.setSelectionMode(QtWidgets.QAbstractItemView.NoSelection)
        items_view.setFocusPolicy(QtCore.Qt.NoFocus)
        header = items_view.header()
        header.setStretchLastSection(True)

        self.add_widget(title_widget)
        self.add_widget(hint_widget)
        self.add_widget(items_view, stretch=1)

        self._title_label = title_label
        self._context_label = context_label
        self._warning_label = warning_label
        self._hint_label = hint_label
        self._hint_widget = hint_widget
        self._items_model = items_model
        self._items_view = items_view

    def set_context_label(self, label: str) -> None:
        """Show the context the preview is calculated for.

        Args:
            label (str): Label of the context.

        """
        text = "for {}".format(label) if label else ""
        self._context_label.setText(text)
        self._context_label.setToolTip(text)

    def set_calculating(self) -> None:
        """Show that the preview is being re-calculated."""
        self._title_label.setText("Calculating preview...")
        self._set_hint(None, False)

    def set_preview(self, preview: Optional[PlaceholderPreview]) -> None:
        """Show result of a preview calculation.

        Args:
            preview (Optional[PlaceholderPreview]): Preview to show. Widget
                hides itself when None is passed.

        """
        if preview is None:
            self.setVisible(False)
            return

        self.setVisible(True)
        self._title_label.setText(preview.title or "Preview")
        self._set_hint(preview.hint, preview.is_error)

        root_item = self._items_model.invisibleRootItem()
        root_item.removeRows(0, root_item.rowCount())

        rows = [(item.label, item.detail or "") for item in preview.items]
        if preview.hidden_items_count:
            rows.append(
                ("... and {} more".format(preview.hidden_items_count), "")
            )

        for label, detail in rows:
            label_item = QtGui.QStandardItem(label)
            label_item.setToolTip(label)
            detail_item = QtGui.QStandardItem(detail)
            for item in (label_item, detail_item):
                item.setEditable(False)
            root_item.appendRow([label_item, detail_item])

        self._items_view.setVisible(bool(preview.items))
        # Keep the detail right next to the label so each row reads as one
        #   entry. Column size hints are not reliable while the view is not
        #   shown and don't count with padding of the item delegate.
        font_metrics = self._items_view.fontMetrics()
        label_width = max(
            (font_metrics.horizontalAdvance(label) for label, _ in rows),
            default=0,
        )
        self._items_view.header().resizeSection(
            0, label_width + (2 * COLUMN_PADDING)
        )
        self._update_items_view_height()

    def _update_items_view_height(self) -> None:
        """Keep the preview only as tall as the entries it shows."""
        rows = self._items_model.rowCount()
        if not rows:
            return

        row_height = self._items_view.sizeHintForRow(0)
        if row_height <= 0:
            row_height = 24
        frame = 2 * self._items_view.frameWidth()
        self._items_view.setFixedHeight(
            min(rows * row_height + frame + 4, MAX_PREVIEW_HEIGHT)
        )

    def _set_hint(self, hint: Optional[str], is_error: bool) -> None:
        self._hint_label.setText(hint or "")
        self._warning_label.setVisible(bool(hint) and is_error)
        self._hint_widget.setVisible(bool(hint))


class PlaceholderHeaderWidget(AYContainer):
    """Icon, name and actions of the edited placeholder.

    Actions are next to the name. They move to a row below the name when
    the name would not fit next to them.
    """

    def __init__(self, parent: Optional[QtWidgets.QWidget] = None):
        super().__init__(
            parent,
            layout=AYContainer.Layout.Grid,
            layout_spacing=HEADER_SPACING,
        )

        # Icon and title are separate labels, a label with both an icon
        #   and text may clip the last character of a bold text.
        icon_label = AYLabel(parent=self, icon="extension", icon_size=24)
        icon_label.set_icon(get_placeholder_icon(None))

        titles_widget = AYContainer(
            self,
            layout=AYContainer.Layout.VBox,
            layout_spacing=0,
        )
        title_label = AYLabel(
            parent=titles_widget,
            rel_text_size=3,
            bold=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        subtitle_label = AYLabel(
            parent=titles_widget,
            dim=True,
            elide_mode=QtCore.Qt.ElideRight,
        )
        titles_widget.add_widget(title_label)
        titles_widget.add_widget(subtitle_label)

        actions_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
        actions_widget.setVisible(False)

        layout = self.layout()
        layout.addWidget(icon_label, 0, 0, QtCore.Qt.AlignTop)
        layout.addWidget(titles_widget, 0, 1)
        layout.setColumnStretch(1, 1)

        self._icon_label = icon_label
        self._title_label = title_label
        self._subtitle_label = subtitle_label
        self._titles_widget = titles_widget
        self._actions_widget = actions_widget
        self._actions_below: Optional[bool] = None
        self._place_actions()

    def get_actions_widget(self) -> AYContainer:
        """Container of the placeholder action buttons.

        Returns:
            AYContainer: Container with horizontal layout.

        """
        return self._actions_widget

    def set_actions_visible(self, visible: bool) -> None:
        """Show the placeholder actions.

        Args:
            visible (bool): Actions are visible.

        """
        self._actions_widget.setVisible(visible)
        self._place_actions()

    def are_actions_below(self) -> bool:
        """Actions are on a row below the name.

        Returns:
            bool: Actions are below the name.

        """
        return bool(self._actions_below)

    def set_header(
        self, icon: Optional[QtGui.QIcon], title: str, subtitle: str
    ) -> None:
        """Show the placeholder.

        Args:
            icon (Optional[QtGui.QIcon]): Icon of the placeholder type.
            title (str): Name of the placeholder.
            subtitle (str): Text below the name.

        """
        if icon is not None:
            self._icon_label.set_icon(icon)
        self._title_label.setText(title)
        self._title_label.setToolTip(title)
        self._subtitle_label.setText(subtitle)
        self._subtitle_label.setToolTip(subtitle)
        self._place_actions()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._place_actions()

    def _get_titles_width(self) -> int:
        """Width the name and subtitle need to be shown in full."""
        return max(
            label.fontMetrics().horizontalAdvance(label.text())
            for label in (self._title_label, self._subtitle_label)
        )

    def _place_actions(self) -> None:
        """Put actions next to the name, or below it when it doesn't fit."""
        actions_below = False
        if self._actions_widget.isVisibleTo(self):
            needed_width = (
                self._icon_label.sizeHint().width()
                + self._get_titles_width()
                + self._actions_widget.sizeHint().width()
                + (2 * HEADER_SPACING)
            )
            actions_below = needed_width > self.width()

        if actions_below == self._actions_below:
            return
        self._actions_below = actions_below

        layout = self.layout()
        layout.removeWidget(self._actions_widget)
        if actions_below:
            layout.addWidget(self._actions_widget, 1, 1, 1, 2)
        else:
            layout.addWidget(
                self._actions_widget, 0, 2, QtCore.Qt.AlignVCenter
            )


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

    """
    create_requested = QtCore.Signal(str, object)
    save_requested = QtCore.Signal(str, object)
    cancel_requested = QtCore.Signal()
    run_requested = QtCore.Signal(str)
    remove_requested = QtCore.Signal(str)
    select_in_scene_requested = QtCore.Signal(str)

    def __init__(
        self,
        controller: AbstractTemplateBuilderController,
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
            "Test run",
            parent=actions_widget,
            variant=AYButton.Variants.Surface,
            icon=RUN_ICON,
        )
        remove_btn = AYButton(
            "Remove",
            parent=actions_widget,
            variant=AYButton.Variants.Surface,
            icon=DELETE_ICON,
        )
        actions_widget.add_widget(select_btn)
        actions_widget.add_widget(run_btn)
        actions_widget.addStretch(1)
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

        # --- Preview ---
        preview_widget = PreviewWidget(self)

        # --- Footer ---
        btns_widget = AYContainer(
            self,
            layout=AYContainer.Layout.HBox,
            layout_spacing=6,
        )
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
        btns_widget.addStretch(1)
        btns_widget.add_widget(cancel_btn)
        btns_widget.add_widget(confirm_btn)

        self.add_widget(header_widget)
        self.add_widget(attrs_scroll, stretch=1)
        self.add_widget(preview_widget)
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

        self._header_widget = header_widget
        self._select_btn = select_btn
        self._attrs_wrapper = attrs_wrapper
        self._attrs_wrapper_layout = attrs_wrapper_layout
        self._preview_widget = preview_widget
        self._confirm_btn = confirm_btn
        self._cancel_btn = cancel_btn
        self._run_btn = run_btn
        self._remove_btn = remove_btn
        self._dynamic_timer = dynamic_timer

        self._mode = CREATE_MODE
        self._plugin_identifier: Optional[str] = None
        self._scene_identifier: Optional[str] = None
        self._attrs_widget: Optional[AttributeDefinitionsWidget] = None
        self._original_values: dict[str, Any] = {}
        self._last_dynamic_values: Optional[dict[str, Any]] = None

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
        self._cancel_btn.setText("Revert")
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

    def has_unsaved_changes(self) -> bool:
        """Options were changed since they were last stored.

        Returns:
            bool: There are changes that would be lost.

        """
        if self._mode != EDIT_MODE or self._attrs_widget is None:
            return False
        return self._attrs_widget.current_value() != self._original_values

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
                "Populate only this placeholder in the scene for the"
                " \"Preview as\" context. Use \"Test build\" to populate"
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
        self._remove_attrs_widget()

        self._preview_widget.set_preview(None)
        self._last_dynamic_values = None
        self._dynamic_timer.stop()

        attr_defs = self._controller.get_placeholder_options(
            plugin_identifier, placeholder_data
        )
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
        self._original_values = attrs_widget.current_value()

        self._update_confirm_state()
        self._request_dynamic_update()

    def _remove_attrs_widget(self) -> None:
        if self._attrs_widget is None:
            return
        self._attrs_wrapper_layout.removeWidget(self._attrs_widget)
        self._attrs_widget.setVisible(False)
        self._attrs_widget.deleteLater()
        self._attrs_widget = None
        self._original_values = {}

    def _update_confirm_state(self) -> None:
        if self._mode == CREATE_MODE:
            self._confirm_btn.setEnabled(self._attrs_widget is not None)
            self._cancel_btn.setEnabled(True)
            return

        has_changes = self.has_unsaved_changes()
        self._confirm_btn.setEnabled(has_changes)
        self._cancel_btn.setEnabled(has_changes)

    def _request_dynamic_update(self) -> None:
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
        completions = self._controller.get_placeholder_completions(
            self._plugin_identifier, values
        )
        if completions and self._attrs_widget is not None:
            self._attrs_widget.set_completions(completions)

        preview = self._controller.get_placeholder_preview(
            self._plugin_identifier, values
        )
        self._preview_widget.set_preview(preview)

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

        if self._attrs_widget is not None:
            self._attrs_widget.set_value(copy.deepcopy(self._original_values))
            self._update_confirm_state()

    def _on_select_click(self) -> None:
        if self._scene_identifier is not None:
            self.select_in_scene_requested.emit(self._scene_identifier)

    def _on_run_click(self) -> None:
        if self._scene_identifier is not None:
            self.run_requested.emit(self._scene_identifier)

    def _on_remove_click(self) -> None:
        if self._scene_identifier is not None:
            self.remove_requested.emit(self._scene_identifier)
