"""Hover card with basic information about a folder or a task.

The card is a small popup shown next to an item view when the mouse stays
on an item for a moment. It shows thumbnail of the entity, its description
and a few facts that help to recognize the entity.

The card never takes focus and is transparent for mouse events, so it
can't get in the way of interaction with the view.
"""
from __future__ import annotations

import re
import traceback
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

import ayon_api
from qtmaterialsymbols import get_icon
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.ui.components.label import AYLabel
from ayon_core.ui.components.user_avatars import UserAvatarCache
from ayon_core.ui.style_types import get_ayon_style_data

from .entity_thumbnails import _ImagesLoading, _load_image

log = Logger.get_logger(__name__)

THUMBNAIL_SIZE = QtCore.QSize(160, 90)
THUMBNAIL_RADIUS = 8
THUMBNAIL_FADE_DURATION = 150
CONTENT_WIDTH = 272
MARGIN = 8
SPACING = 12
DESCRIPTION_LINES = 4
# Facts are shown in a grid under description
FACT_COLUMNS = 2
MAX_FACT_ROWS = 3
# Less facts are shown if entity has a description, to keep the card small
MAX_FACT_ROWS_WITH_DESCRIPTION = 2
FACT_ICON_SIZE = 16
# Icons with darker color would not be readable on the dark background
MIN_ICON_LIGHTNESS = 0.4
# Avatar of a user is shown at the place of fact icon
AVATAR_SIZE = FACT_ICON_SIZE
# Delay of data loading after the mouse entered an item
FETCH_DELAY = 100
# Delay of card show when it was visible a moment ago
QUICK_SHOW_DELAY = 150
QUICK_SHOW_WINDOW = 500


@dataclass
class EntityHoverFact:
    """Short fact about an entity.

    Attributes:
        icon (str): Material symbol name.
        text (str): Text of the fact.
        color (str): Color of the icon, default color is used if empty.
        username (str): Name of user whose avatar is shown instead of
            the icon.
        user_full_name (str): Full name of the user, used for initials
            if the user does not have an avatar.

    """
    icon: str
    text: str
    color: str = ""
    username: str = ""
    user_full_name: str = ""


@dataclass
class EntityHoverInfo:
    """Information shown in the hover card.

    Attributes:
        label (str): Entity label.
        type_name (str): Folder type or task type name.
        type_icon (str): Material symbol name of the type icon.
        description (str): Entity description.
        facts (list[EntityHoverFact]): Facts about the entity ordered by
            importance, only first few are shown.

    """
    label: str
    type_name: str
    type_icon: str
    description: str = ""
    facts: list[EntityHoverFact] = field(default_factory=list)


def _get_icon_pixmap(
    icon_name: str, color: str, size: int, pixel_ratio: float
) -> QtGui.QPixmap:
    """Pixmap of material symbol icon for a size in logical pixels.

    Glyphs rendered directly at a small size are not antialiased well and
    some of them are cut at the edges. The icon is rendered bigger and
    scaled down, which also makes it sharp on screens with scaling.
    """
    key = (icon_name, color, size, pixel_ratio)
    pixmap = _IconsCache.pixmaps.get(key)
    if pixmap is None:
        render_size = max(size * 4, 64)
        # Outlined icons, same as icons of the labels
        pixmap = get_icon(icon_name, color=color, fill=False).pixmap(
            QtCore.QSize(render_size, render_size)
        )
        pixel_size = max(int(round(size * pixel_ratio)), 1)
        pixmap = pixmap.scaled(
            pixel_size,
            pixel_size,
            QtCore.Qt.KeepAspectRatio,
            QtCore.Qt.SmoothTransformation,
        )
        pixmap.setDevicePixelRatio(pixel_ratio)
        _IconsCache.pixmaps[key] = pixmap
    return pixmap


class _IconsCache:
    pixmaps: dict[tuple[str, str, int, float], QtGui.QPixmap] = {}


class _FullNamesCache:
    names: dict[str, str] = {}


