import os
import sys
import contextlib
from functools import partial

from qtpy import QtWidgets, QtCore, QtGui
import qtawesome

from ayon_core.style import (
    get_default_entity_icon_color,
    get_objected_colors,
    get_app_icon_path,
)
from ayon_core.resources import get_image_path
from ayon_core.lib import Logger

from .constants import CHECKED_INT, UNCHECKED_INT

log = Logger.get_logger(__name__)


def checkstate_int_to_enum(state):
    if not isinstance(state, int):
        return state
    if state == CHECKED_INT:
        return QtCore.Qt.Checked

    if state == UNCHECKED_INT:
        return QtCore.Qt.Unchecked
    return QtCore.Qt.PartiallyChecked


def checkstate_enum_to_int(state):
    if isinstance(state, int):
        return state
    if state == QtCore.Qt.Checked:
        return 0
    if state == QtCore.Qt.PartiallyChecked:
        return 1
    return 2


def center_window(window):
    """Move window to center of it's screen."""

    if hasattr(QtWidgets.QApplication, "desktop"):
        desktop = QtWidgets.QApplication.desktop()
        screen_idx = desktop.screenNumber(window)
        screen_geo = desktop.screenGeometry(screen_idx)
    else:
        screen = window.screen()
        screen_geo = screen.geometry()

    geo = window.frameGeometry()
    geo.moveCenter(screen_geo.center())
    if geo.y() < screen_geo.y():
        geo.setY(screen_geo.y())
    window.move(geo.topLeft())


def html_escape(text):
    """Basic escape of html syntax symbols in text."""

    return (
        text
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
        .replace("'", "&#x27;")
    )


def set_style_property(widget, property_name, property_value):
    """Set widget's property that may affect style.

    If current property value is different then style of widget is polished.
    """
    cur_value = widget.property(property_name)
    if cur_value == property_value:
        return
    widget.setProperty(property_name, property_value)
    style = widget.style()
    style.polish(widget)


def paint_image_with_color(image, color):
    """Redraw image with single color using it's alpha.

    It is expected that input image is singlecolor image with alpha.

    Args:
        image (QImage): Loaded image with alpha.
        color (QColor): Color that will be used to paint image.
    """
    width = image.width()
    height = image.height()

    alpha_mask = image.createAlphaMask()
    alpha_region = QtGui.QRegion(QtGui.QBitmap.fromImage(alpha_mask))

    pixmap = QtGui.QPixmap(width, height)
    pixmap.fill(QtCore.Qt.transparent)

    painter = QtGui.QPainter(pixmap)
    render_hints = (
        QtGui.QPainter.Antialiasing
        | QtGui.QPainter.SmoothPixmapTransform
    )
    # Deprecated since 5.14
    if hasattr(QtGui.QPainter, "HighQualityAntialiasing"):
        render_hints |= QtGui.QPainter.HighQualityAntialiasing
    painter.setRenderHints(render_hints)

    painter.setClipRegion(alpha_region)
    painter.setPen(QtCore.Qt.NoPen)
    painter.setBrush(color)
    painter.drawRect(QtCore.QRect(0, 0, width, height))
    painter.end()

    return pixmap


def format_version(value):
    """Formats integer to displayable version name"""
    value = int(value)  # convert e.g. HeroVersionType to its version value
    label = "v{0:03d}".format(abs(value))
    if value < 0:
        return "[{}]".format(label)
    return label


@contextlib.contextmanager
def qt_app_context():
    app = QtWidgets.QApplication.instance()

    if not app:
        print("Starting new QApplication..")
        app = QtWidgets.QApplication(sys.argv)
        yield app
        app.exec_()
    else:
        print("Using existing QApplication..")
        yield app


def get_qt_app():
    """Get Qt application.

    The function initializes new Qt application if it is not already
    initialized. It also sets some attributes to the application to
    ensure that it will work properly on high DPI displays.

    Returns:
        QtWidgets.QApplication: Current Qt application.
    """

    app = QtWidgets.QApplication.instance()
    if app is None:
        for attr_name in (
            "AA_EnableHighDpiScaling",
            "AA_UseHighDpiPixmaps",
        ):
            attr = getattr(QtCore.Qt, attr_name, None)
            if attr is not None:
                QtWidgets.QApplication.setAttribute(attr)

        policy = os.getenv("QT_SCALE_FACTOR_ROUNDING_POLICY")
        if (
            hasattr(
                QtWidgets.QApplication, "setHighDpiScaleFactorRoundingPolicy"
            )
            and not policy
        ):
            QtWidgets.QApplication.setHighDpiScaleFactorRoundingPolicy(
                QtCore.Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
            )

        app = QtWidgets.QApplication(sys.argv)

    return app


