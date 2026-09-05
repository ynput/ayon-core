"""Custom cell painters for the Browser table.

Both delegates here implement ``paint_content``, the hook
:class:`~ayon_core.ui.components.table_view.TableItemDelegate` offers to
columns that want to draw their own foreground while still inheriting the
shared cell background, grid and hover painting.
"""

from __future__ import annotations

import webbrowser
from typing import Any

import arrow
import ayon_api
from qtmaterialsymbols import get_icon
from qtpy import QtCore, QtGui, QtWidgets

from ayon_core.lib import Logger
from ayon_core.tools.utils.delegates import pretty_date
from ayon_core.ui.color_utils import compute_color_for_contrast
from ayon_core.ui.components.user_avatars import UserAvatarCache
from ayon_core.ui.style import get_ayon_style, get_ayon_style_data

log = Logger.get_logger(__name__)

#: Web UI page hosting the details panel for each entity type. Mirrors the
#: frontend's ``buildEntityShareLink``.
_ENTITY_WEB_PAGES = {
    "folder": "overview",
    "task": "overview",
    "product": "products",
    "version": "products",
    "representation": "products",
}


def build_entity_web_url(
    project_name: str,
    entity_type: str,
    entity_id: str,
) -> str | None:
    """Return the AYON web UI URL that opens *entity_id* in its panel.

    Args:
        project_name: Project the entity belongs to.
        entity_type: One of the keys of :data:`_ENTITY_WEB_PAGES`.
        entity_id: Entity ID.

    Returns:
        Absolute URL, or ``None`` when the entity cannot be addressed.
    """
    page = _ENTITY_WEB_PAGES.get(entity_type)
    if not (page and project_name and entity_id):
        return None
    try:
        base_url = ayon_api.get_base_url().rstrip("/")
    except Exception:  # noqa: BLE001 - no connection configured
        log.debug("Could not resolve AYON base URL", exc_info=True)
        return None
    return (
        f"{base_url}/projects/{project_name}/{page}"
        f"?project={project_name}&type={entity_type}&id={entity_id}"
    )


def format_relative_time(timestamp: str) -> str:
    """Return a server timestamp as a relative, human-readable string.

    Shares the legacy Loader's wording by going through the same
    :func:`~ayon_core.tools.utils.delegates.pretty_date` helper the Loader
    Time column uses: "just now", "7 seconds ago", "2:05 hours ago", then
    an absolute date once the timestamp is more than a day old.

    Args:
        timestamp: ISO 8601 timestamp as returned by the server.

    Returns:
        The relative description, or ``""`` when there is no timestamp.
    """
    if not timestamp:
        return ""
    try:
        local = arrow.get(timestamp).to("local")
    except Exception:  # noqa: BLE001 - the server may send anything
        log.debug("Could not parse timestamp %r", timestamp, exc_info=True)
        return str(timestamp)
    # ``pretty_date`` compares against a naive ``datetime.now()``, so hand
    # it a naive datetime that is already in local time.
    return pretty_date(local.naive)


def open_entity_url(url: str) -> None:
    """Open *url* in the user's default web browser."""
    if not webbrowser.open_new_tab(url):
        log.warning("Failed to open web browser for %r", url)


def column_key_for(index: QtCore.QModelIndex) -> str:
    """Return the model column key for *index*, or ``""``."""
    from ayon_core.ui.components.table_model import PaginatedTableModel

    model = index.model()
    if hasattr(model, "sourceModel"):
        model = model.sourceModel()
    if not isinstance(model, PaginatedTableModel):
        return ""
    columns = model.columns
    column = index.column()
    if 0 <= column < len(columns):
        return columns[column].key
    return ""


def _cursor_pos(view: QtWidgets.QWidget | None) -> QtCore.QPoint:
    """Return the cursor position in *view*'s viewport coordinates."""
    if view is None or not hasattr(view, "viewport"):
        return QtCore.QPoint(-1, -1)
    return view.viewport().mapFromGlobal(QtGui.QCursor.pos())


def _palette_color(token: str, fallback: str) -> QtGui.QColor:
    """Return a resolved colour from the AYON style palette."""
    palette = get_ayon_style().model.palette()
    return QtGui.QColor(palette.get(token, fallback))