def _get_user_full_names(usernames: list[str]) -> list[str]:
    missing = [
        username
        for username in usernames
        if username not in _FullNamesCache.names
    ]
    if missing:
        try:
            for user in ayon_api.get_users(
                usernames=missing, fields={"name", "attrib.fullName"}
            ):
                _FullNamesCache.names[user["name"]] = (
                    user["attrib"].get("fullName") or user["name"]
                )
        except Exception:
            log.debug("Failed to query users.", exc_info=True)

    return [
        _FullNamesCache.names.get(username, username)
        for username in usernames
    ]


def _tags_facts(entity: dict[str, Any]) -> list[EntityHoverFact]:
    tags = entity.get("tags")
    if not tags:
        return []
    return [EntityHoverFact("sell", ", ".join(tags))]


def _frames_facts(attrib: dict[str, Any]) -> list[EntityHoverFact]:
    """Frame range and fps, which are always the first facts."""
    facts = []
    frame_start = attrib.get("frameStart")
    frame_end = attrib.get("frameEnd")
    if frame_start is not None and frame_end is not None:
        duration = frame_end - frame_start + 1
        facts.append(EntityHoverFact(
            "timer", f"{frame_start}-{frame_end} ({duration}f)"
        ))
    fps = attrib.get("fps")
    if fps:
        facts.append(EntityHoverFact("speed", f"{fps:g} fps"))
    return facts


def _status_facts(status_item) -> list[EntityHoverFact]:
    if status_item is None:
        return []
    return [EntityHoverFact(
        status_item.icon or "circle", status_item.name, status_item.color
    )]


def get_folder_hover_info(
    folder_entity: dict[str, Any],
    folder_type_item=None,
    status_item=None,
) -> EntityHoverInfo:
    """Prepare hover card information of a folder.

    Args:
        folder_entity (dict[str, Any]): Folder entity.
        folder_type_item (FolderTypeItem | None): Folder type item.
        status_item (StatusItem | None): Status item.

    Returns:
        EntityHoverInfo: Hover card information.

    """
    attrib = folder_entity.get("attrib") or {}
    facts = _frames_facts(attrib)
    facts.extend(_status_facts(status_item))
    facts.extend(_tags_facts(folder_entity))
    width = attrib.get("resolutionWidth")
    height = attrib.get("resolutionHeight")
    if width and height:
        facts.append(EntityHoverFact("aspect_ratio", f"{width}x{height}"))

    type_icon = "folder"
    if folder_type_item is not None and folder_type_item.icon:
        type_icon = folder_type_item.icon
    return EntityHoverInfo(
        label=folder_entity.get("label") or folder_entity["name"],
        type_name=folder_entity["folderType"],
        type_icon=type_icon,
        description=attrib.get("description") or "",
        facts=facts,
    )


def get_task_hover_info(
    task_entity: dict[str, Any],
    task_type_item=None,
    status_item=None,
) -> EntityHoverInfo:
    """Prepare hover card information of a task.

    Function is querying users, should be called in a thread.

    Args:
        task_entity (dict[str, Any]): Task entity.
        task_type_item (TaskTypeItem | None): Task type item.
        status_item (StatusItem | None): Status item.

    Returns:
        EntityHoverInfo: Hover card information.

    """
    attrib = task_entity.get("attrib") or {}
    facts = _frames_facts(attrib)
    assignees = task_entity.get("assignees") or []
    full_names = _get_user_full_names(assignees)
    if full_names:
        names = full_names[0]
        if len(full_names) > 1:
            names = f"{names} +{len(full_names) - 1}"
        facts.append(EntityHoverFact(
            "person",
            names,
            username=assignees[0],
            user_full_name=full_names[0],
        ))
    facts.extend(_status_facts(status_item))
    facts.extend(_tags_facts(task_entity))
    end_date = attrib.get("endDate")
    if end_date:
        facts.append(EntityHoverFact("event", str(end_date)[:10]))
    priority = attrib.get("priority")
    if priority and priority != "normal":
        facts.append(EntityHoverFact("flag", priority.capitalize()))

    type_icon = "task_alt"
    if task_type_item is not None and task_type_item.icon:
        type_icon = task_type_item.icon
    return EntityHoverInfo(
        label=task_entity.get("label") or task_entity["name"],
        type_name=task_entity["taskType"],
        type_icon=type_icon,
        description=attrib.get("description") or "",
        facts=facts,
    )


