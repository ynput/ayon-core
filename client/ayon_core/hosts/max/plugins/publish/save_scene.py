import pyblish.api
from ayon_core.pipeline import registered_host


class SaveCurrentScene(pyblish.api.InstancePlugin):
    """Save current scene"""

    label = "Save current file"
    order = pyblish.api.ExtractorOrder - 0.49
    hosts = ["max"]
    families = ["maxrender", "workfile"]

    def process(self, instance):
        host = registered_host()
        current_file = host.get_current_workfile()

        assert instance.context.data["currentFile"] == current_file
        if instance.data["productType"] == "maxrender":
            host.save_workfile(current_file)

        elif host.workfile_has_unsaved_changes():
            self.log.info(f"Saving current file: {current_file}")
            host.save_workfile(current_file)
        else:
            self.log.debug("No unsaved changes, skipping file save..")