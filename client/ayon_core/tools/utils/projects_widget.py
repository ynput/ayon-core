from __future__ import annotations
from abc import ABC, abstractmethod
from collections.abc import Callable
import typing
from typing import Optional

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.tools.common_models import (
    ProjectItem,
    PROJECTS_MODEL_SENDER,
)

from .views import ListView
from .lib import RefreshThread, get_qt_icon

if typing.TYPE_CHECKING:
    from typing import TypedDict

    class ExpectedProjectSelectionData(TypedDict):
        name: Optional[str]
        current: Optional[str]
        selected: Optional[str]


    class ExpectedSelectionData(TypedDict):
        project: ExpectedProjectSelectionData


PROJECT_NAME_ROLE = QtCore.Qt.UserRole + 1
PROJECT_IS_ACTIVE_ROLE = QtCore.Qt.UserRole + 2
PROJECT_IS_LIBRARY_ROLE = QtCore.Qt.UserRole + 3
PROJECT_IS_CURRENT_ROLE = QtCore.Qt.UserRole + 4
PROJECT_IS_PINNED_ROLE = QtCore.Qt.UserRole + 5
LIBRARY_PROJECT_SEPARATOR_ROLE = QtCore.Qt.UserRole + 6


class AbstractProjectController(ABC):
    @abstractmethod
    def register_event_callback(self, topic: str, callback: Callable):
        pass

    @abstractmethod
    def get_project_items(
        self, sender: Optional[str] = None
    ) -> list[str]:
        pass

    @abstractmethod
    def set_selected_project(self, project_name: str):
        pass

    # These are required only if widget should handle expected selection
    @abstractmethod
    def expected_project_selected(self, project_name: str):
        pass

    @abstractmethod
    def get_expected_selection_data(self) -> "ExpectedSelectionData":
        pass


