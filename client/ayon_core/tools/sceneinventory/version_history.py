"""Panel with version history of the product of selected containers."""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Iterable, Optional

from qtpy import QtCore, QtGui, QtWidgets, shiboken

from ayon_core.lib import Logger
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.tools.utils.activity_widget import ActivityWidget
from ayon_core.tools.utils.delegates import StatusDelegate, pretty_date
from ayon_core.tools.utils.lib import format_version, get_qt_icon
from ayon_core.ui.components.task_queue import AsyncTask, get_task_queue
from ayon_core.ui.components.user_avatars import UserAvatarCache

from .models import VersionHistoryContext, VersionHistoryItem

if TYPE_CHECKING:
    from ayon_core.tools.common_models.activities import ActivitiesModel

    from .control import SceneInventoryController

log = Logger.get_logger(__name__)

VERSION_ID_ROLE = QtCore.Qt.UserRole + 1
IS_LOADED_ROLE = QtCore.Qt.UserRole + 2
IS_LATEST_ROLE = QtCore.Qt.UserRole + 3
IS_HERO_ROLE = QtCore.Qt.UserRole + 4
STATUS_NAME_ROLE = QtCore.Qt.UserRole + 5
STATUS_SHORT_ROLE = QtCore.Qt.UserRole + 6
STATUS_COLOR_ROLE = QtCore.Qt.UserRole + 7
STATUS_ICON_ROLE = QtCore.Qt.UserRole + 8
AUTHOR_NAME_ROLE = QtCore.Qt.UserRole + 9
THUMBNAIL_ROLE = QtCore.Qt.UserRole + 10

LOADED_COLOR = QtGui.QColor("#8fceff")
LATEST_COLOR = QtGui.QColor("#7dd69b")
HERO_COLOR = QtGui.QColor("#b8b8b8")
OUTDATED_COLOR = QtGui.QColor("#f0a34a")

NO_SELECTION_TEXT = "Select a loaded item to see its version history"
NO_ACTIVITY_TEXT = "Select a version to see its activity"


def _parse_date(date_str: str) -> Optional[datetime]:
    """Parse an ISO date to a naive datetime in local time."""
    try:
        date = datetime.fromisoformat(date_str)
    except (TypeError, ValueError):
        return None
    if date.tzinfo is not None:
        date = date.astimezone().replace(tzinfo=None)
    return date


def _format_date(date_str: str) -> str:
    """Format an ISO date to a local date and time.

    Args:
        date_str: Date in ISO format.

    Returns:
        Local date, or the input if it can not be parsed.
    """
    date = _parse_date(date_str)
    if date is None:
        return date_str or ""
    return date.strftime("%Y-%m-%d %H:%M")


def _format_relative_date(
    date_str: str, now: Optional[datetime] = None
) -> str:
    """Format an ISO date relative to now, e.g. '2 days ago'.

    The last day is worded by 'pretty_date' like in the Loader and the
    Browser, older dates are counted in days and then shown as a date.

    Args:
        date_str: Date in ISO format.
        now: Local time to compare to, current time by default.

    Returns:
        Relative date, or the input if it can not be parsed.
    """
    date = _parse_date(date_str)
    if date is None:
        return date_str or ""
    if now is None:
        now = datetime.now()
    days = (now - date).days
    if days < 1:
        return pretty_date(date, now=now)
    if days == 1:
        return "yesterday"
    if days < 31:
        return f"{days} days ago"
    return date.strftime("%b %d %Y")


