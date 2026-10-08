from __future__ import annotations

import html
import uuid
import typing
from typing import Any

import qtmaterialsymbols
from qtpy import QtWidgets, QtCore

from ayon_core.lib.icon_definitions import (
    DEFAULT_WEB_ICON_COLOR,
    IconBase,
    MaterialSymbolsIcon,
    get_icon_def_from_data,
)
from ayon_core.tools.utils.lib import RefreshThread, get_qt_icon
from ayon_core.ui.components import AYButton, AYMenu

if typing.TYPE_CHECKING:
    from ayon_core.tools.workfiles.abstract import (
        ActionItem,
        ActionSelectionData,
        AbstractWorkfilesFrontend,
    )

# Icon used in AYON frontend for actions
MORE_ACTIONS_ICON = "category"

_ACTIVE_THREADS: set[RefreshThread] = set()
_THREAD_SHUTDOWN_CONNECTED = False


def _wait_for_threads() -> None:
    """Keep Qt from destroying threads while they are running."""
    for thread in list(_ACTIVE_THREADS):
        if thread.isRunning():
            thread.wait()


def _track_thread(thread: RefreshThread) -> None:
    """Keep a process-level reference until a thread has finished."""
    global _THREAD_SHUTDOWN_CONNECTED

    _ACTIVE_THREADS.add(thread)
    thread.finished.connect(lambda: _ACTIVE_THREADS.discard(thread))
    app = QtWidgets.QApplication.instance()
    if app is not None and not _THREAD_SHUTDOWN_CONNECTED:
        app.aboutToQuit.connect(_wait_for_threads)
        _THREAD_SHUTDOWN_CONNECTED = True


def _get_action_tooltip(action_item: ActionItem) -> str:
    """Rich text tooltip with label, tooltip and description of action."""
    label = action_item.label
    if action_item.group_label:
        label = f"{action_item.group_label}: {label}"
    lines = [f"<b>{html.escape(label)}</b>"]
    for text in (action_item.tooltip, action_item.description):
        if text:
            lines.append(html.escape(text))
    return "<br/>".join(lines)


def _get_icon_def(action_item: ActionItem) -> IconBase | None:
    icon = action_item.icon
    if isinstance(icon, dict):
        try:
            icon = get_icon_def_from_data(icon)
        except Exception:
            icon = None
    return icon


def add_actions_to_menu(
    menu: QtWidgets.QMenu,
    action_items: list[ActionItem],
) -> dict[QtWidgets.QAction, ActionItem]:
    """Add workfile action items to a menu.

    Items with group label are added to submenus.

    Args:
        menu (QtWidgets.QMenu): Menu to fill.
        action_items (list[ActionItem]): Sorted action items.

    Returns:
        dict[QtWidgets.QAction, ActionItem]: Action items by created
            qt actions.

    """
    menu.setToolTipsVisible(True)
    items_by_action = {}
    group_menu_by_label = {}
    for action_item in action_items:
        action = QtWidgets.QAction(action_item.label, menu)
        icon = get_qt_icon(_get_icon_def(action_item))
        if icon is not None:
            action.setIcon(icon)
        action.setToolTip(_get_action_tooltip(action_item))
        tip = action_item.tooltip or action_item.description
        if tip:
            action.setStatusTip(tip)
        items_by_action[action] = action_item

        group_label = action_item.group_label
        if not group_label:
            menu.addAction(action)
            continue

        group_menu = group_menu_by_label.get(group_label)
        if group_menu is None:
            group_menu = type(menu)(group_label, menu)
            group_menu.setToolTipsVisible(True)
            if icon is not None:
                group_menu.setIcon(icon)
            menu.addMenu(group_menu)
            group_menu_by_label[group_label] = group_menu
        group_menu.addAction(action)
    return items_by_action


