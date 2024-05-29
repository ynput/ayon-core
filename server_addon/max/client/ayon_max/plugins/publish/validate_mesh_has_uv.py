
import pyblish.api
from ayon_max.api.action import SelectInvalidAction
from ayon_core.pipeline.publish import (
    ValidateMeshOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)
from pymxs import runtime as rt


class ValidateMeshHasUVs(pyblish.api.InstancePlugin,
                         OptionalPyblishPluginMixin):

    """Validate the current mesh has UVs.

    This validator only checks if the mesh has UVs but not
    whether all the individual faces of the mesh have UVs.

    It validates whether the current mesh has texture vertices.
    If the mesh does not have texture vertices, it does not
    have UVs in Max.

    """

    order = ValidateMeshOrder
    hosts = ['max']
    families = ['model']
    label = 'Validate Mesh Has UVs'
    actions = [SelectInvalidAction]
    optional = True

    settings_category = "max"

    @classmethod
    def get_invalid(cls, instance):
        meshes = [member for member in instance.data["members"]
                  if rt.isProperty(member, "mesh")]
        invalid = [member for member in meshes
                   if member.mesh.numTVerts == 0]
        return invalid

    def process(self, instance):
        if not self.is_active(instance.data):
            return
        invalid = self.get_invalid(instance)
        if invalid:
            bullet_point_invalid_statement = "\n".join(
                "- {}".format(invalid.name) for invalid
                in invalid
            )
            report = (
                "Model meshes are required to have UVs.\n\n"
                "Meshes detected with invalid or missing UVs:\n"
                f"{bullet_point_invalid_statement}\n"
            )
            raise PublishValidationError(
                report,
                description=(
                "Model meshes are required to have UVs.\n\n"
                "Meshes detected with no texture vertice or missing UVs"),
                title="Non-mesh objects found or mesh has missing UVs")
