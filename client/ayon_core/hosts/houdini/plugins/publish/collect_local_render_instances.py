import os
import pyblish.api


class CollectLocalRenderInstances(pyblish.api.InstancePlugin):
    """Collect instances for local render.

    Agnostic Local Render Collector.
    """

    # this plugin runs after Collect Render Products
    order = pyblish.api.CollectorOrder + 0.12
    families = ["mantra_rop"]

    hosts = ["houdini"]
    targets = ["local", "remote"]
    label = "Collect local render instances"

    def process(self, instance):
        creator_attribute = instance.data["creator_attributes"]
        farm_enabled = creator_attribute["farm"]
        instance.data["farm"] = farm_enabled
        if farm_enabled:
            self.log.debug("Render on farm is enabled. "
                           "Skipping local render collecting.")
            return

        # Create Instance for each AOV.
        context = instance.context
        expectedFiles = next(iter(instance.data["expectedFiles"]), {})

        product_type = "render"  # is always render
        product_group = "render{Task}{productName}".format(
            Task=self._capitalize(instance.data["task"]),
            productName=self._capitalize(instance.data["productName"])
        )  # is always the group

        for aov_name, aov_filepaths in expectedFiles.items():
            # Some AOV instance data
            # label = "{productName}_{AOV}".format(
            #     AOV=aov_name,
            #     productName=instance.data["productName"]
            # )
            product_name = "render{Task}{productName}_{AOV}".format(
                Task=self._capitalize(instance.data["task"]),
                productName=self._capitalize(instance.data["productName"]),
                AOV=aov_name
            )

            # Create instance for each AOV
            aov_instance = context.create_instance(product_name)

            # Prepare Representation for each AOV
            aov_filenames = [os.path.basename(path) for path in aov_filepaths]
            staging_dir = os.path.dirname(aov_filepaths[0])
            ext = aov_filepaths[0].split(".")[-1]

            aov_instance.data.update({
                # 'label': label,
                "task": instance.data["task"],
                "folderPath": instance.data["folderPath"],
                "frameStart": instance.data["frameStartHandle"],
                "frameEnd": instance.data["frameEndHandle"],
                "productType": product_type,
                "productName": product_name,
                "productGroup": product_group,
                "tags": [],
                "families": ["render.local.hou"],
                "instance_node": instance.data["instance_node"],
                "representations": [
                    {
                        "stagingDir": staging_dir,
                        "ext": ext,
                        "name": ext,
                        "files": aov_filenames,
                        "frameStart": instance.data["frameStartHandle"],
                        "frameEnd": instance.data["frameEndHandle"]
                    }
                ]
            })

        # Remove Mantra instance
        # I can't remove it here as I still need it to trigger the render.
        # context.remove(instance)

    @staticmethod
    def _capitalize(word):
        return word[:1].upper() + word[1:]
