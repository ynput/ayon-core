import pyblish.api
from ayon_core.pipeline.publish import OptionalPyblishPluginMixin
from ayon_blender.api.workio import save_file
from ayon_blender.api import plugin


class IncrementWorkfileVersion(
    plugin.BlenderContextPlugin,
    OptionalPyblishPluginMixin
):
    """Increment current workfile version."""

    order = pyblish.api.IntegratorOrder + 0.9
    label = "Increment Workfile Version"
    optional = True
    hosts = ["blender"]
    families = ["animation", "model", "rig", "action", "layout", "blendScene",
                "pointcache", "render.farm"]

    def process(self, context):
        if not self.is_active(context.data):
            return

        assert all(result["success"] for result in context.data["results"]), (
            "Publishing not successful so version is not increased.")

        from ayon_core.lib import version_up
        path = context.data["currentFile"]
        filepath = version_up(path)

        save_file(filepath, copy=False)

        self.log.debug('Incrementing blender workfile version')