class _ClampedText(QtWidgets.QWidget):
    """Word wrapped text limited to a number of lines.

    Last visible line is elided if the text does not fit.
    """

    def __init__(self, max_lines: int, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self._max_lines = max_lines
        self._text = ""
        self._color = QtGui.QColor("#ffffff")
        self._lines: list[str] = []

    def set_text(self, text: str, color: QtGui.QColor) -> None:
        self._text = text
        self._color = color
        self._update_lines()

    def event(self, event: QtCore.QEvent) -> bool:
        if event.type() == QtCore.QEvent.FontChange:
            self._update_lines()
        return super().event(event)

    def _update_lines(self) -> None:
        # Font is not final until the widget is polished
        self.ensurePolished()
        self._lines = self._layout_lines()
        self.setFixedHeight(
            len(self._lines) * self.fontMetrics().lineSpacing()
        )
        self.update()

    def _layout_lines(self) -> list[str]:
        metrics = self.fontMetrics()
        width = self.width()
        lines = []
        paragraphs = [
            line.strip()
            for line in self._text.splitlines()
            if line.strip()
        ]
        for paragraph_idx, paragraph in enumerate(paragraphs):
            layout = QtGui.QTextLayout(paragraph, self.font())
            layout.beginLayout()
            while True:
                line = layout.createLine()
                if not line.isValid():
                    break
                line.setLineWidth(width)
                start = line.textStart()
                end = start + line.textLength()
                if len(lines) + 1 < self._max_lines:
                    lines.append(paragraph[start:end].rstrip())
                    continue

                # Everything remaining goes to the last line
                rest = paragraph[start:]
                if (
                    end < len(paragraph)
                    or paragraph_idx + 1 < len(paragraphs)
                ):
                    rest = paragraph[start:end].rstrip() + "…"
                    # Make sure the ellipsis is always visible
                    while (
                        len(rest) > 1
                        and metrics.horizontalAdvance(rest) > width
                    ):
                        rest = rest[:-2].rstrip() + "…"
                lines.append(rest)
                layout.endLayout()
                return lines
            layout.endLayout()
        return lines

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setPen(self._color)
        metrics = self.fontMetrics()
        pos_y = metrics.ascent()
        for line in self._lines:
            painter.drawText(0, pos_y, line)
            pos_y += metrics.lineSpacing()
        painter.end()


class _ThumbnailWidget(QtWidgets.QWidget):
    """Thumbnail with rounded corners.

    Icon of the entity type on a slightly visible background is shown
    until the thumbnail is set, and for entities without thumbnail.
    """

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setFixedSize(THUMBNAIL_SIZE)

        style_data = get_ayon_style_data("QFrame", "entity-card")
        fade_anim = QtCore.QVariantAnimation(self)
        fade_anim.setStartValue(0.0)
        fade_anim.setEndValue(1.0)
        fade_anim.setDuration(THUMBNAIL_FADE_DURATION)
        fade_anim.valueChanged.connect(self._on_fade_change)

        self._bg_color = QtGui.QColor(
            get_ayon_style_data("QPushButton", "entity-card")[
                "background-color"
            ]
        )
        self._icon_color = QtGui.QColor(style_data["placeholder-icon-color"])
        self._fade_anim = fade_anim
        self._icon_name = ""
        self._icon_pixmap: QtGui.QPixmap | None = None
        self._pixmap: QtGui.QPixmap | None = None
        self._opacity = 1.0

    def get_image_size(self) -> QtCore.QSize:
        """Size of image, in pixels of the screen, filling the widget."""
        return THUMBNAIL_SIZE * self.devicePixelRatioF()

    def set_placeholder_icon(self, icon_name: str) -> None:
        if icon_name == self._icon_name:
            return
        self._icon_name = icon_name
        self._icon_pixmap = None
        self.update()

    def set_image(
        self, image: QtGui.QImage | None, animated: bool = False
    ) -> None:
        """Change the thumbnail.

        Args:
            image (QtGui.QImage | None): Image of size from
                'get_image_size', placeholder is shown without it.
            animated (bool): Fade the image in over the placeholder.

        """
        self._fade_anim.stop()
        self._opacity = 1.0
        self._pixmap = None
        if image is not None and not image.isNull():
            pixmap = QtGui.QPixmap.fromImage(image)
            pixmap.setDevicePixelRatio(
                image.width() / THUMBNAIL_SIZE.width()
            )
            self._pixmap = pixmap
            if animated:
                self._opacity = 0.0
                self._fade_anim.start()
        self.update()

    def _on_fade_change(self, value: float) -> None:
        self._opacity = value
        self.update()

    def _get_icon_pixmap(self) -> QtGui.QPixmap | None:
        if self._icon_pixmap is None and self._icon_name:
            self._icon_pixmap = _get_icon_pixmap(
                self._icon_name,
                self._icon_color.name(),
                int(self.height() * 0.4),
                self.devicePixelRatioF(),
            )
        return self._icon_pixmap

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )
        path = QtGui.QPainterPath()
        path.addRoundedRect(
            QtCore.QRectF(self.rect()), THUMBNAIL_RADIUS, THUMBNAIL_RADIUS
        )
        painter.setClipPath(path)
        if self._pixmap is None or self._opacity < 1.0:
            painter.fillRect(self.rect(), self._bg_color)
            icon_pixmap = self._get_icon_pixmap()
            if icon_pixmap is not None:
                icon_size = icon_pixmap.size() / icon_pixmap.devicePixelRatio()
                painter.drawPixmap(
                    (self.width() - icon_size.width()) // 2,
                    (self.height() - icon_size.height()) // 2,
                    icon_pixmap,
                )
        if self._pixmap is not None:
            painter.setOpacity(self._opacity)
            painter.drawPixmap(self.rect(), self._pixmap)
        painter.end()


