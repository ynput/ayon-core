
import pyblish.api
from ayon_core.pipeline.publish import (
    RepairAction,
    ValidateContentsOrder,
    PublishValidationError,
    KnownPublishError
)


class ValidateEditMode(pyblish.api.InstancePlugin):
    """Validates whether zbrush is in edit mode before
    exporting model with tool settings.
    """

    label = "Validate Frame Range"
    order = ValidateContentsOrder
    families = ["model"]
    hosts = ["zbrush"]
    optional = True
    actions = [RepairAction]

    def process(self, instance):
        pass