class ProjectsQtModel(QtGui.QStandardItemModel):
    refreshed = QtCore.Signal()

    def __init__(self, controller: AbstractProjectController):
        super().__init__()
        self._controller = controller

        self._project_items = {}
        self._has_libraries = False

        self._empty_item = None
        self._empty_item_added = False

        self._select_item = None
        self._select_item_added = False
        self._select_item_visible = None

        self._libraries_sep_item = None
        self._libraries_sep_item_added = False
        self._libraries_sep_item_visible = False

        self._current_context_project = None

        self._selected_project = None

        self._refresh_thread = None

    @property
    def is_refreshing(self):
        return self._refresh_thread is not None

    def refresh(self):
        self._refresh()

    def has_content(self):
        return len(self._project_items) > 0

    def get_index_by_project_name(self, project_name):
        """Get index of project by name.

        Args:
            project_name (str): Project name.

        Returns:
            QtCore.QModelIndex: Index of project item. Index is not valid
                if project is not found.

        """
        item = self._project_items.get(project_name)
        if item is None:
            return QtCore.QModelIndex()
        return self.indexFromItem(item)

    def set_select_item_visible(self, visible):
        if self._select_item_visible is visible:
            return
        self._select_item_visible = visible

        if self._selected_project is None:
            self._add_select_item()

    def set_libraries_separator_visible(self, visible):
        if self._libraries_sep_item_visible is visible:
            return
        self._libraries_sep_item_visible = visible

    def set_selected_project(self, project_name):
        if not self._select_item_visible:
            return

        self._selected_project = project_name
        if project_name is None:
            self._add_select_item()
        else:
            self._remove_select_item()

    def set_current_context_project(self, project_name):
        if project_name == self._current_context_project:
            return
        self._unset_current_context_project(self._current_context_project)
        self._current_context_project = project_name
        self._set_current_context_project(project_name)

    def _set_current_context_project(self, project_name):
        item = self._project_items.get(project_name)
        if item is None:
            return
        item.setData(True, PROJECT_IS_CURRENT_ROLE)

    def _unset_current_context_project(self, project_name):
        item = self._project_items.get(project_name)
        if item is None:
            return
        item.setData(False, PROJECT_IS_CURRENT_ROLE)

    def _add_empty_item(self):
        if self._empty_item_added:
            return
        self._empty_item_added = True
        item = self._get_empty_item()
        root_item = self.invisibleRootItem()
        root_item.appendRow(item)

    def _remove_empty_item(self):
        if not self._empty_item_added:
            return
        self._empty_item_added = False
        root_item = self.invisibleRootItem()
        item = self._get_empty_item()
        root_item.takeRow(item.row())

    def _get_empty_item(self):
        if self._empty_item is None:
            item = QtGui.QStandardItem("< No projects >")
            item.setFlags(QtCore.Qt.NoItemFlags)
            self._empty_item = item
        return self._empty_item

    def _get_library_sep_item(self):
        if self._libraries_sep_item is not None:
            return self._libraries_sep_item

        item = QtGui.QStandardItem()
        item.setData("Libraries", QtCore.Qt.DisplayRole)
        item.setData(True, LIBRARY_PROJECT_SEPARATOR_ROLE)
        item.setFlags(QtCore.Qt.NoItemFlags)
        self._libraries_sep_item = item
        return item

    def _add_library_sep_item(self):
        if (
            not self._libraries_sep_item_visible
            or self._libraries_sep_item_added
        ):
            return
        self._libraries_sep_item_added = True
        item = self._get_library_sep_item()
        root_item = self.invisibleRootItem()
        root_item.appendRow(item)

    def _remove_library_sep_item(self):
        if (
            not self._libraries_sep_item_added
        ):
            return
        self._libraries_sep_item_added = False
        item = self._get_library_sep_item()
        root_item = self.invisibleRootItem()
        root_item.takeRow(item.row())

    def _add_select_item(self):
        if self._select_item_added:
            return
        self._select_item_added = True
        item = self._get_select_item()
        root_item = self.invisibleRootItem()
        root_item.appendRow(item)

    def _remove_select_item(self):
        if not self._select_item_added:
            return
        self._select_item_added = False
        root_item = self.invisibleRootItem()
        item = self._get_select_item()
        root_item.takeRow(item.row())

    def _get_select_item(self):
        if self._select_item is None:
            item = QtGui.QStandardItem("< Select project >")
            item.setEditable(False)
            self._select_item = item
        return self._select_item

    def _refresh(self):
        if self._refresh_thread is not None:
            return

        refresh_thread = RefreshThread(
            "projects", self._query_project_items
        )
        refresh_thread.refresh_finished.connect(self._refresh_finished)

        self._refresh_thread = refresh_thread
        refresh_thread.start()

    def _query_project_items(self):
        return self._controller.get_project_items(
            sender=PROJECTS_MODEL_SENDER
        )

    def _refresh_finished(self):
        # TODO check if failed
        result = self._refresh_thread.get_result()
        if result is not None:
            self._fill_items(result)

        self._refresh_thread = None
        if result is None:
            self._refresh()
        else:
            self.refreshed.emit()

    def _fill_items(self, project_items: list[ProjectItem]):
        new_project_names = {
            project_item.name
            for project_item in project_items
        }

        # Handle "Select item" visibility
        if self._select_item_visible:
            # Add select project. if previously selected project is not in
            #   project items
            if self._selected_project not in new_project_names:
                self._add_select_item()
            else:
                self._remove_select_item()

        root_item = self.invisibleRootItem()

        items_to_remove = set(self._project_items.keys()) - new_project_names
        for project_name in items_to_remove:
            item = self._project_items.pop(project_name)
            root_item.takeRow(item.row())

        has_library_project = False
        new_items = []
        for project_item in project_items:
            project_name = project_item.name
            item = self._project_items.get(project_name)
            if project_item.is_library:
                has_library_project = True
            if item is None:
                item = QtGui.QStandardItem()
                item.setEditable(False)
                new_items.append(item)
            icon = get_qt_icon(project_item.icon)
            item.setData(project_name, QtCore.Qt.DisplayRole)
            item.setData(icon, QtCore.Qt.DecorationRole)
            item.setData(project_name, PROJECT_NAME_ROLE)
            item.setData(project_item.active, PROJECT_IS_ACTIVE_ROLE)
            item.setData(project_item.is_library, PROJECT_IS_LIBRARY_ROLE)
            item.setData(project_item.is_pinned, PROJECT_IS_PINNED_ROLE)
            is_current = project_name == self._current_context_project
            item.setData(is_current, PROJECT_IS_CURRENT_ROLE)
            self._project_items[project_name] = item

        self._set_current_context_project(self._current_context_project)

        self._has_libraries = has_library_project

        if new_items:
            root_item.appendRows(new_items)

        if self.has_content():
            # Make sure "No projects" item is removed
            self._remove_empty_item()
            if has_library_project:
                self._add_library_sep_item()
            else:
                self._remove_library_sep_item()
        else:
            # Keep only "No projects" item
            self._add_empty_item()
            self._remove_select_item()
            self._remove_library_sep_item()