class EntityHoverCard(QtWidgets.QWidget):
    """Popup showing information about an entity.

    Left side of the popup is thumbnail of the entity, or icon of its type
    if it does not have any. Right side shows label and type of the
    entity, its description and a grid of facts right under it.
    The description takes only as many lines as it needs, the popup grows
    a little if all of them are used.

    Args:
        parent (QtWidgets.QWidget): Parent widget, the popup is a window
            that stays on top of it.

    """

    def __init__(self, parent: QtWidgets.QWidget):
        super().__init__(parent)
        self.setWindowFlags(
            QtCore.Qt.ToolTip
            | QtCore.Qt.FramelessWindowHint
            | QtCore.Qt.NoDropShadowWindowHint
            | QtCore.Qt.WindowTransparentForInput
        )
        self.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        self.setAttribute(QtCore.Qt.WA_ShowWithoutActivating)
        self.setAttribute(QtCore.Qt.WA_TransparentForMouseEvents)

        thumbnail_widget = _ThumbnailWidget(self)

        content_widget = QtWidgets.QWidget(self)
        content_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        content_widget.setFixedWidth(CONTENT_WIDTH)

        title_widget = QtWidgets.QWidget(content_widget)
        title_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        label_label = AYLabel(
            "",
            bold=True,
            elide_mode=QtCore.Qt.ElideRight,
            parent=title_widget,
        )
        type_label = AYLabel(
            "",
            dim=True,
            rel_text_size=-1,
            parent=title_widget,
        )
        title_layout = QtWidgets.QHBoxLayout(title_widget)
        title_layout.setContentsMargins(0, 0, 0, 0)
        title_layout.setSpacing(8)
        title_layout.addWidget(label_label, 0)
        title_layout.addWidget(type_label, 0)
        title_layout.addStretch(1)

        description_widget = _ClampedText(DESCRIPTION_LINES, content_widget)
        description_widget.setFixedWidth(CONTENT_WIDTH)

        facts_widget = QtWidgets.QWidget(content_widget)
        facts_widget.setAttribute(QtCore.Qt.WA_TranslucentBackground)
        facts_layout = QtWidgets.QGridLayout(facts_widget)
        facts_layout.setContentsMargins(0, 0, 0, 0)
        facts_layout.setHorizontalSpacing(10)
        facts_layout.setVerticalSpacing(5)
        fact_labels = []
        for idx in range(FACT_COLUMNS * MAX_FACT_ROWS):
            fact_label = AYLabel(
                "",
                dim=True,
                icon_size=FACT_ICON_SIZE,
                icon_text_spacing=6,
                rel_text_size=-1,
                elide_mode=QtCore.Qt.ElideRight,
                parent=facts_widget,
            )
            fact_label.setVisible(False)
            facts_layout.addWidget(
                fact_label, idx // FACT_COLUMNS, idx % FACT_COLUMNS
            )
            fact_labels.append(fact_label)
        for column in range(FACT_COLUMNS):
            facts_layout.setColumnStretch(column, 1)

        content_layout = QtWidgets.QVBoxLayout(content_widget)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(6)
        content_layout.addWidget(title_widget, 0)
        content_layout.addWidget(description_widget, 0)
        content_layout.addWidget(facts_widget, 0)
        content_layout.addStretch(1)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(MARGIN, MARGIN, MARGIN, MARGIN)
        layout.setSpacing(SPACING)
        layout.addWidget(thumbnail_widget, 0, QtCore.Qt.AlignTop)
        layout.addWidget(content_widget, 1)

        # Same colors as menus, the popup should look like part of the UI
        self._bg_color = QtGui.QColor(
            get_ayon_style_data("QFrame", "contextual-menu")[
                "background-color"
            ]
        )
        self._border_color = QtGui.QColor(
            get_ayon_style_data("QPushButton", "entity-card")["border-color"]
        )
        self._text_color = QtGui.QColor(
            get_ayon_style_data("QLabel", "entity-label")["color"]
        )

        # Avatars are downloaded in background, initials are shown until
        #   the avatar is available
        avatar_cache = UserAvatarCache(self)
        avatar_cache.avatar_updated.connect(self._on_avatar_updated)

        # Label of the entity is the most visible text
        label_label.set_text_color(self._text_color.name())

        self._thumbnail_widget = thumbnail_widget
        self._label_label = label_label
        self._type_label = type_label
        self._description_widget = description_widget
        self._content_widget = content_widget
        self._facts_widget = facts_widget
        self._fact_labels = fact_labels
        self._avatar_cache = avatar_cache
        self._facts: list[EntityHoverFact] = []

    def set_info(self, info: EntityHoverInfo) -> None:
        """Change information shown in the card.

        Args:
            info (EntityHoverInfo): Information about the entity.

        """
        # Thumbnail is set separately, see 'set_thumbnail'
        self._thumbnail_widget.set_placeholder_icon(info.type_icon)
        self._thumbnail_widget.set_image(None)

        self._label_label.setText(info.label)
        self._type_label.setText(info.type_name)

        # Empty lines would waste the limited space
        description = re.sub(r"\n\s*\n", "\n", info.description.strip())
        self._description_widget.set_text(description, self._text_color)
        self._description_widget.setVisible(bool(description))

        max_rows = MAX_FACT_ROWS
        if description:
            max_rows = MAX_FACT_ROWS_WITH_DESCRIPTION
        self._facts = info.facts[:FACT_COLUMNS * max_rows]
        self._update_facts()
        # Size of the popup is based on the content
        #   - geometry of the widgets is updated explicitly, layouts would
        #       use outdated size hints until the next event loop
        for widget in (
            self._description_widget,
            self._facts_widget,
            self._content_widget,
        ):
            widget.updateGeometry()
        self.setFixedSize(self.layout().sizeHint())

    def get_thumbnail_size(self) -> QtCore.QSize:
        """Size of image expected by 'set_thumbnail'."""
        return self._thumbnail_widget.get_image_size()

    def set_thumbnail(
        self, image: QtGui.QImage | None, animated: bool = False
    ) -> None:
        """Change thumbnail of the entity.

        Args:
            image (QtGui.QImage | None): Thumbnail image, icon of entity
                type is shown without it.
            animated (bool): Fade the thumbnail in, used when the
                thumbnail is loaded after the card was shown.

        """
        self._thumbnail_widget.set_image(image, animated)

    def _update_facts(self) -> None:
        for idx, fact_label in enumerate(self._fact_labels):
            if idx >= len(self._facts):
                fact_label.setVisible(False)
                continue
            fact = self._facts[idx]
            pixmap = None
            if fact.username:
                # Avatar of the user is shown instead of the icon
                pixmap = self._avatar_cache.pixmap(
                    fact.username, fact.user_full_name, AVATAR_SIZE
                )
            if pixmap is None or pixmap.isNull():
                # Color of the dim text is used for icons without color,
                #   and for colors too dark to be visible on the card
                color = fact.color
                if (
                    not color
                    or QtGui.QColor(color).lightnessF() < MIN_ICON_LIGHTNESS
                ):
                    color = fact_label.palette().color(
                        QtGui.QPalette.Active,
                        QtGui.QPalette.PlaceholderText,
                    ).name()
                pixmap = _get_icon_pixmap(
                    fact.icon,
                    color,
                    FACT_ICON_SIZE,
                    self.devicePixelRatioF(),
                )
            fact_label.setText(fact.text)
            fact_label.set_icon(QtGui.QIcon(pixmap))
            fact_label.setVisible(True)

    def _on_avatar_updated(self, username: str) -> None:
        if any(fact.username == username for fact in self._facts):
            self._update_facts()

    def paintEvent(self, event: QtGui.QPaintEvent) -> None:
        painter = QtGui.QPainter(self)
        painter.setRenderHint(QtGui.QPainter.Antialiasing, True)
        painter.setPen(QtGui.QPen(self._border_color, 1))
        painter.setBrush(self._bg_color)
        rect = QtCore.QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.drawRoundedRect(rect, 12, 12)
        painter.end()