class _ThumbnailDelegate(QtWidgets.QStyledItemDelegate):
    """Paint the version thumbnail fitted into the cell."""

    row_height = 30
    _margin = 2

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        rect = option.rect.adjusted(
            self._margin, self._margin, -self._margin, -self._margin
        )
        if rect.width() <= 0 or rect.height() <= 0:
            return
        painter.save()
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setRenderHint(QtGui.QPainter.SmoothPixmapTransform)
        pixmap = index.data(THUMBNAIL_ROLE)
        if pixmap is None or pixmap.isNull():
            # Keep the place of a missing thumbnail visible
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(QtGui.QColor(255, 255, 255, 14))
            painter.drawRoundedRect(QtCore.QRectF(rect), 3, 3)
        else:
            size = pixmap.size().scaled(
                rect.size(), QtCore.Qt.KeepAspectRatio
            )
            target = QtCore.QRect(QtCore.QPoint(0, 0), size)
            target.moveCenter(rect.center())
            painter.drawPixmap(target, pixmap)
        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        return QtCore.QSize(self.row_height * 16 // 9, self.row_height)


class _UserDelegate(QtWidgets.QStyledItemDelegate):
    """Paint a user as a round avatar followed by the full name.

    Counterpart of the Browser's user column for a standard item view.
    The name is clipped instead of elided, so a narrow column degrades to
    the avatar alone.

    Args:
        avatar_cache: Source of avatars, the view should repaint when it
            emits 'avatar_updated'.
        parent: Parent object.
    """

    _avatar_size = 18
    _spacing = 6

    def __init__(
        self,
        avatar_cache: UserAvatarCache,
        parent: Optional[QtCore.QObject] = None,
    ) -> None:
        super().__init__(parent)
        self._avatar_cache = avatar_cache

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        label = opt.text
        # Only the background is painted by the style
        opt.text = ""
        widget = opt.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        style.drawControl(
            QtWidgets.QStyle.CE_ItemViewItem, opt, painter, widget
        )
        user_name = index.data(AUTHOR_NAME_ROLE)
        if not user_name:
            return

        margin = style.pixelMetric(
            QtWidgets.QStyle.PM_FocusFrameHMargin, opt, widget
        ) + 1
        rect = opt.rect.adjusted(margin, 0, -margin, 0)
        size = min(self._avatar_size, rect.height())
        painter.save()
        painter.setClipRect(opt.rect)
        left = rect.left()
        avatar = self._avatar_cache.pixmap(user_name, label, size)
        if avatar is not None and not avatar.isNull():
            painter.drawPixmap(
                QtCore.QRect(
                    left, rect.center().y() - size // 2, size, size
                ),
                avatar,
            )
            left += size + self._spacing
        text_rect = QtCore.QRect(rect)
        text_rect.setLeft(left)
        text_rect.setRight(opt.rect.right() + 1000)
        color_role = QtGui.QPalette.Text
        if opt.state & QtWidgets.QStyle.State_Selected:
            color_role = QtGui.QPalette.HighlightedText
        painter.setFont(opt.font)
        painter.setPen(opt.palette.color(color_role))
        painter.drawText(
            text_rect, QtCore.Qt.AlignVCenter | QtCore.Qt.AlignLeft, label
        )
        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        size = super().sizeHint(option, index)
        size.setWidth(size.width() + self._avatar_size + self._spacing)
        return size


class _VersionDelegate(QtWidgets.QStyledItemDelegate):
    """Paint 'loaded', 'latest' and 'hero' tags next to the version."""

    _spacing = 6
    _padding = 5

    def _get_tags(
        self, index: QtCore.QModelIndex
    ) -> list[tuple[str, QtGui.QColor]]:
        tags = []
        if index.data(IS_LOADED_ROLE):
            tags.append(("loaded", LOADED_COLOR))
        if index.data(IS_LATEST_ROLE):
            tags.append(("latest", LATEST_COLOR))
        if index.data(IS_HERO_ROLE):
            tags.append(("hero", HERO_COLOR))
        return tags

    def _get_tag_font(self, font: QtGui.QFont) -> QtGui.QFont:
        font = QtGui.QFont(font)
        font.setBold(False)
        if font.pointSizeF() > 0:
            font.setPointSizeF(font.pointSizeF() * 0.85)
        return font

    def _text_margin(self, option: QtWidgets.QStyleOptionViewItem) -> int:
        widget = option.widget
        style = widget.style() if widget else QtWidgets.QApplication.style()
        return style.pixelMetric(
            QtWidgets.QStyle.PM_FocusFrameHMargin, option, widget
        ) + 1

    def paint(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        super().paint(painter, option, index)
        tags = self._get_tags(index)
        if not tags:
            return

        opt = QtWidgets.QStyleOptionViewItem(option)
        self.initStyleOption(opt, index)
        pos_x = (
            opt.rect.left()
            + self._text_margin(opt)
            + opt.fontMetrics.horizontalAdvance(opt.text)
            + self._spacing
        )
        font = self._get_tag_font(opt.font)
        metrics = QtGui.QFontMetrics(font)
        height = metrics.height() + 2
        pos_y = opt.rect.center().y() - height // 2

        painter.save()
        painter.setClipRect(opt.rect)
        painter.setRenderHint(QtGui.QPainter.Antialiasing)
        painter.setFont(font)
        for text, color in tags:
            width = metrics.horizontalAdvance(text) + 2 * self._padding
            rect = QtCore.QRectF(pos_x, pos_y, width, height)
            bg_color = QtGui.QColor(color)
            bg_color.setAlpha(45)
            painter.setPen(QtCore.Qt.NoPen)
            painter.setBrush(bg_color)
            painter.drawRoundedRect(rect, height / 2, height / 2)
            painter.setPen(color)
            painter.drawText(rect, QtCore.Qt.AlignCenter, text)
            pos_x += width + self._spacing
        painter.restore()

    def sizeHint(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> QtCore.QSize:
        size = super().sizeHint(option, index)
        metrics = QtGui.QFontMetrics(self._get_tag_font(option.font))
        for text, _color in self._get_tags(index):
            size.setWidth(
                size.width()
                + metrics.horizontalAdvance(text)
                + 2 * self._padding
                + self._spacing
            )
        return size


class VersionHistoryWidget(QtWidgets.QWidget):
    """Version history of the product of selected containers.

    Lists versions of the product from the newest to the oldest, marking
    the loaded and the latest one, next to the activity of the version
    selected in the list. Versions are fetched in the background and only
    while the widget is visible, so it is free to keep hidden.

    Args:
        controller: Scene inventory controller.
        activities_model: Model used to fetch activity of a version,
            created if not passed.
        parent: Parent widget.
    """

    column_labels = ("", "Version", "Status", "Author", "Date", "Comment")
    thumbnail_col = 0
    version_col = 1
    status_col = 2
    author_col = 3
    date_col = 4
    comment_col = 5

    def __init__(
        self,
        controller: SceneInventoryController,
        activities_model: ActivitiesModel | None = None,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)

        title_label = QtWidgets.QLabel(self)
        title_label.setTextFormat(QtCore.Qt.RichText)
        summary_label = QtWidgets.QLabel(self)
        summary_label.setTextFormat(QtCore.Qt.RichText)

        header_layout = QtWidgets.QHBoxLayout()
        header_layout.setContentsMargins(2, 0, 2, 0)
        header_layout.addWidget(title_label, 1)
        header_layout.addWidget(summary_label, 0)

        message_label = QtWidgets.QLabel(self)
        message_label.setAlignment(QtCore.Qt.AlignCenter)
        message_label.setWordWrap(True)
        message_label.setEnabled(False)

        versions_view = QtWidgets.QTreeView(self)
        versions_view.setRootIsDecorated(False)
        versions_view.setIndentation(0)
        versions_view.setAlternatingRowColors(True)
        versions_view.setUniformRowHeights(True)
        versions_view.setEditTriggers(
            QtWidgets.QAbstractItemView.NoEditTriggers
        )
        versions_view.setSelectionMode(
            QtWidgets.QAbstractItemView.SingleSelection
        )
        versions_model = QtGui.QStandardItemModel(versions_view)
        versions_model.setHorizontalHeaderLabels(list(self.column_labels))
        versions_view.setModel(versions_model)
        version_delegate = _VersionDelegate(versions_view)
        versions_view.setItemDelegateForColumn(
            self.version_col, version_delegate
        )
        thumbnail_delegate = _ThumbnailDelegate(versions_view)
        # Same delegate as the status column of the containers view
        status_delegate = StatusDelegate(
            STATUS_NAME_ROLE,
            STATUS_SHORT_ROLE,
            STATUS_COLOR_ROLE,
            STATUS_ICON_ROLE,
            versions_view,
        )
        avatar_cache = UserAvatarCache(self)
        user_delegate = _UserDelegate(avatar_cache, versions_view)
        for col, delegate in (
            (self.thumbnail_col, thumbnail_delegate),
            (self.status_col, status_delegate),
            (self.author_col, user_delegate),
        ):
            versions_view.setItemDelegateForColumn(col, delegate)
        header = versions_view.header()
        header.setStretchLastSection(True)
        for col, width in (
            (self.thumbnail_col, 60),
            (self.version_col, 150),
            (self.status_col, 110),
            (self.author_col, 140),
            (self.date_col, 110),
        ):
            versions_view.setColumnWidth(col, width)

        # Avatars are shared with the author column of the version list
        activity_widget = ActivityWidget(
            activities_model=activities_model, avatar_cache=avatar_cache
        )
        activity_widget.setMinimumWidth(200)

        splitter = QtWidgets.QSplitter(QtCore.Qt.Horizontal, self)
        splitter.addWidget(versions_view)
        splitter.addWidget(activity_widget)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 2)
        splitter.setCollapsible(0, False)

        pages = QtWidgets.QStackedWidget(self)
        pages.addWidget(message_label)
        pages.addWidget(splitter)

        layout = QtWidgets.QVBoxLayout(self)
        layout.setContentsMargins(0, 4, 0, 0)
        layout.setSpacing(4)
        layout.addLayout(header_layout, 0)
        layout.addWidget(pages, 1)

        versions_view.selectionModel().selectionChanged.connect(
            self._on_version_selection_change
        )
        avatar_cache.avatar_updated.connect(self._on_avatar_update)

        self._controller = controller
        self._title_label = title_label
        self._summary_label = summary_label
        self._message_label = message_label
        self._versions_view = versions_view
        self._versions_model = versions_model
        self._version_delegate = version_delegate
        self._thumbnail_delegate = thumbnail_delegate
        self._status_delegate = status_delegate
        self._user_delegate = user_delegate
        self._avatar_cache = avatar_cache
        self._activity_widget = activity_widget
        self._pages = pages

        self._task_context_id = f"version_history_{id(self)}"
        self._thumbnails_context_id = f"{self._task_context_id}_thumbnails"
        self._item_ids: set[str] = set()
        self._context: VersionHistoryContext | None = None
        self._items: list[VersionHistoryItem] = []
        # Product of versions that are displayed or being fetched
        self._loaded_key: tuple[str, str] | None = None
        # Selection changed while the widget was hidden
        self._dirty = True
        self._populating = False

        self._set_message(NO_SELECTION_TEXT)

    def set_selected_item_ids(self, item_ids: Iterable[str]) -> None:
        """Change containers to show the version history for.

        Args:
            item_ids: Ids of selected container items.
        """
        self._item_ids = set(item_ids)
        self._dirty = True
        if self.isVisible():
            self._update_context()

    def refresh(self) -> None:
        """Fetch versions of the current selection again."""
        self._loaded_key = None
        self._dirty = True
        self._activity_widget.refresh()
        if self.isVisible():
            self._update_context()

    def get_selected_version_id(self) -> str | None:
        """Id of the version selected in the list."""
        index = self._versions_view.currentIndex()
        if not index.isValid():
            return None
        return index.sibling(index.row(), self.version_col).data(
            VERSION_ID_ROLE
        )

    def showEvent(self, event: QtGui.QShowEvent) -> None:
        super().showEvent(event)
        if self._dirty:
            self._update_context()

    def _update_context(self) -> None:
        self._dirty = False
        contexts = self._controller.get_version_history_contexts(
            self._item_ids
        )
        if len(contexts) != 1:
            self._context = None
            self._loaded_key = None
            self._items = []
            get_task_queue().clear_context_tasks(self._task_context_id)
            if contexts:
                self._set_message(
                    f"{len(contexts)} products selected\n"
                    "Select items of a single product to see"
                    " its version history"
                )
            else:
                self._set_message(NO_SELECTION_TEXT)
            return

        context = contexts[0]
        key = (context.project_name, context.product_id)
        previous_context = self._context
        self._context = context
        if key != self._loaded_key:
            self._load(key)
        elif (
            self._items
            and previous_context is not None
            and previous_context.loaded_version_ids
            != context.loaded_version_ids
        ):
            # Same product with different versions loaded
            self._set_items(self._items)

    def _load(self, key: tuple[str, str]) -> None:
        self._loaded_key = key
        self._items = []
        self._set_message("Loading versions…", keep_title=True)

        task_queue = get_task_queue()
        # Only the latest selection is relevant
        task_queue.clear_context_tasks(self._task_context_id)
        controller = self._controller
        widget = self

        def _fetch() -> list[VersionHistoryItem] | None:
            try:
                return controller.get_version_history_items(*key)
            except Exception:
                log.warning("Failed to fetch versions", exc_info=True)
                return None

        def _on_loaded(items: list[VersionHistoryItem] | None) -> None:
            if not shiboken.isValid(widget) or widget._loaded_key != key:
                return
            if items is None:
                # Allow to retry by selecting the item again
                widget._loaded_key = None
                widget._set_message(
                    "Could not load versions", keep_title=True
                )
                return
            widget._set_items(items)

        task_queue.enqueue(
            AsyncTask(
                name="scene_inventory_version_history",
                function=_fetch,
                callback=_on_loaded,
                priority=1,
                context_id=self._task_context_id,
                cancellable=True,
            )
        )

    def _set_message(self, text: str, keep_title: bool = False) -> None:
        get_task_queue().clear_context_tasks(self._thumbnails_context_id)
        self._versions_model.removeRows(0, self._versions_model.rowCount())
        self._message_label.setText(text)
        self._pages.setCurrentIndex(0)
        self._summary_label.setText("")
        self._update_title(keep_title)
        self._activity_widget.set_context(None, [], NO_ACTIVITY_TEXT)

    def _update_title(self, show_context: bool = True) -> None:
        context = self._context
        if context is None or not show_context:
            self._title_label.setText("<b>Version history</b>")
            return
        self._title_label.setText(
            f"<b>{context.product_name}</b>"
            f"&nbsp;&nbsp;<span style='color: #999999;'>"
            f"{context.folder_path}</span>"
        )

    def _update_summary(self) -> None:
        context = self._context
        loaded = [
            item
            for item in self._items
            if item.version_id in context.loaded_version_ids
        ]
        versions = [item for item in self._items if not item.is_hero]
        count = len(versions)
        text = f"{count} version{'' if count == 1 else 's'}"
        loaded_versions = [item for item in loaded if not item.is_hero]
        if loaded_versions and versions:
            # The oldest loaded version defines how far behind the scene is
            oldest = min(item.version for item in loaded_versions)
            behind = sum(1 for item in versions if item.version > oldest)
            if behind:
                text += (
                    f" · <span style='color: {OUTDATED_COLOR.name()};'>"
                    f"{behind} newer than loaded</span>"
                )
            else:
                text += (
                    f" · <span style='color: {LATEST_COLOR.name()};'>"
                    "up to date</span>"
                )
        self._summary_label.setText(text)

    def _set_items(self, items: list[VersionHistoryItem]) -> None:
        self._items = list(items)
        context = self._context
        if context is None:
            return
        if not items:
            self._set_message("Product has no versions", keep_title=True)
            return

        status_items = {}
        try:
            status_items = {
                status_item.name: status_item
                for status_item in self._controller.get_project_status_items(
                    context.project_name
                )
            }
        except Exception:
            log.debug("Failed to get project statuses", exc_info=True)
        status_icons: dict[str, QtGui.QIcon] = {}

        model = self._versions_model
        # Activity is updated once, after the loaded version is selected
        self._populating = True
        model.removeRows(0, model.rowCount())
        bold_font = self._versions_view.font()
        bold_font.setBold(True)
        select_row = 0
        loaded_found = False
        for row, item in enumerate(items):
            is_loaded = item.version_id in context.loaded_version_ids
            if is_loaded and not loaded_found:
                loaded_found = True
                select_row = row

            thumbnail_item = QtGui.QStandardItem()
            version_item = QtGui.QStandardItem(format_version(item.version))
            version_item.setData(item.version_id, VERSION_ID_ROLE)
            version_item.setData(is_loaded, IS_LOADED_ROLE)
            version_item.setData(item.is_latest, IS_LATEST_ROLE)
            version_item.setData(item.is_hero, IS_HERO_ROLE)
            status_item = QtGui.QStandardItem()
            status_item.setToolTip(item.status)
            status_item.setData(item.status, STATUS_NAME_ROLE)
            status_def = status_items.get(item.status)
            if status_def is not None:
                if item.status not in status_icons:
                    status_icons[item.status] = get_qt_icon(
                        MaterialSymbolsIcon(
                            status_def.icon, color=status_def.color
                        )
                    )
                status_item.setData(status_def.short, STATUS_SHORT_ROLE)
                status_item.setData(status_def.color, STATUS_COLOR_ROLE)
                status_item.setData(
                    status_icons[item.status], STATUS_ICON_ROLE
                )
            author_item = QtGui.QStandardItem(item.author)
            author_item.setData(item.author_name, AUTHOR_NAME_ROLE)
            author_item.setToolTip(item.author_name)
            date_item = QtGui.QStandardItem(
                _format_relative_date(item.created_at)
            )
            date_item.setToolTip(_format_date(item.created_at))
            comment_item = QtGui.QStandardItem(
                " ".join(item.comment.split())
            )
            comment_item.setToolTip(item.comment)
            row_items = [
                thumbnail_item,
                version_item,
                status_item,
                author_item,
                date_item,
                comment_item,
            ]
            if is_loaded:
                version_item.setData(bold_font, QtCore.Qt.FontRole)
            model.appendRow(row_items)

        self._pages.setCurrentIndex(1)
        self._update_title()
        self._update_summary()
        # Show activity of what is in the scene by default
        index = model.index(select_row, self.version_col)
        self._versions_view.setCurrentIndex(index)
        self._versions_view.scrollTo(index)
        self._populating = False
        self._on_version_selection_change()
        self._load_thumbnails(items)

    def _load_thumbnails(self, items: list[VersionHistoryItem]) -> None:
        task_queue = get_task_queue()
        # Thumbnails of previously displayed versions are not needed
        task_queue.clear_context_tasks(self._thumbnails_context_id)
        key = self._loaded_key
        if key is None:
            return
        project_name = key[0]
        controller = self._controller
        widget = self

        for item in items:
            if not item.thumbnail_id:
                continue

            def _fetch(item: VersionHistoryItem = item) -> str:
                try:
                    return controller.get_version_thumbnail_path(
                        project_name, item.version_id, item.thumbnail_id
                    )
                except Exception:
                    log.debug("Failed to fetch thumbnail", exc_info=True)
                    return ""

            def _on_loaded(
                path: str, item: VersionHistoryItem = item
            ) -> None:
                if (
                    path
                    and shiboken.isValid(widget)
                    and widget._loaded_key == key
                ):
                    widget._set_thumbnail(item.version_id, path)

            task_queue.enqueue(
                AsyncTask(
                    name=f"scene_inventory_thumbnail_{item.version_id}",
                    function=_fetch,
                    callback=_on_loaded,
                    priority=2,
                    context_id=self._thumbnails_context_id,
                    cancellable=True,
                )
            )

    def _set_thumbnail(self, version_id: str, path: str) -> None:
        pixmap = QtGui.QPixmap(path)
        if pixmap.isNull():
            return
        model = self._versions_model
        for row in range(model.rowCount()):
            index = model.index(row, self.version_col)
            if index.data(VERSION_ID_ROLE) == version_id:
                model.setData(
                    model.index(row, self.thumbnail_col),
                    pixmap,
                    THUMBNAIL_ROLE,
                )
                break

    def _on_avatar_update(self, _user_name: str) -> None:
        self._versions_view.viewport().update()

    def _on_version_selection_change(self, *_args) -> None:
        if self._populating:
            return
        context = self._context
        version_id = self.get_selected_version_id()
        if context is None or not version_id:
            self._activity_widget.set_context(None, [], NO_ACTIVITY_TEXT)
            return
        self._activity_widget.set_context(
            context.project_name, [version_id], NO_ACTIVITY_TEXT
        )
