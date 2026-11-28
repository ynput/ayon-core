from qtpy import QtCore


ITEM_ID_ROLE = QtCore.Qt.UserRole + 1
ITEM_IS_GROUP_ROLE = QtCore.Qt.UserRole + 2
ITEM_LABEL_ROLE = QtCore.Qt.UserRole + 3
ITEM_ERRORED_ROLE = QtCore.Qt.UserRole + 4
PLUGIN_SKIPPED_ROLE = QtCore.Qt.UserRole + 5
PLUGIN_PASSED_ROLE = QtCore.Qt.UserRole + 6
INSTANCE_REMOVED_ROLE = QtCore.Qt.UserRole + 7
PLUGIN_NAME_ROLE = QtCore.Qt.UserRole + 8
PLUGIN_FILEPATH_ROLE = QtCore.Qt.UserRole + 9
PLUGIN_PROCESS_TIME_ROLE = QtCore.Qt.UserRole + 10
# Process time relative to the slowest plugin in report (0.0 - 1.0)
PLUGIN_PROCESS_TIME_RATIO_ROLE = QtCore.Qt.UserRole + 11

# Plugin states used to filter plugins in view
PLUGIN_STATE_SKIPPED = "skipped"
PLUGIN_STATE_PENDING = "pending"
PLUGIN_STATE_SUCCESSFUL = "successful"
PLUGIN_STATE_FAILED = "failed"


__all__ = (
    "ITEM_ID_ROLE",
    "ITEM_IS_GROUP_ROLE",
    "ITEM_LABEL_ROLE",
    "ITEM_ERRORED_ROLE",
    "PLUGIN_SKIPPED_ROLE",
    "INSTANCE_REMOVED_ROLE",
    "PLUGIN_NAME_ROLE",
    "PLUGIN_FILEPATH_ROLE",
    "PLUGIN_PROCESS_TIME_ROLE",
    "PLUGIN_PROCESS_TIME_RATIO_ROLE",
    "PLUGIN_STATE_SKIPPED",
    "PLUGIN_STATE_PENDING",
    "PLUGIN_STATE_SUCCESSFUL",
    "PLUGIN_STATE_FAILED",
)