def get_ayon_qt_app():
    """Main Qt application initialized for AYON processed.

    This function should be used only inside AYON-launcher process
        and never inside other processes.
    """

    app = get_qt_app()
    app.setWindowIcon(QtGui.QIcon(get_app_icon_path()))
    return app


def get_openpype_qt_app():
    return get_ayon_qt_app()


def iter_model_rows(model, column, include_root=False):
    """Iterate over all row indices in a model"""
    indices = [QtCore.QModelIndex()]  # start iteration at root

    for index in indices:
        # Add children to the iterations
        child_rows = model.rowCount(index)
        for child_row in range(child_rows):
            child_index = model.index(child_row, column, index)
            indices.append(child_index)

        if not include_root and not index.isValid():
            continue

        yield index


@contextlib.contextmanager
def preserve_expanded_rows(tree_view, column=0, role=None):
    """Preserves expanded row in QTreeView by column's data role.

    This function is created to maintain the expand vs collapse status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vice versa.

    Arguments:
        tree_view (QWidgets.QTreeView): the tree view which is
            nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()

    expanded = set()

    for index in iter_model_rows(model, column=column, include_root=False):
        if tree_view.isExpanded(index):
            value = index.data(role)
            expanded.add(value)

    try:
        yield
    finally:
        if not expanded:
            return

        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in expanded
            if state:
                tree_view.expand(index)
            else:
                tree_view.collapse(index)


@contextlib.contextmanager
def preserve_selection(tree_view, column=0, role=None, current_index=True):
    """Preserves row selection in QTreeView by column's data role.

    This function is created to maintain the selection status of
    the model items. When refresh is triggered the items which are expanded
    will stay expanded and vice versa.

        tree_view (QWidgets.QTreeView): the tree view nested in the application
        column (int): the column to retrieve the data from
        role (int): the role which dictates what will be returned

    Returns:
        None

    """
    if role is None:
        role = QtCore.Qt.DisplayRole
    model = tree_view.model()
    selection_model = tree_view.selectionModel()
    flags = (
        QtCore.QItemSelectionModel.Select
        | QtCore.QItemSelectionModel.Rows
    )

    if current_index:
        current_index_value = tree_view.currentIndex().data(role)
    else:
        current_index_value = None

    selected_rows = selection_model.selectedRows()
    if not selected_rows:
        yield
        return

    selected = set(row.data(role) for row in selected_rows)
    try:
        yield
    finally:
        if not selected:
            return

        # Go through all indices, select the ones with similar data
        for index in iter_model_rows(model, column=column, include_root=False):
            value = index.data(role)
            state = value in selected
            if state:
                tree_view.scrollTo(index)  # Ensure item is visible
                selection_model.select(index, flags)

            if current_index_value and value == current_index_value:
                selection_model.setCurrentIndex(
                    index, selection_model.NoUpdate
                )


class DynamicQThread(QtCore.QThread):
    """QThread which can run any function with argument and kwargs.

    Args:
        func (function): Function which will be called.
        args (tuple): Arguments which will be passed to function.
        kwargs (tuple): Keyword arguments which will be passed to function.
        parent (QObject): Parent of thread.
    """
    def __init__(self, func, args=None, kwargs=None, parent=None):
        super(DynamicQThread, self).__init__(parent)
        if args is None:
            args = tuple()
        if kwargs is None:
            kwargs = {}
        self._func = func
        self._args = args
        self._kwargs = kwargs

    def run(self):
        """Execute the function with arguments."""
        self._func(*self._args, **self._kwargs)


class WrappedCallbackItem:
    """Structure to store information about callback and args/kwargs for it.

    Item can be used to execute callback in main thread which may be needed
    for execution of Qt objects.

    Item store callback (callable variable), arguments and keyword arguments
    for the callback. Item hold information about it's process.
    """
    not_set = object()
    _log = None

    def __init__(self, callback, *args, **kwargs):
        self._done = False
        self._exception = self.not_set
        self._result = self.not_set
        self._callback = callback
        self._args = args
        self._kwargs = kwargs

    def __call__(self):
        self.execute()

    @property
    def log(self):
        cls = self.__class__
        if cls._log is None:
            cls._log = Logger.get_logger(cls.__name__)
        return cls._log

    @property
    def done(self):
        return self._done

    @property
    def exception(self):
        return self._exception

    @property
    def result(self):
        return self._result

    def execute(self):
        """Execute callback and store its result.

        Method must be called from main thread. Item is marked as `done`
        when callback execution finished. Store output of callback of exception
        information when callback raises one.
        """
        if self.done:
            self.log.warning("- item is already processed")
            return

        try:
            result = self._callback(*self._args, **self._kwargs)
            self._result = result

        except Exception as exc:
            self._exception = exc

        finally:
            self._done = True


def get_warning_pixmap(color=None):
    """Warning icon as QPixmap.

    Args:
        color(QtGui.QColor): Color that will be used to paint warning icon.
    """
    src_image_path = get_image_path("warning.png")
    src_image = QtGui.QImage(src_image_path)
    if color is None:
        color = get_objected_colors("delete-btn-bg").get_qcolor()

    return paint_image_with_color(src_image, color)


class RefreshThread(QtCore.QThread):
    refresh_finished = QtCore.Signal(str)

    def __init__(self, thread_id, func, *args, **kwargs):
        super(RefreshThread, self).__init__()
        self._id = thread_id
        self._callback = partial(func, *args, **kwargs)
        self._exception = None
        self._result = None
        self.finished.connect(self._on_finish_callback)

    @property
    def id(self):
        return self._id

    @property
    def failed(self):
        return self._exception is not None

    def run(self):
        try:
            self._result = self._callback()
        except Exception as exc:
            self._exception = exc

    def get_result(self):
        return self._result

    def _on_finish_callback(self):
        """Trigger custom signal with thread id.

        Listening for 'finished' signal we make sure that execution of thread
            finished and QThread object can be safely deleted.
        """

        self.refresh_finished.emit(self.id)


class _IconsCache:
    """Cache for icons."""

    _cache = {}
    _default = None
    _qtawesome_cache = {}

    @classmethod
    def _get_cache_key(cls, icon_def):
        parts = []
        icon_type = icon_def["type"]
        if icon_type == "path":
            parts = [icon_type, icon_def["path"]]

        elif icon_type == "awesome-font":
            parts = [icon_type, icon_def["name"], icon_def["color"]]
        return "|".join(parts)

    @classmethod
    def get_icon(cls, icon_def):
        if not icon_def:
            return None
        icon_type = icon_def["type"]
        cache_key = cls._get_cache_key(icon_def)
        cache = cls._cache.get(cache_key)
        if cache is not None:
            return cache

        icon = None
        if icon_type == "path":
            path = icon_def["path"]
            if os.path.exists(path):
                icon = QtGui.QIcon(path)

        elif icon_type == "awesome-font":
            icon_name = icon_def["name"]
            icon_color = icon_def["color"]
            icon = cls.get_qta_icon_by_name_and_color(icon_name, icon_color)
            if icon is None:
                icon = cls.get_qta_icon_by_name_and_color(
                    "fa.{}".format(icon_name), icon_color)
        if icon is None:
            icon = cls.get_default()
        cls._cache[cache_key] = icon
        return icon

    @classmethod
    def get_default(cls):
        pix = QtGui.QPixmap(1, 1)
        pix.fill(QtCore.Qt.transparent)
        return QtGui.QIcon(pix)

    @classmethod
    def get_qta_icon_by_name_and_color(cls, icon_name, icon_color):
        if not icon_name or not icon_color:
            return None

        full_icon_name = "{0}-{1}".format(icon_name, icon_color)
        if full_icon_name in cls._qtawesome_cache:
            return cls._qtawesome_cache[full_icon_name]

        variants = [icon_name]
        qta_instance = qtawesome._instance()
        for key in qta_instance.charmap.keys():
            variants.append("{0}.{1}".format(key, icon_name))

        icon = None
        used_variant = None
        for variant in variants:
            try:
                icon = qtawesome.icon(variant, color=icon_color)
                used_variant = variant
                break
            except Exception:
                pass

        if used_variant is None:
            log.info("Didn't find icon \"{}\"".format(icon_name))

        elif used_variant != icon_name:
            log.debug("Icon \"{}\" was not found \"{}\" is used instead".format(
                icon_name, used_variant
            ))

        cls._qtawesome_cache[full_icon_name] = icon
        return icon


def get_qt_icon(icon_def):
    """Returns icon from cache or creates new one.

    Args:
        icon_def (dict[str, Any]): Icon definition.

    Returns:
        QtGui.QIcon: Icon.

    """
    return _IconsCache.get_icon(icon_def)


def get_qta_icon_by_name_and_color(icon_name, icon_color):
    """Returns icon from cache or creates new one.

    Args:
        icon_name (str): Icon name.
        icon_color (str): Icon color.

    Returns:
        QtGui.QIcon: Icon.

    """
    return _IconsCache.get_qta_icon_by_name_and_color(icon_name, icon_color)