def _text_color(
    index: QtCore.QModelIndex,
    styles: dict[str, dict],
) -> QtGui.QColor:
    """Return the foreground colour the shared delegate would use."""
    brush = index.data(QtCore.Qt.ItemDataRole.ForegroundRole)
    if brush is not None:
        return QtGui.QColor(brush.color())
    return QtGui.QColor(styles["base"].get("color", "#f4f5f5"))


class EntityLinkDelegate(QtWidgets.QStyledItemDelegate):
    """Paint an entity cell as a pill that links to the AYON web UI.

    The cell shows the entity-type icon in its anatomy colour followed by
    the entity name.  Hovering highlights the pill and reveals an
    ``open_in_new`` icon; clicking it opens the entity in the user's web
    browser.  The frontend uses ``dock_to_left`` there because it opens an
    in-page side panel - this leaves the application, so it advertises an
    external link instead.

    The name keeps the full cell width: the hover affordance is appended
    after it and clipped at the cell edge rather than shortening the name
    that is on screen all the time.

    Args:
        entity_type: ``"folder"`` or ``"task"``.
        id_key: Row-dict key holding the entity ID.
        variant: AYTableView style variant used to resolve paddings.
        parent: The table view the delegate paints in.
    """

    ICON_SIZE = 16
    SPACING = 4
    PILL_PADDING = 4
    PILL_RADIUS = 4
    OPEN_ICON = "open_in_new"

    def __init__(
        self,
        entity_type: str,
        id_key: str,
        variant: str = "default",
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._entity_type = entity_type
        self._id_key = id_key
        self._variant = variant
        self._padding: tuple[int, int] | None = None

    # -- geometry -------------------------------------------------------

    def content_rect(self, cell_rect: QtCore.QRect) -> QtCore.QRect:
        """Return the padded content area of *cell_rect*.

        Matches the rect the shared table delegate passes to
        :meth:`paint_content`, so hit tests driven from the view agree
        with what was painted.
        """
        if self._padding is None:
            # Resolving style data deep-copies it, and this runs on every
            # mouse move across an entity column.
            style = get_ayon_style_data("AYTableView", self._variant)
            padding = style.get("item-padding", [1, 2])
            self._padding = (int(padding[0]), int(padding[1]))
        pad_v, pad_h = self._padding
        return QtCore.QRect(cell_rect).adjusted(pad_h, pad_v, -pad_h, -pad_v)

    def _layout(
        self,
        content_rect: QtCore.QRect,
        row_data: dict[str, Any],
        column_key: str,
        font: QtGui.QFont,
    ) -> tuple[QtCore.QRect, QtCore.QRect, QtCore.QRect, QtCore.QRect, str]:
        """Return the pill, icon, text and open-icon rects plus the label.

        The label gets the full cell width; the open-icon slot is appended
        after it and is allowed to run past the cell edge, where the
        painter clips it away.  Reserving room for it would shorten every
        name just to keep a hover-only affordance visible.
        """
        icon_name = row_data.get(f"{column_key}__icon") or ""
        label = str(row_data.get(column_key) or "")

        icon_w = self.ICON_SIZE + self.SPACING if icon_name else 0
        max_text_w = max(
            0, content_rect.width() - 2 * self.PILL_PADDING - icon_w
        )
        metrics = QtGui.QFontMetrics(font)
        natural_w = metrics.horizontalAdvance(label)
        text_w = min(max_text_w, natural_w)
        # Only elide when the label really is too wide: asking Qt to elide
        # to its own advance width still costs a couple of characters to
        # make room for the ellipsis.
        text = (
            metrics.elidedText(
                label, QtCore.Qt.TextElideMode.ElideRight, max_text_w
            )
            if natural_w > max_text_w
            else label
        )

        pill_w = (
            2 * self.PILL_PADDING
            + icon_w
            + text_w
            + self.SPACING
            + self.ICON_SIZE
        )
        pill_h = min(content_rect.height(), self.ICON_SIZE + 6)
        pill = QtCore.QRect(
            content_rect.left(),
            content_rect.center().y() - pill_h // 2,
            pill_w,
            pill_h,
        )

        left = pill.left() + self.PILL_PADDING
        icon_rect = QtCore.QRect(
            left,
            pill.center().y() - self.ICON_SIZE // 2,
            self.ICON_SIZE if icon_name else 0,
            self.ICON_SIZE,
        )
        if icon_name:
            left += self.ICON_SIZE + self.SPACING
        text_rect = QtCore.QRect(left, pill.top(), text_w, pill.height())
        open_rect = QtCore.QRect(
            pill.right() - self.PILL_PADDING - self.ICON_SIZE + 1,
            pill.center().y() - self.ICON_SIZE // 2,
            self.ICON_SIZE,
            self.ICON_SIZE,
        )
        return pill, icon_rect, text_rect, open_rect, text

    def _url_at(
        self,
        cell_rect: QtCore.QRect,
        pos: QtCore.QPoint,
        index: QtCore.QModelIndex,
        font: QtGui.QFont | None = None,
    ) -> str | None:
        """Return the URL when *pos* falls on this cell's link pill.

        Args:
            cell_rect: Viewport rect of the cell.
            pos: Cursor position in viewport coordinates.
            index: The cell's index.
            font: Font the cell is laid out with; defaults to the view's.

        Returns:
            The entity URL, or ``None`` when the position misses the pill
            or the row carries no linkable entity.
        """
        column_key = column_key_for(index)
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        if not column_key or not row_data.get(column_key):
            return None
        url = build_entity_web_url(
            row_data.get("project_name", ""),
            self._entity_type,
            row_data.get(self._id_key, ""),
        )
        if not url:
            return None
        if font is None:
            view = self.parent()
            font = view.font() if view is not None else QtGui.QFont()
        pill = self._layout(
            self.content_rect(cell_rect), row_data, column_key, font
        )[0]
        # The pill may run past the cell; only its visible part is
        # clickable.
        return url if pill.intersected(cell_rect).contains(pos) else None

    # -- interaction ----------------------------------------------------

    def cursor_shape_at(
        self,
        cell_rect: QtCore.QRect,
        pos: QtCore.QPoint,
        index: QtCore.QModelIndex,
    ) -> QtCore.Qt.CursorShape | None:
        """Return a hand cursor while the cursor rests on the link pill.

        Called by :class:`~ayon_core.ui.components.table_view.AYTableView`
        as the cursor moves, which also repaints the cell so the pill
        highlight follows.
        """
        if self._url_at(cell_rect, pos, index) is None:
            return None
        return QtCore.Qt.CursorShape.PointingHandCursor

    def editorEvent(
        self,
        event: QtCore.QEvent,
        model: QtCore.QAbstractItemModel,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> bool:
        """Open the entity in a web browser when its pill is clicked.

        Reached through
        :meth:`~ayon_core.ui.components.table_view.TableItemDelegate.
        editorEvent`, which forwards item events to the column's delegate.
        ``option.rect`` is the cell rect, so the hit test runs against the
        same geometry :meth:`paint_content` drew.
        """
        if (
            event.type() != QtCore.QEvent.Type.MouseButtonRelease
            or event.button() != QtCore.Qt.MouseButton.LeftButton
        ):
            return False
        url = self._url_at(option.rect, event.pos(), index, option.font)
        if url is None:
            return False
        open_entity_url(url)
        return True

    # -- painting -------------------------------------------------------

    def paint_content(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
        content_rect: QtCore.QRect,
        styles: dict[str, dict],
    ) -> None:
        """Draw the entity pill for one cell."""
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        column_key = column_key_for(index)
        if not column_key or not row_data.get(column_key):
            return

        font = option.font
        pill, icon_rect, text_rect, open_rect, text = self._layout(
            content_rect, row_data, column_key, font
        )
        color = _text_color(index, styles)
        linkable = bool(
            row_data.get(self._id_key) and row_data.get("project_name")
        )
        hovered = linkable and pill.intersected(option.rect).contains(
            _cursor_pos(self.parent())
        )
        # The pill deliberately overflows narrow cells; clip so it cannot
        # bleed into the neighbouring column.
        painter.setClipRect(
            option.rect, QtCore.Qt.ClipOperation.IntersectClip
        )

        if hovered:
            highlight = QtGui.QColor(color)
            highlight.setAlpha(38)
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(highlight))
            painter.drawRoundedRect(pill, self.PILL_RADIUS, self.PILL_RADIUS)

        icon_name = row_data.get(f"{column_key}__icon") or ""
        if icon_name and icon_rect.width():
            icon_color = (
                row_data.get(f"{column_key}__icon_color") or color.name()
            )
            get_icon(icon_name, color=icon_color).paint(
                painter, icon_rect, QtCore.Qt.AlignmentFlag.AlignCenter
            )

        painter.setFont(font)
        painter.setPen(color)
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignmentFlag.AlignVCenter
            | QtCore.Qt.AlignmentFlag.AlignLeft,
            text,
        )

        if hovered:
            get_icon(self.OPEN_ICON, color=color.name()).paint(
                painter, open_rect, QtCore.Qt.AlignmentFlag.AlignCenter
            )