class WorkfileActionsLoader(QtCore.QObject):
    """Collect workfile action items without blocking the UI.

    Action items are collected in a background thread. Signal
        'items_changed' is emitted when items for a selection are
        available. The items are cached by the controller, this object
        cares only about the threads.

    Plugins have to be discovered before the first collection. Preparation
        of plugin paths happens in a thread too, only import of plugin
        files happens in the main thread.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        parent (QtCore.QObject | None): Parent object.

    """
    items_changed = QtCore.Signal(object)

    def __init__(
        self,
        controller: AbstractWorkfilesFrontend,
        parent: QtCore.QObject | None = None,
    ) -> None:
        super().__init__(parent)

        controller.register_event_callback(
            "controller.reset.started",
            self._on_controller_reset,
        )
        controller.register_event_callback(
            "workfile_action.finished",
            self._on_action_finished,
        )

        self._controller = controller
        self._plugins_ready = False
        self._prepare_thread: RefreshThread | None = None
        # Selections waiting for the plugins
        self._queued_selections: list[ActionSelectionData] = []
        self._fetch_threads: dict[
            str, tuple[RefreshThread, ActionSelectionData]
        ] = {}
        self._fetching_selections: set[ActionSelectionData] = set()

    def get_cached_items(
        self, selection: ActionSelectionData
    ) -> list[ActionItem] | None:
        """Get action items if are already collected.

        Args:
            selection (ActionSelectionData): Selection in the tool.

        Returns:
            list[ActionItem] | None: Action items or None if were
                not collected yet.

        """
        return self._controller.get_cached_workfile_action_items(selection)

    def get_items(
        self, selection: ActionSelectionData
    ) -> list[ActionItem]:
        """Get action items right away.

        Items are collected in the current thread if they are not cached
            yet. Use when the items are needed right now, e.g. for context
            menu.

        Args:
            selection (ActionSelectionData): Selection in the tool.

        Returns:
            list[ActionItem]: Action items.

        """
        items = self.get_cached_items(selection)
        if items is None:
            self._controller.prepare_workfile_action_plugins()
            self._plugins_ready = True
            items = self._controller.get_workfile_action_items(selection)
        return items

    def request_items(self, selection: ActionSelectionData) -> None:
        """Collect action items in the background.

        Signal 'items_changed' is emitted when the items are available.

        Args:
            selection (ActionSelectionData): Selection in the tool.

        """
        if self.get_cached_items(selection) is not None:
            self.items_changed.emit(selection)
            return

        if self._plugins_ready:
            self._start_fetch(selection)
            return

        if selection not in self._queued_selections:
            self._queued_selections.append(selection)
        self._start_prepare()

    def _forget_requests(self) -> None:
        # Items collected by running threads are not cached by controller
        #   because its cache was cleared
        self._queued_selections = []
        self._fetching_selections = set()

    def _on_controller_reset(self) -> None:
        # Plugins are discovered again after reset
        self._plugins_ready = False
        self._forget_requests()

    def _on_action_finished(self) -> None:
        self._forget_requests()

    def _start_prepare(self) -> None:
        if self._prepare_thread is not None:
            return
        thread = RefreshThread(
            uuid.uuid4().hex,
            self._controller.prepare_workfile_action_paths,
        )
        self._prepare_thread = thread
        thread.refresh_finished.connect(self._on_prepare_finished)
        _track_thread(thread)
        thread.start()

    def _on_prepare_finished(self, _thread_id: str) -> None:
        self._prepare_thread = None
        # Import of plugin files has to happen in the main thread
        self._controller.prepare_workfile_action_plugins()
        self._plugins_ready = True

        queued_selections = self._queued_selections
        self._queued_selections = []
        for selection in queued_selections:
            self._start_fetch(selection)

    def _start_fetch(self, selection: ActionSelectionData) -> None:
        if selection in self._fetching_selections:
            return
        self._fetching_selections.add(selection)
        thread = RefreshThread(
            uuid.uuid4().hex,
            self._controller.get_workfile_action_items,
            selection,
        )
        self._fetch_threads[thread.id] = (thread, selection)
        thread.refresh_finished.connect(self._on_fetch_finished)
        _track_thread(thread)
        thread.start()

    def _on_fetch_finished(self, thread_id: str) -> None:
        _thread, selection = self._fetch_threads.pop(thread_id)
        self._fetching_selections.discard(selection)
        # Items are not cached if cache of the controller was cleared
        #   during the collection
        if self.get_cached_items(selection) is not None:
            self.items_changed.emit(selection)


