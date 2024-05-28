import nuke
import pyblish.api


class IncrementScriptVersion(pyblish.api.ContextPlugin):
    """Increment current script version."""

    order = pyblish.api.IntegratorOrder + 0.9
    label = "Increment Script Version"
    optional = True
    families = ["workfile"]
    hosts = ["nuke"]

    settings_category = "nuke"

    def process(self, context):
        if not context.data.get("increment_script_version", True):
            return

        assert all(result["success"] for result in context.data["results"]), (
            "Publishing not successful so version is not increased.")

        from ayon_core.lib import version_up
        path = context.data["currentFile"]
        nuke.scriptSaveAs(version_up(path))
        self.log.info('Incrementing script version')
