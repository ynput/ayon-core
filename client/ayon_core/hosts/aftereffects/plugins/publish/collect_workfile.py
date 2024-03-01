import os

import pyblish.api


class CollectWorkfile(pyblish.api.ContextPlugin):
    """ Adds the AE render instances """

    label = "Collect After Effects Workfile Instance"
    order = pyblish.api.CollectorOrder + 0.1

    default_variant = "Main"

    def process(self, context):
        workfile_instance = None
        for instance in context:
            if instance.data["productType"] == "workfile":
                self.log.debug("Workfile instance found")
                workfile_instance = instance
                break

        current_file = context.data["currentFile"]
        staging_dir = os.path.dirname(current_file)
        scene_file = os.path.basename(current_file)
        if workfile_instance is None:
            self.log.debug("Workfile instance not found. Skipping")
            return

        # creating representation
        workfile_instance.data["representations"].append({
            "name": "aep",
            "ext": "aep",
            "files": scene_file,
            "stagingDir": staging_dir,
        })
