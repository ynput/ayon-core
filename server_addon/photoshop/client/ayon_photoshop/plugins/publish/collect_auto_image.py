import pyblish.api

from ayon_photoshop import api as photoshop
from ayon_core.pipeline.create import get_product_name


class CollectAutoImage(pyblish.api.ContextPlugin):
    """Creates auto image in non artist based publishes (Webpublisher).
    """

    label = "Collect Auto Image"
    hosts = ["photoshop"]
    order = pyblish.api.CollectorOrder + 0.2

    targets = ["automated"]

    def process(self, context):
        for instance in context:
            creator_identifier = instance.data.get("creator_identifier")
            if creator_identifier and creator_identifier == "auto_image":
                self.log.debug("Auto image instance found, won't create new")
                return

        project_name = context.data["projectName"]
        proj_settings = context.data["project_settings"]
        host_name = context.data["hostName"]
        folder_entity = context.data["folderEntity"]
        task_entity = context.data["taskEntity"]
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        auto_creator = proj_settings.get(
            "photoshop", {}).get(
            "create", {}).get(
            "AutoImageCreator", {})

        if not auto_creator or not auto_creator["enabled"]:
            self.log.debug("Auto image creator disabled, won't create new")
            return

        stub = photoshop.stub()
        stored_items = stub.get_layers_metadata()
        for item in stored_items:
            if item.get("creator_identifier") == "auto_image":
                if not item.get("active"):
                    self.log.debug("Auto_image instance disabled")
                    return

        layer_items = stub.get_layers()

        publishable_ids = [layer.id for layer in layer_items
                           if layer.visible]

        # collect stored image instances
        instance_names = []
        for layer_item in layer_items:
            layer_meta_data = stub.read(layer_item, stored_items)

            # Skip layers without metadata.
            if layer_meta_data is None:
                continue

            # Skip containers.
            if "container" in layer_meta_data["id"]:
                continue

            # active might not be in legacy meta
            if layer_meta_data.get("active", True) and layer_item.visible:
                instance_names.append(layer_meta_data["productName"])

        if len(instance_names) == 0:
            variants = proj_settings.get(
                "photoshop", {}).get(
                "create", {}).get(
                "CreateImage", {}).get(
                "default_variants", [''])
            product_type = "image"

            variant = context.data.get("variant") or variants[0]

            product_name = get_product_name(
                project_name,
                task_name,
                task_type,
                host_name,
                product_type,
                variant,
            )

            instance = context.create_instance(product_name)
            instance.data["folderPath"] = folder_entity["path"]
            instance.data["productType"] = product_type
            instance.data["productName"] = product_name
            instance.data["ids"] = publishable_ids
            instance.data["publish"] = True
            instance.data["creator_identifier"] = "auto_image"
            instance.data["family"] = product_type
            instance.data["families"] = [product_type]

            if auto_creator["mark_for_review"]:
                instance.data["creator_attributes"] = {"mark_for_review": True}
                instance.data["families"].append("review")

            self.log.info("auto image instance: {} ".format(instance.data))
