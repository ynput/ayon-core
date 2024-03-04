
import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    ValidateContentsOrder,
    PublishValidationError
)
from ayon_core.hosts.zbrush.api.lib import has_edit_mode


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

    def process(self, context):
        edit_mode = has_edit_mode()
        self.log.debug(f"{edit_mode}")
        if edit_mode == "0":
            raise PublishValidationError(
                "Zbrush is not in edit mode, "
                "please make sure it is in edit mode before extraction."
            )
