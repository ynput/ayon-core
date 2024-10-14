# -*- coding: utf-8 -*-
import os
import functools
from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core.style import get_objected_colors
from ayon_core.tools import resources
from ayon_core.tools.flickcharm import FlickCharm
from ayon_core.tools.utils import (
    IconButton,
    PixmapLabel,
)
from ayon_core.tools.publisher.constants import ResetKeySequence

from .icons import (
    get_pixmap,
    get_icon_path
)

FA_PREFIXES = ["", "fa.", "fa5.", "fa5b.", "fa5s.", "ei.", "mdi."]


def parse_icon_def(
    icon_def, default_width=None, default_height=None, color=None
):
    if not icon_def:
        return None

    if isinstance(icon_def, QtGui.QPixmap):
        return icon_def

    color = color or "white"
    default_width = default_width or 512
    default_height = default_height or 512

    if isinstance(icon_def, QtGui.QIcon):
        return icon_def.pixmap(default_width, default_height)

    try:
        if os.path.exists(icon_def):
            return QtGui.QPixmap(icon_def)
    except Exception:
        # TODO logging
        pass

    for prefix in FA_PREFIXES:
        try:
            icon_name = "{}{}".format(prefix, icon_def)
            icon = qtawesome.icon(icon_name, color=color)
            return icon.pixmap(default_width, default_height)
        except Exception:
            # TODO logging
            continue


class PublishPixmapLabel(PixmapLabel):
    def _get_pix_size(self):
        size = self.fontMetrics().height()
        size += size % 2
        return size, size


class IconValuePixmapLabel(PublishPixmapLabel):
    """Label resizing to width and height of font.

    Handle icon parsing from creators/instances. Using of QAwesome module
    of path to images.
    """
    default_size = 200

    def __init__(self, icon_def, parent):
        source_pixmap = self._parse_icon_def(icon_def)

        super().__init__(source_pixmap, parent)

    def set_icon_def(self, icon_def):
        """Set icon by it's definition name.

        Args:
            icon_def (str): Name of FontAwesome icon or path to image.
        """
        source_pixmap = self._parse_icon_def(icon_def)
        self.set_source_pixmap(source_pixmap)

    def _default_pixmap(self):
        pix = QtGui.QPixmap(1, 1)
        pix.fill(QtCore.Qt.transparent)
        return pix

    def _parse_icon_def(self, icon_def):
        icon = parse_icon_def(icon_def, self.default_size, self.default_size)
        if icon:
            return icon
        return self._default_pixmap()


class ContextWarningLabel(PublishPixmapLabel):
    """Pixmap label with warning icon."""
    def __init__(self, parent):
        pix = get_pixmap("warning")

        super().__init__(pix, parent)

        self.setToolTip(
            "Contain invalid context. Please check details."
        )
        self.setObjectName("ProductTypeIconLabel")


class PublishIconBtn(IconButton):
    """Button using alpha of source image to redraw with different color.

    Main class for buttons showed in publisher.

    TODO:
    Add different states:
    - normal           : before publishing
    - publishing       : publishing is running
    - validation error : validation error happened
    - error            : other error happened
    - success          : publishing finished
    """

    def __init__(self, pixmap_path, *args, **kwargs):
        super().__init__(*args, **kwargs)

        colors = get_objected_colors()
        icon = self.generate_icon(
            pixmap_path,
            enabled_color=colors["font"].get_qcolor(),
            disabled_color=colors["font-disabled"].get_qcolor())
        self.setIcon(icon)

    def generate_icon(self, pixmap_path, enabled_color, disabled_color):
        icon = QtGui.QIcon()
        image = QtGui.QImage(pixmap_path)
        enabled_pixmap = self.paint_image_with_color(image, enabled_color)
        icon.addPixmap(enabled_pixmap, QtGui.QIcon.Normal)
        disabled_pixmap = self.paint_image_with_color(image, disabled_color)
        icon.addPixmap(disabled_pixmap, QtGui.QIcon.Disabled)
        return icon

    @staticmethod
    def paint_image_with_color(image, color):
        """Redraw image with single color using it's alpha.

        It is expected that input image is singlecolor image with alpha.

        Args:
            image (QImage): Loaded image with alpha.
            color (QColor): Color that will be used to paint image.
        """
        width = image.width()
        height = image.height()
        partition = 8
        part_w = int(width / partition)
        part_h = int(height / partition)
        part_w -= part_w % 2
        part_h -= part_h % 2
        scaled_image = image.scaled(
            width - (2 * part_w),
            height - (2 * part_h),
            QtCore.Qt.IgnoreAspectRatio,
            QtCore.Qt.SmoothTransformation
        )
        alpha_mask = scaled_image.createAlphaMask()
        alpha_region = QtGui.QRegion(QtGui.QBitmap.fromImage(alpha_mask))
        alpha_region.translate(part_w, part_h)

        pixmap = QtGui.QPixmap(width, height)
        pixmap.fill(QtCore.Qt.transparent)

        painter = QtGui.QPainter(pixmap)
        painter.setClipRegion(alpha_region)
        painter.setPen(QtCore.Qt.NoPen)
        painter.setBrush(color)
        painter.drawRect(QtCore.QRect(0, 0, width, height))
        painter.end()

        return pixmap


