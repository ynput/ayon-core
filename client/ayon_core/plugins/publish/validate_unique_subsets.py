from collections import defaultdict

import pyblish.api

from ayon_core.pipeline.publish import (
    PublishXmlValidationError,
)


class ValidateProductUniqueness(pyblish.api.ContextPlugin):
    """Validate all product names are unique.

    This only validates whether the instances currently set to publish from
    the workfile overlap one another for the folder + product they are
    publishing to.

    This does not perform any check against existing publishes in the database
    since it is allowed to publish into existing products resulting in
    versioning.

    A product may appear twice to publish from the workfile if one
    of them is set to publish to another folder than the other.

    """

    label = "Validate Product Uniqueness"
    order = pyblish.api.ValidatorOrder
    families = ["*"]

    def process(self, context):

        # Find instance per (folder,product)
        instance_per_folder_product = defaultdict(list)
        for instance in context:

            # Ignore disabled instances
            if not instance.data.get('publish', True):
                continue

            # Ignore instance without folder data
            folder_path = instance.data.get("folderPath")
            if folder_path is None:
                self.log.warning("Instance found without `folderPath` data: "
                                 "{}".format(instance.name))
                continue

            # Ignore instance without product data
            product_name = instance.data.get("productName")
            if product_name is None:
                self.log.warning((
                    "Instance found without `productName` in data: {}"
                ).format(instance.name))
                continue

            instance_per_folder_product[(folder_path, product_name)].append(
                instance
            )

        non_unique = []
        for (folder_path, product_name), instances in (
            instance_per_folder_product.items()
        ):
            # A single instance per folder, product is fine
            if len(instances) < 2:
                continue

            non_unique.append(
                "{} > {}".format(folder_path, product_name)
            )

        if not non_unique:
            # All is ok
            return

        msg = (
            f"Instance product names {non_unique} are not unique."
            " Please remove or rename duplicates."
        )
        formatting_data = {
            "non_unique": ",".join(non_unique)
        }

        if non_unique:
            raise PublishXmlValidationError(self, msg,
                                            formatting_data=formatting_data)