class ProjectSortFilterProxy(QtCore.QSortFilterProxyModel):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._filter_inactive = True
        self._filter_standard = False
        self._filter_library = False
        self._sort_by_type = True
        # Disable case sensitivity
        self.setSortCaseSensitivity(QtCore.Qt.CaseInsensitive)
        self.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

    def _type_sort(self, l_index, r_index):
        if not self._sort_by_type:
            return None

        l_is_library = l_index.data(PROJECT_IS_LIBRARY_ROLE)
        r_is_library = r_index.data(PROJECT_IS_LIBRARY_ROLE)
        # Both hare project items
        if l_is_library is not None and r_is_library is not None:
            if l_is_library is r_is_library:
                return None
            if l_is_library:
                return False
            return True

        if l_index.data(LIBRARY_PROJECT_SEPARATOR_ROLE):
            if r_is_library is None:
                return False
            return r_is_library

        if r_index.data(LIBRARY_PROJECT_SEPARATOR_ROLE):
            if l_is_library is None:
                return True
            return l_is_library
        return None

    def lessThan(self, left_index, right_index):
        # Current project always on top
        # - make sure this is always first, before any other sorting
        #   e.g. type sort would move the item lower
        if left_index.data(PROJECT_IS_CURRENT_ROLE):
            return True
        if right_index.data(PROJECT_IS_CURRENT_ROLE):
            return False

        # Library separator should be before library projects
        l_is_library = left_index.data(PROJECT_IS_LIBRARY_ROLE)
        r_is_library = right_index.data(PROJECT_IS_LIBRARY_ROLE)
        l_is_sep = left_index.data(LIBRARY_PROJECT_SEPARATOR_ROLE)
        r_is_sep = right_index.data(LIBRARY_PROJECT_SEPARATOR_ROLE)
        if l_is_sep:
            return bool(r_is_library)

        if r_is_sep:
            return not l_is_library

        # Non project items should be on top
        l_project_name = left_index.data(PROJECT_NAME_ROLE)
        r_project_name = right_index.data(PROJECT_NAME_ROLE)
        if l_project_name is None:
            return True
        if r_project_name is None:
            return False

        left_is_active = left_index.data(PROJECT_IS_ACTIVE_ROLE)
        right_is_active = right_index.data(PROJECT_IS_ACTIVE_ROLE)
        if right_is_active != left_is_active:
            return left_is_active

        l_is_pinned = left_index.data(PROJECT_IS_PINNED_ROLE)
        r_is_pinned = right_index.data(PROJECT_IS_PINNED_ROLE)
        if l_is_pinned is True and not r_is_pinned:
            return True

        if r_is_pinned is True and not l_is_pinned:
            return False

        # Move inactive projects to the end
        left_is_active = left_index.data(PROJECT_IS_ACTIVE_ROLE)
        right_is_active = right_index.data(PROJECT_IS_ACTIVE_ROLE)
        if right_is_active != left_is_active:
            return left_is_active

        # Move library projects after standard projects
        if (
            l_is_library is not None
            and r_is_library is not None
            and l_is_library != r_is_library
        ):
            return r_is_library
        return super().lessThan(left_index, right_index)

    def filterAcceptsRow(self, source_row, source_parent):
        index = self.sourceModel().index(source_row, 0, source_parent)
        project_name = index.data(PROJECT_NAME_ROLE)
        if project_name is None:
            return True

        # Make sure current project is visible
        if index.data(PROJECT_IS_CURRENT_ROLE):
            return True

        default = super().filterAcceptsRow(source_row, source_parent)
        if not default:
            return default

        string_pattern = self.filterRegularExpression().pattern()
        if (
            string_pattern
            and string_pattern.lower() not in project_name.lower()
        ):
            return False

        if (
            self._filter_inactive
            and not index.data(PROJECT_IS_ACTIVE_ROLE)
        ):
            return False

        if (
            self._filter_standard
            and not index.data(PROJECT_IS_LIBRARY_ROLE)
        ):
            return False

        if (
            self._filter_library
            and index.data(PROJECT_IS_LIBRARY_ROLE)
        ):
            return False
        return True

    def _custom_index_filter(self, index):
        return bool(index.data(PROJECT_IS_ACTIVE_ROLE))

    def is_active_filter_enabled(self):
        return self._filter_inactive

    def set_active_filter_enabled(self, enabled):
        if self._filter_inactive == enabled:
            return
        self._filter_inactive = enabled
        self.invalidateFilter()

    def set_library_filter_enabled(self, enabled):
        if self._filter_library == enabled:
            return
        self._filter_library = enabled
        self.invalidateFilter()

    def set_standard_filter_enabled(self, enabled):
        if self._filter_standard == enabled:
            return
        self._filter_standard = enabled
        self.invalidateFilter()

    def set_sort_by_type(self, enabled):
        if self._sort_by_type is enabled:
            return
        self._sort_by_type = enabled
        self.invalidate()