class WorkfileActionsRow(QtWidgets.QWidget):
    """Row of buttons with actions available for the current selection.

    Shows as many action buttons as fit into the width of the widget. The
        rest of the actions is available in a menu of the last button.
        Actions that are not marked as quick actions are not shown, they
        are available only in the context menu of workfiles.

    The widget always takes its space, so the layout around does not jump
        when actions become available. The buttons fade in when actions
        are available and fade out when there are no actions for
        the selection.

    Args:
        controller (AbstractWorkfilesFrontend): The control object.
        actions_loader (WorkfileActionsLoader): Loader of action items.
        parent (QtWidgets.QWidget): The parent widget.

    """
    spacing = 4
    # Duration of buttons fade in milliseconds
    fade_duration = 150

    def __init__(
        self,
        controller: AbstractWorkfilesFrontend,
        actions_loader: WorkfileActionsLoader,
        parent: QtWidgets.QWidget,
    ) -> None:
        super().__init__(parent)

        # Buttons are in a separate widget so they can fade together
        content_widget = QtWidgets.QWidget(self)
        content_widget.setVisible(False)
        opacity_effect = QtWidgets.QGraphicsOpacityEffect(content_widget)
        opacity_effect.setOpacity(0.0)
        content_widget.setGraphicsEffect(opacity_effect)

        more_btn = AYButton(
            icon=MORE_ACTIONS_ICON,
            variant=AYButton.Variants.Surface,
            tooltip="More actions",
            parent=content_widget,
        )
        more_btn.setVisible(False)

        fade_anim = QtCore.QVariantAnimation(self)
        fade_anim.setEasingCurve(QtCore.QEasingCurve.InOutQuad)

        # Do not collect actions for each change in a quick sequence of
        #   selection changes
        request_timer = QtCore.QTimer(self)
        request_timer.setSingleShot(True)
        request_timer.setInterval(100)

        request_timer.timeout.connect(self._request_items)
        fade_anim.valueChanged.connect(self._on_fade_value_change)
        fade_anim.finished.connect(self._on_fade_finished)
        more_btn.clicked.connect(self._on_more_clicked)
        actions_loader.items_changed.connect(self._on_items_changed)

        for topic in (
            "selection.task.changed",
            "selection.workarea.changed",
            "selection.representation.changed",
            "controller.reset.finished",
        ):
            controller.register_event_callback(
                topic, self._on_selection_change
            )
        controller.register_event_callback(
            "workfile_action.finished", self._on_action_finished
        )

        self._controller = controller
        self._actions_loader = actions_loader
        self._content_widget = content_widget
        self._opacity_effect = opacity_effect
        self._fade_anim = fade_anim
        self._more_btn = more_btn
        self._request_timer = request_timer

        self._published_mode = False
        # Selection for which are items requested
        self._requested_selection: ActionSelectionData | None = None
        # Selection for which are items shown
        self._selection: ActionSelectionData | None = None
        self._action_items: list[ActionItem] = []
        self._buttons: list[AYButton] = []
        self._overflow_items: list[ActionItem] = []

        self.setSizePolicy(
            QtWidgets.QSizePolicy.Policy.Ignored,
            QtWidgets.QSizePolicy.Policy.Fixed,
        )

    def set_published_mode(self, published_mode: bool) -> None:
        """Change published mode.

        Args:
            published_mode (bool): Published mode enabled.

        """
        if self._published_mode == published_mode:
            return
        self._published_mode = published_mode
        self._on_selection_change()

    def sizeHint(self) -> QtCore.QSize:
        # Height does not depend on the buttons to keep the space reserved
        return self._more_btn.sizeHint()

    def minimumSizeHint(self) -> QtCore.QSize:
        return self.sizeHint()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_buttons_geometry()

    def showEvent(self, event) -> None:
        super().showEvent(event)
        self._update_buttons_geometry()

    def _on_selection_change(self) -> None:
        selection = self._controller.get_workfile_action_selection(
            self._published_mode
        )
        self._requested_selection = selection
        items = self._actions_loader.get_cached_items(selection)
        if items is not None:
            self._request_timer.stop()
            self._set_items(selection, items)
            return

        # Buttons of previous selection stay as they are until actions of
        #   the new selection are known, so the row does not flicker when
        #   a user goes through workfiles
        self._request_timer.start()

    def _on_action_finished(self) -> None:
        # Available actions might be different after an action, the
        #   controller did clear cached items
        self._requested_selection = (
            self._controller.get_workfile_action_selection(
                self._published_mode
            )
        )
        self._selection = None
        self._request_timer.start()

    def _request_items(self) -> None:
        if self._requested_selection is not None:
            self._actions_loader.request_items(self._requested_selection)

    def _on_items_changed(self, selection: ActionSelectionData) -> None:
        if selection != self._requested_selection:
            return
        items = self._actions_loader.get_cached_items(selection)
        if items is not None:
            self._set_items(selection, items)

    def _set_items(
        self,
        selection: ActionSelectionData,
        action_items: list[ActionItem],
    ) -> None:
        self._selection = selection
        action_items = [
            action_item
            for action_item in action_items
            if action_item.quick_action
        ]
        if not action_items:
            # Keep the buttons until they fade out
            self._action_items = []
            self._fade_to(0.0)
            return

        if action_items != self._action_items or not self._buttons:
            self._action_items = action_items
            self._remove_buttons()
            self._buttons = [
                self._create_button(action_item)
                for action_item in action_items
            ]
            self._update_buttons_geometry()

        self._fade_to(1.0)

    def _ensure_current_items(self) -> None:
        """Make sure shown actions are related to current selection.

        Shown buttons are related to previous selection until actions of
            the new selection are collected. Collect them right away if
            a user is faster.
        """
        selection = self._requested_selection
        if selection is None or selection == self._selection:
            return
        self._request_timer.stop()
        self._set_items(selection, self._actions_loader.get_items(selection))

    def _remove_buttons(self) -> None:
        for button in self._buttons:
            button.setVisible(False)
            button.deleteLater()
        self._buttons = []

    def _fade_to(self, opacity: float) -> None:
        """Animate opacity of the buttons to the value."""
        fade_in = opacity > 0.0
        if fade_in:
            self._content_widget.setVisible(True)
        # Buttons that fade out should not be clickable
        self._content_widget.setAttribute(
            QtCore.Qt.WA_TransparentForMouseEvents, not fade_in
        )

        self._fade_anim.stop()
        current_opacity = self._opacity_effect.opacity()
        if not self._buttons or current_opacity == opacity:
            self._opacity_effect.setOpacity(opacity)
            self._on_fade_finished()
            return

        self._opacity_effect.setEnabled(True)
        self._fade_anim.setStartValue(current_opacity)
        self._fade_anim.setEndValue(opacity)
        self._fade_anim.setDuration(
            int(self.fade_duration * abs(opacity - current_opacity))
        )
        self._fade_anim.start()

    def _on_fade_value_change(self, value: float) -> None:
        self._opacity_effect.setOpacity(value)

    def _on_fade_finished(self) -> None:
        if self._opacity_effect.opacity() > 0.0:
            # Effect is not needed for fully visible buttons
            self._opacity_effect.setEnabled(False)
            return
        self._content_widget.setVisible(False)
        self._remove_buttons()
        self._update_buttons_geometry()

    def _create_button(self, action_item: ActionItem) -> AYButton:
        kwargs: dict[str, Any] = {
            "variant": AYButton.Variants.Surface,
            "tooltip": _get_action_tooltip(action_item),
            "parent": self._content_widget,
        }
        icon_def = _get_icon_def(action_item)
        qt_icon = None
        args = []
        if (
            isinstance(icon_def, MaterialSymbolsIcon)
            and qtmaterialsymbols.get_icon_name_char(icon_def.name) is not None
        ):
            # Let the button handle colors of the icon by its state
            kwargs["icon"] = icon_def.name
            kwargs["icon_fill"] = icon_def.fill
            if icon_def.color != DEFAULT_WEB_ICON_COLOR:
                kwargs["icon_color"] = icon_def.color

        elif icon_def is not None:
            qt_icon = get_qt_icon(icon_def, default=None)

        if "icon" not in kwargs and qt_icon is None:
            # Actions without icon are shown with their label
            args.append(action_item.label)

        button = AYButton(*args, **kwargs)
        if qt_icon is not None:
            button.setIcon(qt_icon)
        button.clicked.connect(
            lambda *_, item=action_item: self._trigger_action(item)
        )
        return button

    def _update_buttons_geometry(self) -> None:
        """Show buttons that fit to the width and hide the rest."""
        self._content_widget.setGeometry(self.rect())
        if not self._buttons:
            self._overflow_items = []
            self._more_btn.setVisible(False)
            return

        width = self.width()
        height = self.height()
        more_size = self._more_btn.sizeHint()
        sizes = [button.sizeHint() for button in self._buttons]

        total_width = (
            sum(size.width() for size in sizes)
            + self.spacing * (len(sizes) - 1)
        )
        available_width = width
        show_more = total_width > width
        if show_more:
            available_width -= more_size.width() + self.spacing

        pos_x = 0
        visible_count = 0
        for size in sizes:
            if pos_x + size.width() > available_width:
                break
            pos_x += size.width() + self.spacing
            visible_count += 1

        pos_x = 0
        for idx, button in enumerate(self._buttons):
            visible = idx < visible_count
            button.setVisible(visible)
            if not visible:
                continue
            size = sizes[idx]
            button.setGeometry(
                pos_x, (height - size.height()) // 2,
                size.width(), size.height(),
            )
            pos_x += size.width() + self.spacing

        # Action items are already cleared for buttons that fade out
        self._overflow_items = self._action_items[visible_count:]
        self._more_btn.setVisible(show_more)
        if show_more:
            self._more_btn.setGeometry(
                pos_x, (height - more_size.height()) // 2,
                more_size.width(), more_size.height(),
            )

    def _on_more_clicked(self) -> None:
        self._ensure_current_items()
        if not self._overflow_items:
            return
        menu = AYMenu(self)
        items_by_action = add_actions_to_menu(menu, self._overflow_items)
        action = menu.exec_(
            self._more_btn.mapToGlobal(
                QtCore.QPoint(0, self._more_btn.height())
            )
        )
        action_item = items_by_action.get(action)
        if action_item is not None:
            self._trigger_action(action_item)

    def _trigger_action(self, action_item: ActionItem) -> None:
        self._ensure_current_items()
        # The action might not be available for the current selection
        if self._selection is None or action_item not in self._action_items:
            return
        self._controller.trigger_workfile_action(
            action_item.identifier,
            self._selection,
            action_item.data,
            {},
        )
