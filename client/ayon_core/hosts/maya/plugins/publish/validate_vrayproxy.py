import pyblish.api

from ayon_core.pipeline.publish import (
    OptionalPyblishPluginMixin,
    PublishValidationError
)


class ValidateVrayProxy(pyblish.api.InstancePlugin,
                        OptionalPyblishPluginMixin):

    order = pyblish.api.ValidatorOrder
    label = "VRay Proxy Settings"
    hosts = ["maya"]
    families = ["vrayproxy"]
    optional = False

    def process(self, instance):
        data = instance.data
        if not self.is_active(data):
            return
        if not data["setMembers"]:
            raise PublishValidationError(
                f"Instance '{instance.name}' is empty."
            )

        if data["animation"]:
            if data["frameEnd"] < data["frameStart"]:
                raise PublishValidationError(
                    "End frame is smaller than start frame"
                )

        if not data["vrmesh"] and not data["alembic"]:
            raise PublishValidationError(
                "Both vrmesh and alembic are off. Needs at least one to"
                " publish."
            )
