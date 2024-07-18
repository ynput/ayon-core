import inspect

import pyblish.api

from ayon_core.pipeline.publish import PublishValidationError
from ayon_core.tools.utils.host_tools import show_workfiles
from ayon_core.pipeline.context_tools import version_up_current_workfile


class SaveByVersionUpAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Save Workfile"
    on = "failed"
    icon = "save"

    def process(self, context, plugin):
        version_up_current_workfile()


class ShowWorkfilesAction(pyblish.api.Action):
    """Save Workfile."""
    label = "Show Workfiles Tool..."
    on = "failed"
    icon = "files-o"

    def process(self, context, plugin):
        show_workfiles()


class ValidateCurrentSaveFile(pyblish.api.ContextPlugin):
    """File must be saved before publishing"""

    label = "Validate File Saved"
    order = pyblish.api.ValidatorOrder - 0.1
    hosts = ["maya", "houdini", "nuke", "fusion"]
    actions = [SaveByVersionUpAction, ShowWorkfilesAction]

    def process(self, context):

        current_file = context.data["currentFile"]
        if not current_file:
            raise PublishValidationError(
                "File not saved",
                title="File not saved",
                description=self.get_description())

    def get_description(self):
        return inspect.cleandoc("""
            ### File not saved
            
            Your workfile must be saved to continue publishing.
            
            Please save your scene.
            
            The **Save Workfile** action will save it for you with the first 
            available workfile version number in your current context.
        """)
