import pyblish.api
from pymxs import runtime as rt
from ayon_core.pipeline import (
    OptionalPyblishPluginMixin
)
from ayon_core.pipeline.publish import (
    RepairAction,
    PublishValidationError
)
from ayon_max.api.lib import (
    reset_scene_resolution,
    imprint
)


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
        current_width, current_height = (
            self.get_current_resolution(instance)
        )

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

    def get_current_resolution(self, instance):
        return rt.renderWidth, rt.renderHeight

    @classmethod
    def get_folder_resolution(cls, instance):
        task_entity = instance.data.get("taskEntity")
        if task_entity:
            task_attributes = task_entity["attrib"]
            width = task_attributes["resolutionWidth"]
            height = task_attributes["resolutionHeight"]
            return int(width), int(height)

        # Defaults if not found in folder entity
        return 1920, 1080

    @classmethod
    def repair(cls, instance):
        reset_scene_resolution()


class ValidateReviewResolutionSetting(ValidateResolutionSetting):
    families = ["review"]
    optional = True
    actions = [RepairAction]

    def get_current_resolution(self, instance):
        current_width = instance.data["review_width"]
        current_height = instance.data["review_height"]
        return current_width, current_height

    @classmethod
    def repair(cls, instance):
        context_width, context_height = (
            cls.get_folder_resolution(instance)
        )
        creator_attrs = instance.data["creator_attributes"]
        creator_attrs["review_width"] = context_width
        creator_attrs["review_height"] = context_height
        creator_attrs_data = {
            "creator_attributes": creator_attrs
        }
        # update the width and height of review
        # data in creator_attributes
        imprint(instance.data["instance_node"], creator_attrs_data)
