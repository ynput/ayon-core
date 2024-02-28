
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


    @classmethod
    def get_invalid(cls, instance):
        invalid_mesh_type = [member for member in instance.data["members"]
                             if not rt.isProperty(member, "mesh")]
        if invalid_mesh_type:
            cls.log.error("Non-mesh type objects detected:\n".join(
                "-{}".format(invalid.name) for invalid
                in invalid_mesh_type))
            return invalid_mesh_type

        invalid_uv = [member for member in instance.data["members"]
                      if not member.mesh.numTVerts > 0]
        if invalid_uv:
            cls.log.error("Meshes detected with invalid UVs:\n".join(
                "-{}".format(invalid.name) for invalid
                in invalid_uv))
        return invalid_uv

    def process(self, instance):
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
                title="Mesh has missing UVs")
