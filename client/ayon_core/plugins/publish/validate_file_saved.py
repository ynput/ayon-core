import inspect

import pyblish.api

from ayon_core.host import IWorkfileHost
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.publish import PublishValidationError
from ayon_core.pipeline.workfile import save_next_version
from ayon_core.tools.utils.host_tools import show_workfiles


class SaveByVersionUpAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Save Workfile"
    on = "failed"
    icon = "save"

    def process(self, context, plugin):
        save_next_version()


class ShowWorkfilesAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Show Workfiles Tool..."
    on = "failed"
    icon = "files-o"

    def process(self, context, plugin):
        show_workfiles()


class ValidateCurrentSaveFile(pyblish.api.ContextPlugin):
    """File must be saved before publishing

    This does not validate for unsaved changes. It only validates whether
    the current context was able to identify any 'currentFile'.
    """

    label = "Validate File Saved"
    order = pyblish.api.ValidatorOrder - 0.1
    actions = [SaveByVersionUpAction, ShowWorkfilesAction]

    def process(self, context):
        host = registered_host()
        if not isinstance(host, IWorkfileHost):
            return

        current_file = context.data["currentFile"]
        if not current_file:
            raise PublishValidationError(
                "Workfile is not saved. Please save your scene to continue.",
                title="File not saved",
                description=self.get_description())

    def get_description(self):
        return inspect.cleandoc("""
            ### File not saved

            Your workfile must be saved to continue publishing.

            The **Save Workfile** action will save it for you with the first
            available workfile version number in your current context.
        """)
