import os
import pyblish.api


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
            name_template = "render{Task}{productName}_{AOV}"
            if not aov_name:
                # This is done to remove the trailing `_`
                # if aov name is an empty string.
                name_template = "render{Task}{productName}"

            product_name = name_template.format(
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
                "productName": product_name,
                "productGroup": product_group,
                "families": ["render.local.hou", "review"],
                "instance_node": instance.data["instance_node"],
                "representations": [
                    {
                        "stagingDir": staging_dir,
                        "ext": ext,
                        "name": ext,
                        "tags": ["review"],
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
