from ayon_server.settings import BaseSettingsModel, SettingsField


class WorkfileActionPluginModel(BaseSettingsModel):
    enabled: bool = SettingsField(True, title="Enabled")


class WorkfileActionsModel(BaseSettingsModel):
    ExploreHereAction: WorkfileActionPluginModel = SettingsField(
        default_factory=WorkfileActionPluginModel,
        title="Explore here",
        description=(
            "Show the selected workfile in the file browser of OS. Opens"
            " the work directory if a workfile is not selected."
        ),
    )
    DuplicateWorkfileAction: WorkfileActionPluginModel = SettingsField(
        default_factory=WorkfileActionPluginModel,
        title="Duplicate",
        description=(
            "Duplicate the selected workfile to a different version"
            " or with a different comment."
        ),
    )
    CopyFileAction: WorkfileActionPluginModel = SettingsField(
        default_factory=WorkfileActionPluginModel,
        title="Copy file path / Copy file",
        description=(
            "Copy path of the selected workfile, or the workfile itself,"
            " to clipboard."
        ),
    )
    IncrementAndOpenAction: WorkfileActionPluginModel = SettingsField(
        default_factory=WorkfileActionPluginModel,
        title="Increment and open",
        description=(
            "Copy the selected workfile to the next available version"
            " and open it."
        ),
    )


DEFAULT_WORKFILE_ACTIONS_VALUES = {
    "ExploreHereAction": {
        "enabled": True
    },
    "DuplicateWorkfileAction": {
        "enabled": True
    },
    "CopyFileAction": {
        "enabled": True
    },
    "IncrementAndOpenAction": {
        "enabled": True
    },
}
