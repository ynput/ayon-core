
import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    ValidateContentsOrder,
    PublishValidationError,
    RepairContextAction
)
from ayon_core.hosts.zbrush.api.lib import is_in_edit_mode, execute_zscript


class ValidateEditMode(pyblish.api.ContextPlugin,
                       OptionalPyblishPluginMixin):
    """Validates whether zbrush is in edit mode before
    exporting model with tool settings.
    """

    label = "Validate Edit Mode"
    order = ValidateContentsOrder
    families = ["model"]
    hosts = ["zbrush"]
    optional = True
    actions = [RepairContextAction]

    def process(self, context):
        edit_mode = is_in_edit_mode()
        if int(edit_mode) == 0:
            raise PublishValidationError(
                "Zbrush is not in edit mode, "
                "please make sure it is in edit mode before extraction."
            )

    @classmethod
    def repair(cls, context):
        # Enable Transform:Edit state
        execute_zscript("[ISet, Transform:Edit, 1]")
