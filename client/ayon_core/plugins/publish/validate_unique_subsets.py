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
            if not instance.data.get("publish", True):
                continue

            # Ignore instances not marked to integrate
            if not instance.data.get("integrate", True):
                continue

            # Ignore instance without folder data
            folder_path = instance.data.get("folderPath")
            if folder_path is None:
                self.log.warning(
                    "Instance found without `folderPath` data: "
                    f"{instance.name}"
                )
                continue

            # Ignore instance without product data
            product_name = instance.data.get("productName")
            if product_name is None:
                self.log.warning(
                    "Instance found without `productName` in data: "
                    f"{instance.name}"
                )
                continue

            version = instance.data.get("version")
            key = (
                folder_path,
                product_name,
                version
            )
            instance_per_folder_product[key].append(instance)

        non_unique = []
        for (folder_path, product_name, version), instances in (
            instance_per_folder_product.items()
        ):
            label = f"{folder_path} > {product_name}"

            # If this has an explicit version, but there is also a non-explicit
            # version instance then disallow it.
            versionless_key = (folder_path, product_name, None)
            if (
                version is not None
                and versionless_key in instance_per_folder_product
            ):
                non_unique.append(label)
                self.log.error(
                    f"Instance with explicit version {version} found for "
                    f"product {label}, but there is also an instance without "
                    f"explicit version. This is not allowed."
                )

            # A single instance per folder, product is fine
            if len(instances) < 2:
                continue

            if version is not None:
                label += f" (version {version})"
            non_unique.append(label)

        if not non_unique:
            # All is ok
            return

        msg = (
            f"Instance products {non_unique} are not unique."
            " Please remove or rename duplicates."
        )
        formatting_data = {
            "non_unique": ",".join(non_unique)
        }

        if non_unique:
            raise PublishXmlValidationError(self, msg,
                                            formatting_data=formatting_data)