class ProjectsDelegate(QtWidgets.QStyledItemDelegate):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._pin_icon = None

    def paint(self, painter, option, index):
        is_pinned = index.data(PROJECT_IS_PINNED_ROLE)
        if not is_pinned:
            super().paint(painter, option, index)
            return
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        widget = option.widget
        if widget is None:
            style = QtWidgets.QApplication.style()
        else:
            style = widget.style()
        # CE_ItemViewItem
        proxy = style.proxy()
        painter.save()
        painter.setClipRect(option.rect)
        decor_rect = proxy.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemDecoration, opt, widget
        )
        text_rect = proxy.subElementRect(
            QtWidgets.QStyle.SE_ItemViewItemText, opt, widget
        )
        proxy.drawPrimitive(
            QtWidgets.QStyle.PE_PanelItemViewItem, opt, painter, widget
        )
        mode = QtGui.QIcon.Normal
        if not opt.state & QtWidgets.QStyle.State_Enabled:
            mode = QtGui.QIcon.Disabled
        elif opt.state & QtWidgets.QStyle.State_Selected:
            mode = QtGui.QIcon.Selected
        state = QtGui.QIcon.Off
        if opt.state & QtWidgets.QStyle.State_Open:
            state = QtGui.QIcon.On

        # Draw project icon
        opt.icon.paint(
            painter, decor_rect, opt.decorationAlignment, mode, state
        )

        # Draw pin icon
        if index.data(PROJECT_IS_PINNED_ROLE):
            pin_icon = self._get_pin_icon()
            pin_rect = QtCore.QRect(decor_rect)
            diff = option.rect.width() - pin_rect.width()
            pin_rect.moveLeft(diff)
            pin_icon.paint(
                painter, pin_rect, opt.decorationAlignment, mode, state
            )

        # Draw text
        if opt.text:
            if not opt.state & QtWidgets.QStyle.State_Enabled:
                cg = QtGui.QPalette.Disabled
            elif not (opt.state & QtWidgets.QStyle.State_Active):
                cg = QtGui.QPalette.Inactive
            else:
                cg = QtGui.QPalette.Normal

            if opt.state & QtWidgets.QStyle.State_Selected:
                painter.setPen(opt.palette.color(cg, QtGui.QPalette.HighlightedText))
            else:
                painter.setPen(opt.palette.color(cg, QtGui.QPalette.Text))

            if opt.state & QtWidgets.QStyle.State_Editing:
                painter.setPen(opt.palette.color(cg, QtGui.QPalette.Text))
                painter.drawRect(text_rect.adjusted(0, 0, -1, -1))

            margin = proxy.pixelMetric(
                QtWidgets.QStyle.PM_FocusFrameHMargin, None, widget
            ) + 1
            text_rect.adjust(margin, 0, -margin, 0)
            # NOTE skipping some steps e.g. word wrapping and elided
            #   text (adding '...' when too long).
            painter.drawText(
                text_rect,
                opt.displayAlignment,
                opt.text
            )

        # Draw focus rect
        if opt.state & QtWidgets.QStyle.State_HasFocus:
            focus_opt = QtWidgets.QStyleOptionFocusRect()
            focus_opt.state = option.state
            focus_opt.direction = option.direction
            focus_opt.rect = option.rect
            focus_opt.fontMetrics = option.fontMetrics
            focus_opt.palette = option.palette

            focus_opt.rect = style.subElementRect(
                QtWidgets.QCommonStyle.SE_ItemViewItemFocusRect,
                option,
                option.widget
            )
            focus_opt.state |= (
                QtWidgets.QStyle.State_KeyboardFocusChange
                | QtWidgets.QStyle.State_Item
            )
            focus_opt.backgroundColor = option.palette.color(
                (
                    QtGui.QPalette.Normal
                    if option.state & QtWidgets.QStyle.State_Enabled
                    else QtGui.QPalette.Disabled
                ),
                (
                    QtGui.QPalette.Highlight
                    if option.state & QtWidgets.QStyle.State_Selected
                    else QtGui.QPalette.Window
                )
            )
            style.drawPrimitive(
                QtWidgets.QCommonStyle.PE_FrameFocusRect,
                focus_opt,
                painter,
                option.widget
            )
        painter.restore()

    def _get_pin_icon(self):
        if self._pin_icon is None:
            self._pin_icon = get_qt_icon({
                "type": "material-symbols",
                "name": "keep",
            })
        return self._pin_icon


