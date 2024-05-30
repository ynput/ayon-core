import ayon_api
import ayon_maya.api.action
import pyblish.api
from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError,
)
from ayon_maya.api import plugin


class ValidateRenderLayerAOVs(plugin.MayaInstancePlugin,
                              OptionalPyblishPluginMixin):
    """Validate created AOVs / RenderElement is registered in the database

    Each render element is registered as a product which is formatted based on
    the render layer and the render element, example:

        <render layer>.<render element>

    This translates to something like this:

        CHAR.diffuse

    This check is needed to ensure the render output is still complete

    """

    order = pyblish.api.ValidatorOrder + 0.1
    label = "Render Passes / AOVs Are Registered"
    families = ["renderlayer"]
    actions = [ayon_maya.api.action.SelectInvalidAction]
    optional = False

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                "Found unregistered products: {}".format(invalid))

    def get_invalid(self, instance):
        invalid = []

        project_name = instance.context.data["projectName"]
        folder_entity = instance.data["folderEntity"]
        render_passes = instance.data.get("renderPasses", [])
        for render_pass in render_passes:
            is_valid = self.validate_product_registered(
                project_name, folder_entity, render_pass
            )
            if not is_valid:
                invalid.append(render_pass)

        return invalid

    def validate_product_registered(
        self, project_name, folder_entity, product_name
    ):
        """Check if product is registered in the database under the folder"""

        return ayon_api.get_product_by_name(
            project_name, product_name, folder_entity["id"], fields={"id"}
        )
