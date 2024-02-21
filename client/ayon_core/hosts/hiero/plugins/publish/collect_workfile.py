import os

import pyblish.api

import hiero
import nuke


class CollectWorkfile(pyblish.api.InstancePlugin):
    """Collect the current working file into context"""

    families = ["workfile"]
    label = "Collect Workfile"
    order = pyblish.api.CollectorOrder - 0.49

    def process(self, instance):
        current_file = os.path.normpath(hiero.ui.activeProject().path())

        # creating instances per write node
        staging_dir = os.path.dirname(current_file)
        base_name = os.path.basename(current_file)

        # creating representation
        representation = {
            'name': 'nk',
            'ext': 'nk',
            'files': base_name,
            "stagingDir": staging_dir,
        }

        # creating instance data
        instance.data.update({
            "name": base_name,
            "representations": [representation]
        })

        self.log.debug(
            "Collected current script version: {}".format(current_file)
        )