class _FetchTask(QtCore.QObject, QtCore.QRunnable):
    finished = QtCore.Signal(str)

    def __init__(self, task_id: str, func: Callable[[], Any]):
        QtCore.QObject.__init__(self)
        QtCore.QRunnable.__init__(self)
        self.setAutoDelete(False)
        self.id = task_id
        self.result = None
        self._func = func

    def run(self) -> None:
        try:
            self.result = self._func()
        except Exception:
            log.debug(
                "Failed to prepare hover card information.\n%s",
                traceback.format_exc(),
            )
        finally:
            self.finished.emit(self.id)


class EntityHoverCardHandler(QtCore.QObject):
    """Show hover card for items of an item view.

    Information and thumbnail for the card are loaded in threads shortly
    after the mouse enters an item, which is earlier than the card is
    shown. The card does not wait for the thumbnail, if it is not loaded
    yet it is filled in when it is ready. The card is
    shown when the mouse stays on the item for tooltip wake up delay and
    is hidden when the mouse leaves the item or user interacts with
    the view.

    The view must have enabled mouse tracking.

    Args:
        view (QtWidgets.QAbstractItemView): View with entity items.
        id_role (int): Item role with entity id.
        info_getter (Callable[[str], EntityHoverInfo | None]): Function to
            receive information for entity id. Is called in a thread.
        thumbnail_getter (Callable[[str], str | None] | None): Function to
            receive path to thumbnail for entity id. Is called in
            a thread.

    """

    def __init__(
        self,
        view: QtWidgets.QAbstractItemView,
        id_role: int,
        info_getter: Callable[[str], Optional[EntityHoverInfo]],
        thumbnail_getter: Optional[Callable[[str], Optional[str]]] = None,
    ):
        super().__init__(view)
        # Images are loaded in threads
        _ImagesLoading.warm_up()

        fetch_timer = QtCore.QTimer(self)
        fetch_timer.setSingleShot(True)
        fetch_timer.setInterval(FETCH_DELAY)
        fetch_timer.timeout.connect(self._on_fetch_timeout)

        show_timer = QtCore.QTimer(self)
        show_timer.setSingleShot(True)
        show_timer.timeout.connect(self._on_show_timeout)

        threadpool = QtCore.QThreadPool(self)
        threadpool.setMaxThreadCount(2)

        view.entered.connect(self._on_item_entered)
        view.viewportEntered.connect(self.reset_hover)
        view.installEventFilter(self)
        view.viewport().installEventFilter(self)

        self._view = view
        self._id_role = id_role
        self._info_getter = info_getter
        self._thumbnail_getter = thumbnail_getter

        self._fetch_timer = fetch_timer
        self._show_timer = show_timer
        self._threadpool = threadpool

        self._card: EntityHoverCard | None = None
        self._card_entity_id: str | None = None
        self._hover_id: str | None = None
        self._hover_index = QtCore.QPersistentModelIndex()
        self._show_requested = False
        self._hidden_timer = QtCore.QElapsedTimer()

        self._generation = 0
        self._info_by_id: dict[str, EntityHoverInfo | None] = {}
        self._images_by_id: dict[str, QtGui.QImage | None] = {}
        # Task ids of running tasks
        self._fetching: set[str] = set()
        self._tasks: dict[str, _FetchTask] = {}

    def clear_cache(self) -> None:
        """Forget loaded information, e.g. when the view was refreshed."""
        self._generation += 1
        self._info_by_id = {}
        self._images_by_id = {}
        self._fetching = set()
        self.reset_hover()

    def reset_hover(self) -> None:
        """Hide the card and forget which item is hovered."""
        self._hover_id = None
        self._hover_index = QtCore.QPersistentModelIndex()
        self._show_requested = False
        self._fetch_timer.stop()
        self._show_timer.stop()
        self._hide_card()

    def show_for_index(self, index: QtCore.QModelIndex) -> bool:
        """Show the card for an index if its information is loaded.

        Args:
            index (QtCore.QModelIndex): Index of the view's model.

        Returns:
            bool: Card is shown.

        """
        entity_id = index.data(self._id_role)
        info = self._info_by_id.get(entity_id)
        if info is None:
            return False
        if self._card is None:
            self._card = EntityHoverCard(self._view.window())
        self._card_entity_id = entity_id
        self._card.set_info(info)
        self._card.set_thumbnail(self._images_by_id.get(entity_id))
        self._card.move(self._get_card_pos(index, self._card.size()))
        self._card.show()
        return True

    def eventFilter(self, obj: QtCore.QObject, event: QtCore.QEvent) -> bool:
        event_type = event.type()
        if obj is self._view:
            if event_type in (
                QtCore.QEvent.KeyPress,
                QtCore.QEvent.Hide,
                QtCore.QEvent.WindowDeactivate,
            ):
                self.reset_hover()
            return False

        if event_type in (
            QtCore.QEvent.Leave,
            QtCore.QEvent.MouseButtonPress,
            QtCore.QEvent.MouseButtonDblClick,
            QtCore.QEvent.Wheel,
        ):
            self.reset_hover()

        elif event_type == QtCore.QEvent.ToolTip:
            # Card replaces the tooltip of the entity, unless there is
            #   nothing to show in the card
            index = self._view.indexAt(event.pos())
            entity_id = index.data(self._id_role)
            if (
                index.column() == 0
                and entity_id
                and self._info_by_id.get(entity_id, True) is not None
            ):
                return True
        return False

    def _on_item_entered(self, index: QtCore.QModelIndex) -> None:
        entity_id = None
        if index.column() == 0:
            entity_id = index.data(self._id_role)
        if not entity_id:
            self.reset_hover()
            return
        if entity_id == self._hover_id:
            return

        was_visible = self._card is not None and self._card.isVisible()
        self._hide_card()
        self._hover_id = entity_id
        self._hover_index = QtCore.QPersistentModelIndex(index)
        self._show_requested = False
        self._fetch_timer.start()

        # Show the card faster when user moves from item to item
        delay = self._view.style().styleHint(
            QtWidgets.QStyle.SH_ToolTip_WakeUpDelay
        )
        if was_visible or (
            self._hidden_timer.isValid()
            and self._hidden_timer.elapsed() < QUICK_SHOW_WINDOW
        ):
            delay = QUICK_SHOW_DELAY
        self._show_timer.start(delay)

    def _on_fetch_timeout(self) -> None:
        entity_id = self._hover_id
        if not entity_id:
            return
        if entity_id not in self._info_by_id:
            self._start_task(
                "info", entity_id, lambda: self._info_getter(entity_id)
            )
        if (
            self._thumbnail_getter is not None
            and entity_id not in self._images_by_id
        ):
            self._start_task(
                "thumbnail", entity_id, self._get_thumbnail_loader(entity_id)
            )

    def _get_thumbnail_loader(
        self, entity_id: str
    ) -> Callable[[], Optional[QtGui.QImage]]:
        size = QtCore.QSize(THUMBNAIL_SIZE)
        size *= self._view.devicePixelRatioF()
        thumbnail_getter = self._thumbnail_getter

        def _load_thumbnail() -> Optional[QtGui.QImage]:
            path = thumbnail_getter(entity_id)
            if not path:
                return None
            return _load_image(path, size)

        return _load_thumbnail

    def _start_task(
        self, kind: str, entity_id: str, func: Callable[[], Any]
    ) -> None:
        task_id = f"{self._generation}|{kind}|{entity_id}"
        if task_id in self._fetching:
            return
        self._fetching.add(task_id)
        task = _FetchTask(task_id, func)
        self._tasks[task_id] = task
        task.finished.connect(self._on_task_finished)
        self._threadpool.start(task)

    def _on_task_finished(self, task_id: str) -> None:
        task = self._tasks.pop(task_id)
        generation, kind, entity_id = task_id.split("|", 2)
        if int(generation) != self._generation:
            return
        self._fetching.discard(task_id)
        if kind == "info":
            self._info_by_id[entity_id] = task.result
            if entity_id == self._hover_id and self._show_requested:
                self._show_hovered()
            return

        self._images_by_id[entity_id] = task.result
        # Thumbnail was loaded after the card was shown
        if (
            self._card is not None
            and self._card.isVisible()
            and self._card_entity_id == entity_id
        ):
            self._card.set_thumbnail(task.result, animated=True)

    def _on_show_timeout(self) -> None:
        self._show_requested = True
        self._show_hovered()

    def _show_hovered(self) -> None:
        index = QtCore.QModelIndex(self._hover_index)
        viewport = self._view.viewport()
        if (
            not index.isValid()
            or not viewport.underMouse()
            or not self._view.window().isActiveWindow()
        ):
            return
        # Make sure the mouse is still on the item
        pos = viewport.mapFromGlobal(QtGui.QCursor.pos())
        hovered_index = self._view.indexAt(pos)
        if hovered_index.data(self._id_role) != self._hover_id:
            return
        self.show_for_index(index)

    def _hide_card(self) -> None:
        if self._card is not None and self._card.isVisible():
            self._card.hide()
            self._hidden_timer.restart()

    def _get_card_pos(
        self, index: QtCore.QModelIndex, size: QtCore.QSize
    ) -> QtCore.QPoint:
        """Position of the card next to the view at the item height.

        The card is placed out of the view so it does not cover its items,
        on the right side if there is enough space on the screen, on the
        left side otherwise. It is placed under the item if it does not
        fit to any side of the view.
        """
        view = self._view
        viewport = view.viewport()
        item_rect = view.visualRect(index)
        view_top_left = view.mapToGlobal(QtCore.QPoint(0, 0))
        item_center = viewport.mapToGlobal(item_rect.center())

        screen = view.screen().availableGeometry()
        gap = 6
        pos_y = item_center.y() - (size.height() // 2)
        pos_x = view_top_left.x() + view.width() + gap
        if pos_x + size.width() > screen.right():
            pos_x = view_top_left.x() - gap - size.width()
        if pos_x < screen.left():
            item_bottom_left = viewport.mapToGlobal(item_rect.bottomLeft())
            pos_x = min(
                item_bottom_left.x(), screen.right() - size.width()
            )
            pos_y = item_bottom_left.y() + gap
            if pos_y + size.height() > screen.bottom():
                pos_y = item_bottom_left.y() - (
                    item_rect.height() + gap + size.height()
                )

        pos_y = min(pos_y, screen.bottom() - size.height())
        pos_y = max(pos_y, screen.top())
        return QtCore.QPoint(max(pos_x, screen.left()), pos_y)
