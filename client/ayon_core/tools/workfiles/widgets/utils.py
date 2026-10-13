from qtpy import QtWidgets, QtCore

from ayon_core.ui.components.tree_view import TreeViewItemDelegate
from ayon_core.ui.components.user_avatars import (
    ITEM_AVATAR_SIZE,
    UserAvatarCache,
    set_avatar_decoration,
)
from ayon_core.tools.utils.delegates import pretty_timestamp

# Login name of the user shown in the 'Author' column
USERNAME_ROLE = QtCore.Qt.UserRole + 50


class WorkfilesDelegate(TreeViewItemDelegate):
    """Unified delegate for the workfiles tree view.

    Column 0: workfile name with middle-elide.
    Column 1: author name with the avatar of the user.
    Column 2: pretty-printed timestamp (falls back to ``"N/A"``).

    Args:
        avatar_cache (UserAvatarCache): Cache of the user avatars. The
            view should be repainted when an avatar is updated.
        parent (QtWidgets.QWidget): The parent widget.
        style_model (StyleData): Style data of the tree view.
    """

    def __init__(self, avatar_cache, parent=None, style_model=None):
        super().__init__(parent=parent, style_model=style_model)
        self._avatar_cache = avatar_cache

    def initStyleOption(self, option, index):
        super().initStyleOption(option, index)
        if index.column() == 0:
            option.textElideMode = QtCore.Qt.ElideMiddle

        elif index.column() == 1:
            # Never blocks, the avatar is downloaded in the background.
            set_avatar_decoration(
                option,
                self._avatar_cache,
                index.data(USERNAME_ROLE),
                option.text,
            )

        elif index.column() == 2:
            # Column 2 exposes timestamp through DisplayRole in WorkfilesModel.
            raw = index.data(QtCore.Qt.DisplayRole)
            text = "N/A"
            if raw is not None:
                pretty = pretty_timestamp(raw)
                if pretty is not None:
                    text = pretty
            option.text = text


def create_avatar_cache(view):
    """Create cache of user avatars for a files view.

    The view must have its model set, the 'Author' column is made wider
    to fit the avatars.

    Args:
        view (QtWidgets.QAbstractItemView): View showing the avatars.

    Returns:
        UserAvatarCache: Cache that repaints the view when an avatar
            is downloaded.
    """
    # Keep the space the author names had before the avatars were added
    view.setColumnWidth(1, view.columnWidth(1) + ITEM_AVATAR_SIZE + 6)

    avatar_cache = UserAvatarCache(view)
    avatar_cache.avatar_updated.connect(
        lambda _username: view.viewport().update()
    )
    return avatar_cache


class BaseOverlayFrame(QtWidgets.QFrame):
    """Base frame for overlay widgets.

    Has implemented automated resize and event filtering.
    """

    def __init__(self, parent):
        super().__init__(parent)
        self.setObjectName("OverlayFrame")

        self._parent = parent

    def setVisible(self, visible):
        super().setVisible(visible)
        if visible:
            self._parent.installEventFilter(self)
            self.resize(self._parent.size())
        else:
            self._parent.removeEventFilter(self)

    def eventFilter(self, obj, event):
        if event.type() == QtCore.QEvent.Resize:
            self.resize(obj.size())

        return super().eventFilter(obj, event)
