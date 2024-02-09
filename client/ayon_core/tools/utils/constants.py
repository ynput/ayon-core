from qtpy import QtCore


UNCHECKED_INT = getattr(QtCore.Qt.Unchecked, "value", 0)
PARTIALLY_CHECKED_INT = getattr(QtCore.Qt.PartiallyChecked, "value", 1)
CHECKED_INT = getattr(QtCore.Qt.Checked, "value", 2)

# Checkbox state
try:
    ITEM_IS_USER_TRISTATE = QtCore.Qt.ItemIsUserTristate
except AttributeError:
    ITEM_IS_USER_TRISTATE = QtCore.Qt.ItemIsTristate

DEFAULT_PROJECT_LABEL = "< Default >"
PROJECT_NAME_ROLE = QtCore.Qt.UserRole + 101
PROJECT_IS_ACTIVE_ROLE = QtCore.Qt.UserRole + 102