class CreateBtn(PublishIconBtn):
    """Create instance button."""

    def __init__(self, parent=None):
        icon_path = get_icon_path("create")
        super().__init__(icon_path, "Create", parent)
        self.setToolTip("Create new product/s")
        self.setLayoutDirection(QtCore.Qt.RightToLeft)


class SaveBtn(PublishIconBtn):
    """Save context and instances information."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("save")
        super().__init__(icon_path, parent)
        self.setToolTip(
            "Save changes ({})".format(
                QtGui.QKeySequence(QtGui.QKeySequence.Save).toString()
            )
        )


class ResetBtn(PublishIconBtn):
    """Publish reset button."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("refresh")
        super().__init__(icon_path, parent)
        self.setToolTip(
            "Reset & discard changes ({})".format(ResetKeySequence.toString())
        )


class StopBtn(PublishIconBtn):
    """Publish stop button."""
    def __init__(self, parent):
        icon_path = get_icon_path("stop")
        super().__init__(icon_path, parent)
        self.setToolTip("Stop/Pause publishing")


class ValidateBtn(PublishIconBtn):
    """Publish validate button."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("validate")
        super().__init__(icon_path, parent)
        self.setToolTip("Validate")


class PublishBtn(PublishIconBtn):
    """Publish start publish button."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("play")
        super().__init__(icon_path, "Publish", parent)
        self.setToolTip("Publish")


