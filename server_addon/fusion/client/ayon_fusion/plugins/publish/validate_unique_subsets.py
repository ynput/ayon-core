from collections import defaultdict

import pyblish.api
from ayon_core.pipeline import PublishValidationError

from ayon_fusion.api.action import SelectInvalidAction


class ValidateUniqueSubsets(pyblish.api.ContextPlugin):
    """Ensure all instances have a unique product name"""

    order = pyblish.api.ValidatorOrder
    label = "Validate Unique Products"
    families = ["render", "image"]
    hosts = ["fusion"]
    actions = [SelectInvalidAction]

    @classmethod
    def get_invalid(cls, context):

        # Collect instances per product per folder
        instances_per_product_folder = defaultdict(lambda: defaultdict(list))
        for instance in context:
            folder_path = instance.data["folderPath"]
            product_name = instance.data["productName"]
            instances_per_product_folder[folder_path][product_name].append(
                instance
            )

        # Find which folder + subset combination has more than one instance
        # Those are considered invalid because they'd integrate to the same
        # destination.
        invalid = []
        for folder_path, instances_per_product in (
            instances_per_product_folder.items()
        ):
            for product_name, instances in instances_per_product.items():
                if len(instances) > 1:
                    cls.log.warning(
                        (
                            "{folder_path} > {product_name} used by more than "
                            "one instance: {instances}"
                        ).format(
                            folder_path=folder_path,
                            product_name=product_name,
                            instances=instances
                        )
                    )
                    invalid.extend(instances)

        # Return tools for the invalid instances so they can be selected
        invalid = [instance.data["tool"] for instance in invalid]

        return invalid

    def process(self, context):
        invalid = self.get_invalid(context)
        if invalid:
            raise PublishValidationError(
                "Multiple instances are set to the same folder > product.",
                title=self.label
            )