class TagsDelegate(QtWidgets.QStyledItemDelegate):
    """Paint tags as coloured chips, wrapping to the available row height.

    Chip colours come from the project anatomy tag definitions, supplied
    on the row as ``<key>__chips``.  When the row is tall enough the chips
    wrap onto further lines; chips that still do not fit are summarised by
    a trailing ``+N`` chip.
    """

    CHIP_HEIGHT = 16
    CHIP_PADDING = 5
    CHIP_RADIUS = 4
    GAP = 4

    def paint_content(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
        content_rect: QtCore.QRect,
        styles: dict[str, dict],
    ) -> None:
        """Draw the tag chips for one cell."""
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        column_key = column_key_for(index)
        if not column_key:
            return

        chips = row_data.get(f"{column_key}__chips")
        if chips is None:
            # Rows from providers that only set the joined string (and
            # group-header rows) keep rendering as plain text.
            self._paint_plain(
                painter, option, index, content_rect, styles, column_key
            )
            return
        if not chips:
            return

        font = option.font
        metrics = QtGui.QFontMetrics(font)
        default_bg = QtGui.QColor(
            styles["base"].get("border-color", "#4a4f57")
        )
        line_height = self.CHIP_HEIGHT + self.GAP
        max_lines = max(1, (content_rect.height() + self.GAP) // line_height)
        lines = self._layout_lines(
            chips, content_rect.width(), metrics, int(max_lines)
        )
        block_height = (
            len(lines) * self.CHIP_HEIGHT + (len(lines) - 1) * self.GAP
        )
        top = content_rect.top() + max(
            0, (content_rect.height() - block_height) // 2
        )

        painter.setFont(font)
        for row, line in enumerate(lines):
            x = content_rect.left()
            y = top + row * line_height
            for label, color_name, width in line:
                background = QtGui.QColor(color_name) if color_name else None
                if background is None or not background.isValid():
                    background = default_bg
                rect = QtCore.QRect(x, y, width, self.CHIP_HEIGHT)
                painter.setPen(QtCore.Qt.PenStyle.NoPen)
                painter.setBrush(QtGui.QBrush(background))
                painter.drawRoundedRect(
                    rect, self.CHIP_RADIUS, self.CHIP_RADIUS
                )
                painter.setPen(
                    compute_color_for_contrast(
                        background.toTuple(), (0, 0, 0, 255)
                    )
                )
                # A chip that was not clamped already fits its label, and
                # eliding to its own width would still drop characters to
                # make room for the ellipsis.
                text = label
                if self._chip_width(label, metrics) > width:
                    text = metrics.elidedText(
                        label,
                        QtCore.Qt.TextElideMode.ElideRight,
                        width - 2 * self.CHIP_PADDING,
                    )
                painter.drawText(
                    rect, QtCore.Qt.AlignmentFlag.AlignCenter, text
                )
                x += width + self.GAP

    def _paint_plain(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
        content_rect: QtCore.QRect,
        styles: dict[str, dict],
        column_key: str,
    ) -> None:
        """Fall back to the plain text rendering of the shared delegate."""
        text = str(index.data(QtCore.Qt.ItemDataRole.DisplayRole) or "")
        if not text:
            return
        painter.setFont(option.font)
        painter.setPen(_text_color(index, styles))
        painter.drawText(
            content_rect,
            QtCore.Qt.AlignmentFlag.AlignVCenter
            | QtCore.Qt.AlignmentFlag.AlignLeft,
            QtGui.QFontMetrics(option.font).elidedText(
                text,
                QtCore.Qt.TextElideMode.ElideRight,
                content_rect.width(),
            ),
        )

    def _chip_width(self, label: str, metrics: QtGui.QFontMetrics) -> int:
        return metrics.horizontalAdvance(label) + 2 * self.CHIP_PADDING

    def _layout_lines(
        self,
        chips: list[tuple[str, str]],
        available_width: int,
        metrics: QtGui.QFontMetrics,
        max_lines: int,
    ) -> list[list[tuple[str, str, int]]]:
        """Wrap *chips* into at most *max_lines* rows of chips.

        Chips that do not fit are replaced by a trailing ``+N`` chip so
        the cell always reports how much it is hiding.

        Args:
            chips: ``(label, colour)`` pairs.
            available_width: Width of the cell content area.
            metrics: Font metrics used to measure labels.
            max_lines: Maximum number of chip rows that fit vertically.

        Returns:
            Rows of ``(label, colour, width)`` tuples.
        """
        lines: list[list[tuple[str, str, int]]] = [[]]
        used = 0
        for idx, (label, color_name) in enumerate(chips):
            width = min(
                self._chip_width(label, metrics), max(available_width, 0)
            )
            needed = width + self.GAP if lines[-1] else width
            if used + needed > available_width and lines[-1]:
                if len(lines) >= max_lines:
                    self._append_overflow(
                        lines, len(chips) - idx, available_width, metrics
                    )
                    break
                lines.append([])
                used = 0
                needed = width
            lines[-1].append((label, color_name, width))
            used += needed
        return [line for line in lines if line]

    def _append_overflow(
        self,
        lines: list[list[tuple[str, str, int]]],
        remaining: int,
        available_width: int,
        metrics: QtGui.QFontMetrics,
    ) -> None:
        """Summarise chips that did not fit with a trailing ``+N`` chip.

        One real chip is always kept - an elided tag name says more than a
        bare counter - so the last chip is narrowed rather than dropped
        when that is the only way to fit the counter.
        """
        line = lines[-1]
        label = f"+{remaining}"
        width = self._chip_width(label, metrics)
        used = sum(w for _, _, w in line) + self.GAP * len(line)
        while len(line) > 1 and used + width > available_width:
            used -= line.pop()[2] + self.GAP
            remaining += 1
            label = f"+{remaining}"
            width = self._chip_width(label, metrics)
        if used + width > available_width:
            first_label, first_color, first_width = line[0]
            shrunk = first_width - (used + width - available_width)
            if shrunk < 4 * self.CHIP_PADDING:
                return
            line[0] = (first_label, first_color, shrunk)
        line.append((label, "", width))


class BooleanCheckboxDelegate(QtWidgets.QStyledItemDelegate):
    """Paint a boolean cell as a read-only checkbox, like the frontend.

    Mirrors the frontend's boolean widget: a 16 px rounded square centred
    in the cell, outlined when unchecked and filled with the primary
    colour plus a tick when checked.  Any value the row actually carries
    is rendered, so a false (or empty) attribute shows an unchecked box
    the same way the web UI does.  Rows that do not carry the key at all -
    group headers, folder rows - draw nothing.
    """

    BOX_SIZE = 16
    BOX_RADIUS = 2

    def paint_content(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
        content_rect: QtCore.QRect,
        styles: dict[str, dict],
    ) -> None:
        """Draw the checkbox for one boolean cell."""
        column_key = column_key_for(index)
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        if not column_key or column_key not in row_data:
            return

        size = min(self.BOX_SIZE, content_rect.height())
        box = QtCore.QRect(
            content_rect.center().x() - size // 2,
            content_rect.center().y() - size // 2,
            size,
            size,
        )
        painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
        if row_data[column_key]:
            fill = _palette_color("--md-sys-color-primary-dark", "#8fceff")
            painter.setPen(QtCore.Qt.PenStyle.NoPen)
            painter.setBrush(QtGui.QBrush(fill))
            painter.drawRoundedRect(box, self.BOX_RADIUS, self.BOX_RADIUS)
            tick = compute_color_for_contrast(
                fill.toTuple(), (0, 0, 0, 255)
            )
            pen = QtGui.QPen(tick, max(1.5, size / 9.0))
            pen.setCapStyle(QtCore.Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(QtCore.Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
            painter.drawPolyline(
                QtGui.QPolygonF(
                    [
                        QtCore.QPointF(
                            box.left() + size * 0.26,
                            box.top() + size * 0.52,
                        ),
                        QtCore.QPointF(
                            box.left() + size * 0.43,
                            box.top() + size * 0.70,
                        ),
                        QtCore.QPointF(
                            box.left() + size * 0.75,
                            box.top() + size * 0.31,
                        ),
                    ]
                )
            )
            return

        outline = _palette_color("--md-sys-color-outline-dark", "#8b9198")
        painter.setPen(QtGui.QPen(outline, 1))
        painter.setBrush(QtCore.Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(
            QtCore.QRectF(box).adjusted(0.5, 0.5, -0.5, -0.5),
            self.BOX_RADIUS,
            self.BOX_RADIUS,
        )


class UserDelegate(QtWidgets.QStyledItemDelegate):
    """Paint a user cell as a round avatar followed by the full name.

    The stored value stays the login name so filtering and sorting keep
    matching what the server indexes; the row supplies the display name as
    ``<key>__label``.  Avatars come from a shared
    :class:`~ayon_core.ui.components.user_avatars.UserAvatarCache`, which
    hands out initials immediately and swaps in the downloaded image once
    it arrives.

    The name is never elided: it runs past the cell edge and is clipped
    there, so narrowing the column degrades to the avatar alone instead of
    stopping at a width that still fits an ellipsis.

    Args:
        avatar_cache: Cache shared with the view that repaints on
            :attr:`UserAvatarCache.avatar_updated`.
        parent: The table view the delegate paints in.
    """

    AVATAR_SIZE = 18
    SPACING = 6

    def __init__(
        self,
        avatar_cache: UserAvatarCache,
        parent: QtWidgets.QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._avatars = avatar_cache

    def paint_content(
        self,
        painter: QtGui.QPainter,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
        content_rect: QtCore.QRect,
        styles: dict[str, dict],
    ) -> None:
        """Draw the avatar and name for one user cell."""
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        column_key = column_key_for(index)
        if not column_key:
            return
        user_name = str(row_data.get(column_key) or "")
        if not user_name:
            return
        label = str(row_data.get(f"{column_key}__label") or user_name)

        size = min(self.AVATAR_SIZE, content_rect.height())
        left = content_rect.left()
        avatar = self._avatars.pixmap(user_name, label, size)
        if avatar is not None and not avatar.isNull():
            painter.drawPixmap(
                QtCore.QRect(
                    left,
                    content_rect.center().y() - size // 2,
                    size,
                    size,
                ),
                avatar,
            )
            left += size + self.SPACING

        if left > content_rect.right():
            return
        text_rect = QtCore.QRect(content_rect)
        text_rect.setLeft(left)
        text_rect.setWidth(
            QtGui.QFontMetrics(option.font).horizontalAdvance(label)
        )
        painter.setClipRect(
            option.rect, QtCore.Qt.ClipOperation.IntersectClip
        )
        painter.setFont(option.font)
        painter.setPen(_text_color(index, styles))
        painter.drawText(
            text_rect,
            QtCore.Qt.AlignmentFlag.AlignVCenter
            | QtCore.Qt.AlignmentFlag.AlignLeft,
            label,
        )


class PrettyTimeDelegate(QtWidgets.QStyledItemDelegate):
    """Show a timestamp column the way the legacy Loader's Time column did.

    The row keeps the raw server timestamp so server-side sorting and any
    export stay exact; only the displayed text is relative, and it is
    resolved per paint so "7 seconds ago" keeps counting up rather than
    freezing at the value the row was built with.  The absolute local time
    is supplied separately by the row as ``<key>__tooltip``.
    """

    def initStyleOption(
        self,
        option: QtWidgets.QStyleOptionViewItem,
        index: QtCore.QModelIndex,
    ) -> None:
        """Replace the cell text with its relative description."""
        super().initStyleOption(option, index)
        column_key = column_key_for(index)
        if not column_key:
            return
        row_data = index.data(QtCore.Qt.ItemDataRole.UserRole) or {}
        pretty = format_relative_time(row_data.get(column_key) or "")
        if pretty:
            option.text = pretty
