
import pyblish.api
from ayon_core.hosts.max.api.action import SelectInvalidAction
from ayon_core.pipeline.publish import (
    ValidateMeshOrder,
    OptionalPyblishPluginMixin,
    PublishValidationError
)
from pymxs import runtime as rt


class ValidateMeshHasUVs(pyblish.api.InstancePlugin,
                         OptionalPyblishPluginMixin):

    """Validate the current mesh has UVs.

    It validates whether the current UV set has non-zero UVs and
    at least more than the vertex count. It's not really bulletproof,
    but a simple quick validation to check if there are likely
    UVs for every face.
    """

    order = ValidateMeshOrder
    hosts = ['max']
    families = ['model']
    label = 'Validate Mesh Has UVs'
    actions = [SelectInvalidAction]
    optional = True


    @classmethod
    def get_invalid(cls, instance):
        invalid = [member for member in instance.data["members"]
                   if not member.mesh.numTVerts > 0]
        return invalid

    def process(self, instance):
        invalid = self.get_invalid(instance)
        if invalid:
            raise PublishValidationError(
                title="Mesh has missing UVs",
                message="Model meshes are required to have UVs.<br><br>"
                        "Meshes detected with invalid or missing UVs:<br>"
                        "{0}".format([err.name for err in invalid])
            )
