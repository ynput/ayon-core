from collections import defaultdict
import pyblish.api
from ayon_core.pipeline.publish import (
    PublishXmlValidationError,
)


class ValidateSubsetUniqueness(pyblish.api.ContextPlugin):
    """Validate all product names are unique.

    This only validates whether the instances currently set to publish from
    the workfile overlap one another for the asset + product they are publishing
    to.

    This does not perform any check against existing publishes in the database
    since it is allowed to publish into existing products resulting in
    versioning.

    A product may appear twice to publish from the workfile if one
    of them is set to publish to another asset than the other.

    """

    label = "Validate Subset Uniqueness"
    order = pyblish.api.ValidatorOrder
    families = ["*"]

    def process(self, context):

        # Find instance per (asset,product)
        instance_per_asset_product = defaultdict(list)
        for instance in context:

            # Ignore disabled instances
            if not instance.data.get('publish', True):
                continue

            # Ignore instance without asset data
            asset = instance.data.get("folderPath")
            if asset is None:
                self.log.warning("Instance found without `asset` data: "
                                 "{}".format(instance.name))
                continue

            # Ignore instance without product data
            product_name = instance.data.get("productName")
            if product_name is None:
                self.log.warning((
                    "Instance found without `productName` in data: {}"
                ).format(instance.name))
                continue

            instance_per_asset_product[(asset, product_name)].append(instance)

        non_unique = []
        for (asset, product_name), instances in instance_per_asset_product.items():

            # A single instance per asset, product is fine
            if len(instances) < 2:
                continue

            non_unique.append("{} > {}".format(asset, product_name))

        if not non_unique:
            # All is ok
            return

        msg = ("Instance product names {} are not unique. ".format(non_unique) +
               "Please remove or rename duplicates.")
        formatting_data = {
            "non_unique": ",".join(non_unique)
        }

        if non_unique:
            raise PublishXmlValidationError(self, msg,
                                            formatting_data=formatting_data)