class ProjectsCombobox(QtWidgets.QWidget):
    refreshed = QtCore.Signal()
    selection_changed = QtCore.Signal(str)

    def __init__(
        self,
        controller: AbstractProjectController,
        parent: QtWidgets.QWidget,
        handle_expected_selection: bool = False,
    ):
        super().__init__(parent)

        projects_combobox = QtWidgets.QComboBox(self)
        combobox_delegate = ProjectsDelegate(projects_combobox)
        projects_combobox.setItemDelegate(combobox_delegate)
        projects_model = ProjectsQtModel(controller)
        projects_proxy_model = ProjectSortFilterProxy()
        projects_proxy_model.setSourceModel(projects_model)
        projects_combobox.setModel(projects_proxy_model)

        main_layout = QtWidgets.QHBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(projects_combobox, 1)

        projects_model.refreshed.connect(self._on_model_refresh)

        controller.register_event_callback(
            "projects.refresh.finished",
            self._on_projects_refresh_finished
        )
        controller.register_event_callback(
            "controller.refresh.finished",
            self._on_controller_refresh
        )
        controller.register_event_callback(
            "expected_selection_changed",
            self._on_expected_selection_change
        )

        projects_combobox.currentIndexChanged.connect(
            self._on_current_index_changed
        )

        self._controller = controller
        self._listen_selection_change = True
        self._select_item_visible = False

        self._handle_expected_selection = handle_expected_selection
        self._expected_selection = None

        self._projects_combobox = projects_combobox
        self._projects_model = projects_model
        self._projects_proxy_model = projects_proxy_model
        self._combobox_delegate = combobox_delegate

    def refresh(self):
        self._projects_model.refresh()

    def set_selection(self, project_name: str):
        """Set selection to a given project.

        Selection change is ignored if project is not found.

        Args:
            project_name (str): Name of project.

        Returns:
            bool: True if selection was changed, False otherwise. NOTE:
                Selection may not be changed if project is not found, or if
                project is already selected.

        """
        idx = self._projects_combobox.findData(
            project_name, PROJECT_NAME_ROLE)
        if idx < 0:
            return False
        if idx != self._projects_combobox.currentIndex():
            self._projects_combobox.setCurrentIndex(idx)
            return True
        return False

    def set_listen_to_selection_change(self, listen: bool):
        """Disable listening to changes of the selection.

        Because combobox is triggering selection change when it's model
        is refreshed, it's necessary to disable listening to selection for
        some cases, e.g. when is on a different page of UI and should be just
        refreshed.

        Args:
            listen (bool): Enable or disable listening to selection changes.
        """

        self._listen_selection_change = listen

    def get_selected_project_name(self):
        """Name of selected project.

        Returns:
            Union[str, None]: Name of selected project, or None if no project
        """

        idx = self._projects_combobox.currentIndex()
        if idx < 0:
            return None
        return self._projects_combobox.itemData(idx, PROJECT_NAME_ROLE)

    def set_current_context_project(self, project_name: str):
        self._projects_model.set_current_context_project(project_name)
        self._projects_proxy_model.invalidateFilter()

    def set_select_item_visible(self, visible: bool):
        self._select_item_visible = visible
        self._projects_model.set_select_item_visible(visible)
        self._update_select_item_visiblity()

    def set_libraries_separator_visible(self, visible):
        self._projects_model.set_libraries_separator_visible(visible)

    def is_active_filter_enabled(self):
        return self._projects_proxy_model.is_active_filter_enabled()

    def set_active_filter_enabled(self, enabled):
        return self._projects_proxy_model.set_active_filter_enabled(enabled)

    def set_standard_filter_enabled(self, enabled):
        return self._projects_proxy_model.set_standard_filter_enabled(enabled)

    def set_library_filter_enabled(self, enabled):
        return self._projects_proxy_model.set_library_filter_enabled(enabled)

    def _update_select_item_visiblity(self, **kwargs):
        if not self._select_item_visible:
            return
        if "project_name" not in kwargs:
            project_name = self.get_selected_project_name()
        else:
            project_name = kwargs.get("project_name")

        # Hide the item if a project is selected
        self._projects_model.set_selected_project(project_name)

    def _on_current_index_changed(self, idx):
        if not self._listen_selection_change:
            return
        project_name = self._projects_combobox.itemData(
            idx, PROJECT_NAME_ROLE)
        self._update_select_item_visiblity(project_name=project_name)
        self._controller.set_selected_project(project_name)
        self.selection_changed.emit(project_name or "")

    def _on_model_refresh(self):
        self._projects_proxy_model.sort(0)
        self._projects_proxy_model.invalidateFilter()
        if self._expected_selection:
            self._set_expected_selection()
        self._update_select_item_visiblity()
        self.refreshed.emit()

    def _on_projects_refresh_finished(self, event):
        if event["sender"] != PROJECTS_MODEL_SENDER:
            self._projects_model.refresh()

    def _on_controller_refresh(self):
        self._update_expected_selection()

    # Expected selection handling
    def _on_expected_selection_change(self, event):
        self._update_expected_selection(event.data)

    def _set_expected_selection(self):
        if not self._handle_expected_selection:
            return
        project_name = self._expected_selection
        if project_name is not None:
            if project_name != self.get_selected_project_name():
                self.set_selection(project_name)
            else:
                # Fake project change
                self._on_current_index_changed(
                    self._projects_combobox.currentIndex()
                )

        self._controller.expected_project_selected(project_name)

    def _update_expected_selection(self, expected_data=None):
        if not self._handle_expected_selection:
            return
        if expected_data is None:
            expected_data = self._controller.get_expected_selection_data()

        project_data = expected_data.get("project")
        if (
            not project_data
            or not project_data["current"]
            or project_data["selected"]
        ):
            return
        self._expected_selection = project_data["name"]
        if not self._projects_model.is_refreshing:
            self._set_expected_selection()


