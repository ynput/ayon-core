import os
import re

import pyblish.api

from ayon_core.lib import prepare_template_data, is_in_tests
from ayon_core.settings import get_project_settings
from ayon_photoshop import api as photoshop


class CollectColorCodedInstances(pyblish.api.ContextPlugin):
    """Creates instances for layers marked by configurable color.

    Used in remote publishing when artists marks publishable layers by color-
    coding. Top level layers (group) must be marked by specific color to be
    published as an instance of 'image' product type.

    Can add group for all publishable layers to allow creation of flattened
    image. (Cannot contain special background layer as it cannot be grouped!)

    Based on value `create_flatten_image` from Settings:
    - "yes": create flattened 'image' product of all publishable layers + create
        'image' product per publishable layer
    - "only": create ONLY flattened 'image' product of all publishable layers
    - "no": do not create flattened 'image' product at all,
        only separate products per marked layer.

    Identifier:
        id (str): "ayon.create.instance"
    """

    label = "Collect Color-coded Instances"
    order = pyblish.api.CollectorOrder
    hosts = ["photoshop"]
    targets = ["automated"]
    settings_category = "photoshop"

    # configurable by Settings
    color_code_mapping = []
    create_flatten_image = "no"
    flatten_product_name_template = ""

    def process(self, context):
        self.log.info("CollectColorCodedInstances")
        batch_dir = (
            os.environ.get("AYON_PUBLISH_DATA")
            or os.environ.get("OPENPYPE_PUBLISH_DATA")
        )
        if (
            is_in_tests()
            and (
                not batch_dir or not os.path.exists(batch_dir)
            )
        ):
            self.log.debug("Automatic testing, no batch data, skipping")
            return

        existing_product_names = self._get_existing_product_names(context)

        # from CollectBatchData
        folder_path = context.data["folderPath"]
        task_name = context.data["task"]
        variant = context.data["variant"]
        project_name = context.data["projectEntity"]["name"]

        naming_conventions = get_project_settings(project_name).get(
            "photoshop", {}).get(
            "publish", {}).get(
            "ValidateNaming", {})

        stub = photoshop.stub()
        layers = stub.get_layers()

        publishable_layers = []
        created_instances = []
        product_type_from_settings = None
        for layer in layers:
            self.log.debug("Layer:: {}".format(layer))
            if layer.parents:
                self.log.debug("!!! Not a top layer, skip")
                continue

            if not layer.visible:
                self.log.debug("Not visible, skip")
                continue

            resolved_product_type, resolved_product_template = (
                self._resolve_mapping(layer)
            )

            if not resolved_product_template or not resolved_product_type:
                self.log.debug("!!! Not found product type or template, skip")
                continue

            if not product_type_from_settings:
                product_type_from_settings = resolved_product_type

            fill_pairs = {
                "variant": variant,
                "family": resolved_product_type,
                "product": {"type": resolved_product_type},
                "task": task_name,
                "layer": layer.clean_name
            }

            product_name = resolved_product_template.format(
                **prepare_template_data(fill_pairs))

            product_name = self._clean_product_name(
                stub, naming_conventions, product_name, layer
            )

            if product_name in existing_product_names:
                self.log.info((
                    "Product {} already created, skipping."
                ).format(product_name))
                continue

            if self.create_flatten_image != "flatten_only":
                instance = self._create_instance(
                    context,
                    layer,
                    resolved_product_type,
                    folder_path,
                    product_name,
                    task_name
                )
                created_instances.append(instance)

            existing_product_names.append(product_name)
            publishable_layers.append(layer)

        if self.create_flatten_image != "no" and publishable_layers:
            self.log.debug("create_flatten_image")
            if not self.flatten_product_name_template:
                self.log.warning("No template for flatten image")
                return

            fill_pairs.pop("layer")
            product_name = self.flatten_product_name_template.format(
                **prepare_template_data(fill_pairs))

            first_layer = publishable_layers[0]  # dummy layer
            first_layer.name = product_name
            product_type = product_type_from_settings  # inherit product type
            instance = self._create_instance(
                context,
                first_layer,
                product_type,
                folder_path,
                product_name,
                task_name
            )
            instance.data["ids"] = [layer.id for layer in publishable_layers]
            created_instances.append(instance)

        for instance in created_instances:
            # Produce diagnostic message for any graphical
            # user interface interested in visualising it.
            self.log.info("Found: \"%s\" " % instance.data["name"])
            self.log.info("instance: {} ".format(instance.data))

    def _get_existing_product_names(self, context):
        """Collect manually created instances from workfile.

        Shouldn't be any as Webpublisher bypass publishing via Openpype, but
        might be some if workfile published through OP is reused.
        """
        existing_product_names = []
        for instance in context:
            if instance.data.get("publish") is not False:
                existing_product_names.append(instance.data.get("productName"))

        return existing_product_names

    def _create_instance(
        self,
        context,
        layer,
        product_type,
        folder_path,
        product_name,
        task_name
    ):
        instance = context.create_instance(layer.name)
        instance.data["publish"] = True
        instance.data["productType"] = product_type
        instance.data["productName"] = product_name
        instance.data["folderPath"] = folder_path
        instance.data["task"] = task_name
        instance.data["layer"] = layer
        instance.data["family"] = product_type
        instance.data["families"] = [product_type]

        return instance

    def _resolve_mapping(self, layer):
        """Matches 'layer' color code and name to mapping.

            If both color code AND name regex is configured, BOTH must be valid
            If layer matches to multiple mappings, only first is used!
        """
        product_type_list = []
        product_name_list = []
        for mapping in self.color_code_mapping:
            if (
                mapping["color_code"]
                and layer.color_code not in mapping["color_code"]
            ):
                continue

            if (
                mapping["layer_name_regex"]
                and not any(
                    re.search(pattern, layer.name)
                    for pattern in mapping["layer_name_regex"]
                )
            ):
                continue

            product_type_list.append(mapping["product_type"])
            product_name_list.append(mapping["product_name_template"])

        if len(product_name_list) > 1:
            self.log.warning(
                "Multiple mappings found for '{}'".format(layer.name)
            )
            self.log.warning("Only first product name template used!")
            product_name_list[:] = product_name_list[0]

        if len(product_type_list) > 1:
            self.log.warning(
                "Multiple mappings found for '{}'".format(layer.name)
            )
            self.log.warning("Only first product type used!")
            product_type_list[:] = product_type_list[0]

        resolved_product_template = None
        if product_name_list:
            resolved_product_template = product_name_list.pop()

        product_type = None
        if product_type_list:
            product_type = product_type_list.pop()

        self.log.debug("resolved_product_type {}".format(product_type))
        self.log.debug("resolved_product_template {}".format(
            resolved_product_template))
        return product_type, resolved_product_template

    def _clean_product_name(
        self, stub, naming_conventions, product_name, layer
    ):
        """Cleans invalid characters from product name and layer name."""
        if re.search(naming_conventions["invalid_chars"], product_name):
            product_name = re.sub(
                naming_conventions["invalid_chars"],
                naming_conventions["replace_char"],
                product_name
            )
            layer_name = re.sub(
                naming_conventions["invalid_chars"],
                naming_conventions["replace_char"],
                layer.clean_name
            )
            layer.name = layer_name
            stub.rename_layer(layer.id, layer_name)

        return product_name