class CreateInstanceBtn(PublishIconBtn):
    """Create add button."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("add")
        super().__init__(icon_path, parent)
        self.setToolTip("Create new instance")


class PublishReportBtn(PublishIconBtn):
    """Publish report button."""

    triggered = QtCore.Signal(str)

    def __init__(self, parent=None):
        icon_path = get_icon_path("view_report")
        super().__init__(icon_path, parent)
        self.setToolTip("Copy report")
        self._actions = []

    def add_action(self, label, identifier):
        self._actions.append(
            (label, identifier)
        )

    def _on_action_trigger(self, identifier):
        self.triggered.emit(identifier)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        menu = QtWidgets.QMenu(self)
        actions = []
        for item in self._actions:
            label, identifier = item
            action = QtWidgets.QAction(label, menu)
            action.triggered.connect(
                functools.partial(self._on_action_trigger, identifier)
            )
            actions.append(action)
        menu.addActions(actions)
        menu.exec_(event.globalPos())


class RemoveInstanceBtn(PublishIconBtn):
    """Create remove button."""
    def __init__(self, parent=None):
        icon_path = resources.get_icon_path("delete")
        super().__init__(icon_path, parent)
        self.setToolTip("Remove selected instances")


class ChangeViewBtn(PublishIconBtn):
    """Create toggle view button."""
    def __init__(self, parent=None):
        icon_path = get_icon_path("change_view")
        super().__init__(icon_path, parent)
        self.setToolTip("Swap between views")


class AbstractInstanceView(QtWidgets.QWidget):
    """Abstract class for instance view in creation part."""
    selection_changed = QtCore.Signal()
    # Refreshed attribute is not changed by view itself
    # - widget which triggers `refresh` is changing the state
    # TODO store that information in widget which cares about refreshing
    refreshed = False

    def set_refreshed(self, refreshed):
        """View is refreshed with last instances.

        Views are not updated all the time. Only if are visible.
        """
        self.refreshed = refreshed

    def refresh(self):
        """Refresh instances in the view from current `CreatedContext`."""
        raise NotImplementedError((
            "{} Method 'refresh' is not implemented."
        ).format(self.__class__.__name__))

    def has_items(self):
        """View has at least one item.

        This is more a question for controller but is called from widget
        which should probably should not use controller.

        Returns:
            bool: There is at least one instance or conversion item.
        """

        raise NotImplementedError((
            "{} Method 'has_items' is not implemented."
        ).format(self.__class__.__name__))

    def get_selected_items(self):
        """Selected instances required for callbacks.

        Example: When delete button is clicked to know what should be deleted.
        """

        raise NotImplementedError((
            "{} Method 'get_selected_items' is not implemented."
        ).format(self.__class__.__name__))

    def set_selected_items(
        self, instance_ids, context_selected, convertor_identifiers
    ):
        """Change selection for instances and context.

        Used to applying selection from one view to other.

        Args:
            instance_ids (List[str]): Selected instance ids.
            context_selected (bool): Context is selected.
            convertor_identifiers (List[str]): Selected convertor identifiers.

        """
        raise NotImplementedError((
            "{} Method 'set_selected_items' is not implemented."
        ).format(self.__class__.__name__))

    def set_active_toggle_enabled(self, enabled):
        """Instances are disabled for changing enabled state.

        Active state should stay the same until is "unset".

        Args:
            enabled (bool): Instance state can be changed.
        """

        raise NotImplementedError((
            "{} Method 'set_active_toggle_enabled' is not implemented."
        ).format(self.__class__.__name__))


class ClickableLineEdit(QtWidgets.QLineEdit):
    """QLineEdit capturing left mouse click.

    Triggers `clicked` signal on mouse click.
    """
    clicked = QtCore.Signal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.setReadOnly(True)
        self._mouse_pressed = False

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._mouse_pressed = True
        event.accept()

    def mouseMoveEvent(self, event):
        event.accept()

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed:
            self._mouse_pressed = False
            if self.rect().contains(event.pos()):
                self.clicked.emit()
        event.accept()

    def mouseDoubleClickEvent(self, event):
        event.accept()


class MultipleItemWidget(QtWidgets.QWidget):
    """Widget for immutable text which can have more than one value.

    Content may be bigger than widget's size and does not have scroll but has
    flick widget on top (is possible to move around with clicked mouse).
    """

    def __init__(self, parent):
        super().__init__(parent)

        model = QtGui.QStandardItemModel()

        view = QtWidgets.QListView(self)
        view.setObjectName("MultipleItemView")
        view.setLayoutMode(QtWidgets.QListView.Batched)
        view.setViewMode(QtWidgets.QListView.IconMode)
        view.setResizeMode(QtWidgets.QListView.Adjust)
        view.setWrapping(False)
        view.setSpacing(2)
        view.setModel(model)
        view.setHorizontalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)
        view.setVerticalScrollBarPolicy(QtCore.Qt.ScrollBarAlwaysOff)

        flick = FlickCharm(parent=view)
        flick.activateOn(view)

        layout = QtWidgets.QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(view)

        model.rowsInserted.connect(self._on_insert)

        self._view = view
        self._model = model

        self._value = []

    def _on_insert(self):
        self._update_size()

    def _update_size(self):
        model = self._view.model()
        if model.rowCount() == 0:
            return
        height = self._view.sizeHintForRow(0)
        self.setMaximumHeight(height + (2 * self._view.spacing()))

    def showEvent(self, event):
        super().showEvent(event)
        tmp_item = None
        if not self._value:
            # Add temp item to be able calculate maximum height of widget
            tmp_item = QtGui.QStandardItem("tmp")
            self._model.appendRow(tmp_item)
            self._update_size()

        if tmp_item is not None:
            self._model.clear()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._update_size()

    def set_value(self, value=None):
        """Set value/s of currently selected instance."""
        if value is None:
            value = []
        self._value = value

        self._model.clear()
        for item_text in value:
            item = QtGui.QStandardItem(item_text)
            item.setEditable(False)
            item.setSelectable(False)
            self._model.appendRow(item)


class CreateNextPageOverlay(QtWidgets.QWidget):
    clicked = QtCore.Signal()

    def __init__(self, parent):
        super().__init__(parent)
        self.setCursor(QtCore.Qt.PointingHandCursor)
        self._arrow_color = (
            get_objected_colors("font").get_qcolor()
        )
        self._bg_color = (
            get_objected_colors("bg-buttons").get_qcolor()
        )

        change_anim = QtCore.QVariantAnimation()
        change_anim.setStartValue(0.0)
        change_anim.setEndValue(1.0)
        change_anim.setDuration(200)
        change_anim.setEasingCurve(QtCore.QEasingCurve.OutCubic)

        change_anim.valueChanged.connect(self._on_anim)

        self._change_anim = change_anim
        self._is_visible = None
        self._anim_value = 0.0
        self._increasing = False
        self._under_mouse = None
        self._handle_show_on_own = True
        self._mouse_pressed = False
        self.set_visible(True)

    def set_increasing(self, increasing):
        if self._increasing is increasing:
            return
        self._increasing = increasing
        if increasing:
            self._change_anim.setDirection(QtCore.QAbstractAnimation.Forward)
        else:
            self._change_anim.setDirection(QtCore.QAbstractAnimation.Backward)

        if self._change_anim.state() != QtCore.QAbstractAnimation.Running:
            self._change_anim.start()

    def set_visible(self, visible):
        if self._is_visible is visible:
            return

        self._is_visible = visible
        if not visible:
            self.set_increasing(False)
            if not self._is_anim_finished():
                return

        self.setVisible(visible)
        self._check_anim_timer()

    def _is_anim_finished(self):
        if self._increasing:
            return self._anim_value == 1.0
        return self._anim_value == 0.0

    def _on_anim(self, value):
        self._check_anim_timer()

        self._anim_value = value

        self.update()

        if not self._is_anim_finished():
            return

        if not self._is_visible:
            self.setVisible(False)

    def set_under_mouse(self, under_mouse):
        if self._under_mouse is under_mouse:
            return

        self._under_mouse = under_mouse
        self.set_increasing(under_mouse)

    def _is_under_mouse(self):
        mouse_pos = self.mapFromGlobal(QtGui.QCursor.pos())
        under_mouse = self.rect().contains(mouse_pos)
        return under_mouse

    def _check_anim_timer(self):
        if not self.isVisible():
            return

        self.set_increasing(self._under_mouse)

    def mousePressEvent(self, event):
        if event.button() == QtCore.Qt.LeftButton:
            self._mouse_pressed = True
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        if self._mouse_pressed:
            self._mouse_pressed = False
            if self.rect().contains(event.pos()):
                self.clicked.emit()

        super().mouseReleaseEvent(event)

    def paintEvent(self, event):
        painter = QtGui.QPainter()
        painter.begin(self)
        if self._anim_value == 0.0:
            painter.end()
            return

        painter.setClipRect(event.rect())
        painter.setRenderHints(
            QtGui.QPainter.Antialiasing
            | QtGui.QPainter.SmoothPixmapTransform
        )

        painter.setPen(QtCore.Qt.NoPen)

        rect = QtCore.QRect(self.rect())
        rect_width = rect.width()
        rect_height = rect.height()
        radius = rect_width * 0.2

        x_offset = 0
        y_offset = 0
        if self._anim_value != 1.0:
            x_offset += rect_width - (rect_width * self._anim_value)

        arrow_height = rect_height * 0.4
        arrow_half_height = arrow_height * 0.5
        arrow_x_start = x_offset + ((rect_width - arrow_half_height) * 0.5)
        arrow_x_end = arrow_x_start + arrow_half_height
        center_y = rect.center().y()

        painter.setBrush(self._bg_color)
        painter.drawRoundedRect(
            x_offset, y_offset,
            rect_width + radius, rect_height,
            radius, radius
        )

        src_arrow_path = QtGui.QPainterPath()
        src_arrow_path.moveTo(arrow_x_start, center_y - arrow_half_height)
        src_arrow_path.lineTo(arrow_x_end, center_y)
        src_arrow_path.lineTo(arrow_x_start, center_y + arrow_half_height)

        arrow_stroker = QtGui.QPainterPathStroker()
        arrow_stroker.setWidth(min(4, arrow_half_height * 0.2))
        arrow_path = arrow_stroker.createStroke(src_arrow_path)

        painter.fillPath(arrow_path, self._arrow_color)

        painter.end()