class ProjectsWidget(QtWidgets.QWidget):
    """Projects widget showing projects in list.

    Warnings:
        This widget does not support expected selection handling.

    """
    refreshed = QtCore.Signal()
    selection_changed = QtCore.Signal(str)
    double_clicked = QtCore.Signal()

    def __init__(
        self,
        controller: AbstractProjectController,
        parent: Optional[QtWidgets.QWidget] = None
    ):
        super().__init__(parent=parent)

        projects_view = ListView(parent=self)
        projects_view.setResizeMode(QtWidgets.QListView.Adjust)
        projects_view.setVerticalScrollMode(
            QtWidgets.QAbstractItemView.ScrollPerPixel
        )
        projects_view.setAlternatingRowColors(False)
        projects_view.setWrapping(False)
        projects_view.setWordWrap(False)
        projects_view.setSpacing(0)
        projects_delegate = ProjectsDelegate(projects_view)
        projects_view.setItemDelegate(projects_delegate)
        projects_view.activate_flick_charm()
        projects_view.set_deselectable(True)

        projects_model = ProjectsQtModel(controller)
        projects_proxy_model = ProjectSortFilterProxy()
        projects_proxy_model.setSourceModel(projects_model)
        projects_view.setModel(projects_proxy_model)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(projects_view, 1)

        projects_view.selectionModel().selectionChanged.connect(
            self._on_selection_change
        )
        projects_view.double_clicked.connect(self.double_clicked)
        projects_model.refreshed.connect(self._on_model_refresh)

        controller.register_event_callback(
            "projects.refresh.finished",
            self._on_projects_refresh_finished
        )

        self._controller = controller

        self._projects_view = projects_view
        self._projects_model = projects_model
        self._projects_proxy_model = projects_proxy_model
        self._projects_delegate = projects_delegate

    def refresh(self):
        self._projects_model.refresh()

    def has_content(self) -> bool:
        """Model has at least one project.

        Returns:
             bool: True if there is any content in the model.

        """
        return self._projects_model.has_content()

    def set_name_filter(self, text: str):
        self._projects_proxy_model.setFilterFixedString(text)

    def get_selected_project(self) -> Optional[str]:
        selection_model = self._projects_view.selectionModel()
        for index in selection_model.selectedIndexes():
            project_name = index.data(PROJECT_NAME_ROLE)
            if project_name:
                return project_name
        return None

    def set_selected_project(self, project_name: Optional[str]):
        if project_name is None:
            self._projects_view.clearSelection()
            self._projects_view.setCurrentIndex(QtCore.QModelIndex())
            return

        index = self._projects_model.get_index_by_project_name(project_name)
        if not index.isValid():
            return
        proxy_index = self._projects_proxy_model.mapFromSource(index)
        if proxy_index.isValid():
            selection_model = self._projects_view.selectionModel()
            selection_model.select(
                proxy_index,
                QtCore.QItemSelectionModel.ClearAndSelect
            )

    def _on_model_refresh(self):
        self._projects_proxy_model.sort(0)
        self._projects_proxy_model.invalidateFilter()
        self.refreshed.emit()

    def _on_selection_change(self, new_selection, _old_selection):
        project_name = None
        for index in new_selection.indexes():
            name = index.data(PROJECT_NAME_ROLE)
            if name:
                project_name = name
                break
        self.selection_changed.emit(project_name or "")
        self._controller.set_selected_project(project_name)

    def _on_projects_refresh_finished(self, event):
        if event["sender"] != PROJECTS_MODEL_SENDER:
            self._projects_model.refresh()

