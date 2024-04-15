import os
import pyblish.api
from ayon_core.pipeline.create import get_product_name


class CollectLocalRenderInstances(pyblish.api.InstancePlugin):
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

    hosts = ["houdini"]
    label = "Collect local render instances"

    def process(self, instance):

        if instance.data["farm"]:
            self.log.debug("Render on farm is enabled. "
                           "Skipping local render collecting.")
            return

        # Create Instance for each AOV.
        context = instance.context
        self.log.debug(instance.data["expectedFiles"])
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

            # Support Single frame.
            # The integrator wants single files to be a single
            #  filename instead of a list.
            # More info: https://github.com/ynput/ayon-core/issues/238
            if len(aov_filenames) == 1:
                aov_filenames = aov_filenames[0]

            # TODO: Add some option to allow users to mark
            #       aov_instances as reviewable.
            aov_instance.data.update({
                # 'label': label,
                "task": instance.data["task"],
                "folderPath": instance.data["folderPath"],
                "frameStart": instance.data["frameStartHandle"],
                "frameEnd": instance.data["frameEndHandle"],
                "productType": product_type,
                "productName": product_name,
                "productGroup": product_group,
                "families": ["render.local.hou"],
                "instance_node": instance.data["instance_node"],
                "representations": [
                    {
                        "stagingDir": staging_dir,
                        "ext": ext,
                        "name": ext,
                        "tags": [],
                        "files": aov_filenames,
                        "frameStart": instance.data["frameStartHandle"],
                        "frameEnd": instance.data["frameEndHandle"]
                    }
                ]
            })

        # Remove original render instance
        # I can't remove it here as I still need it to trigger the render.
        # context.remove(instance)
