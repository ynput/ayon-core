import os
import pyblish.api
from ayon_core.pipeline.create import get_product_name
from ayon_core.pipeline.farm.patterning import match_aov_pattern
from ayon_core.pipeline.publish import (
    get_plugin_settings,
    apply_plugin_settings_automatically
)
from ayon_houdini.api import plugin


class CollectLocalRenderInstances(plugin.HoudiniInstancePlugin):
    """Collect instances for local render.

    Agnostic Local Render Collector.
    """

    # this plugin runs after Collect Render Products
    order = pyblish.api.CollectorOrder + 0.12
    families = ["mantra_rop",
                "karma_rop",
                "redshift_rop",
                "arnold_rop",
                "vray_rop"]

    label = "Collect local render instances"

    use_deadline_aov_filter = False
    aov_filter = {"host_name": "houdini",
                  "value": [".*([Bb]eauty).*"]}

    @classmethod
    def apply_settings(cls, project_settings):
        # Preserve automatic settings applying logic
        settings = get_plugin_settings(plugin=cls,
                                       project_settings=project_settings,
                                       log=cls.log,
                                       category="houdini")
        apply_plugin_settings_automatically(cls, settings, logger=cls.log)

        if not cls.use_deadline_aov_filter:
            # get aov_filter from collector settings
            # and restructure it as match_aov_pattern requires.
            cls.aov_filter = {
                cls.aov_filter["host_name"]: cls.aov_filter["value"]
            }
        else:
            # get aov_filter from deadline settings
            cls.aov_filter = project_settings["deadline"]["publish"]["ProcessSubmittedJobOnFarm"]["aov_filter"]
            cls.aov_filter = {
            item["name"]: item["value"]
            for item in cls.aov_filter
        }

    def process(self, instance):

        if instance.data["farm"]:
            self.log.debug("Render on farm is enabled. "
                           "Skipping local render collecting.")
            return

        # Create Instance for each AOV.
        context = instance.context
        expectedFiles = next(iter(instance.data["expectedFiles"]), {})

        product_type = "render"  # is always render
        product_group = get_product_name(
            context.data["projectName"],
            context.data["taskEntity"]["name"],
            context.data["taskEntity"]["taskType"],
            context.data["hostName"],
            product_type,
            instance.data["productName"]
        )

        for aov_name, aov_filepaths in expectedFiles.items():
            product_name = product_group

            if aov_name:
                product_name = "{}_{}".format(product_name, aov_name)

            # Create instance for each AOV
            aov_instance = context.create_instance(product_name)

            # Prepare Representation for each AOV
            aov_filenames = [os.path.basename(path) for path in aov_filepaths]
            staging_dir = os.path.dirname(aov_filepaths[0])
            ext = aov_filepaths[0].split(".")[-1]

            # Decide if instance is reviewable
            preview = False
            if instance.data.get("multipartExr", False):
                # Add preview tag because its multipartExr.
                preview = True
            else:
                # Add Preview tag if the AOV matches the filter.
                preview = match_aov_pattern(
                    "houdini", self.aov_filter, aov_filenames[0]
                )

            preview = preview and instance.data.get("review", False)

            # Support Single frame.
            # The integrator wants single files to be a single
            #  filename instead of a list.
            # More info: https://github.com/ynput/ayon-core/issues/238
            if len(aov_filenames) == 1:
                aov_filenames = aov_filenames[0]

            aov_instance.data.update({
                # 'label': label,
                "task": instance.data["task"],
                "folderPath": instance.data["folderPath"],
                "frameStart": instance.data["frameStartHandle"],
                "frameEnd": instance.data["frameEndHandle"],
                "productType": product_type,
                "family": product_type,
                "productName": product_name,
                "productGroup": product_group,
                "families": ["render.local.hou", "review"],
                "instance_node": instance.data["instance_node"],
                "representations": [
                    {
                        "stagingDir": staging_dir,
                        "ext": ext,
                        "name": ext,
                        "tags": ["review"] if preview else [],
                        "files": aov_filenames,
                        "frameStart": instance.data["frameStartHandle"],
                        "frameEnd": instance.data["frameEndHandle"]
                    }
                ]
            })

        # Skip integrating original render instance.
        # We are not removing it because it's used to trigger the render.
        instance.data["integrate"] = False
