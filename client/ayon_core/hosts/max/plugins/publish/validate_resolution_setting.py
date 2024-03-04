import pyblish.api
from pymxs import runtime as rt
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)
from ayon_core.hosts.max.api.lib import reset_scene_resolution


class ValidateResolutionSetting(pyblish.api.InstancePlugin,
                                OptionalPyblishPluginMixin):
    """Validate the resolution setting aligned with DB"""

    order = pyblish.api.ValidatorOrder - 0.01
    families = ["maxrender"]
    hosts = ["max"]
    label = "Validate Resolution Setting"
    optional = True
    actions = [RepairAction]

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        width, height = self.get_folder_resolution(instance)
        current_width = rt.renderWidth
        current_height = rt.renderHeight
        if current_width != width and current_height != height:
            raise PublishValidationError("Resolution Setting "
                                         "not matching resolution "
                                         "set on asset or shot.")
        if current_width != width:
            raise PublishValidationError("Width in Resolution Setting "
                                         "not matching resolution set "
                                         "on asset or shot.")

        if current_height != height:
            raise PublishValidationError("Height in Resolution Setting "
                                         "not matching resolution set "
                                         "on asset or shot.")

    def get_folder_resolution(self, instance):
        folder_entity = instance.data["folderEntity"]
        if folder_entity:
            folder_attributes = folder_entity["attrib"]
            width = folder_attributes["resolutionWidth"]
            height = folder_attributes["resolutionHeight"]
            return int(width), int(height)

        # Defaults if not found in folder entity
        return 1920, 1080

    @classmethod
    def repair(cls, instance):
        reset_scene_resolution()
