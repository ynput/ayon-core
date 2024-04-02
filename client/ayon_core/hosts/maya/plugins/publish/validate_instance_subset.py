import pyblish.api
import string

import six
from ayon_core.pipeline.publish import (
    ValidateContentsOrder,
    PublishValidationError
)

# Allow only characters, numbers and underscore
allowed = set(string.ascii_lowercase +
              string.ascii_uppercase +
              string.digits +
              '_')


def validate_name(product_name):
    return all(x in allowed for x in product_name)


class ValidateSubsetName(pyblish.api.InstancePlugin):
    """Validates product name has only valid characters"""

    order = ValidateContentsOrder
    families = ["*"]
    label = "Product Name"

    def process(self, instance):

        product_name = instance.data.get("productName", None)

        # Ensure product data
        if product_name is None:
            raise PublishValidationError(
                "Instance is missing product name: {0}".format(product_name)
            )

        if not isinstance(product_name, six.string_types):
            raise PublishValidationError((
                "Instance product name must be string, got: {0} ({1})"
            ).format(product_name, type(product_name)))

        # Ensure is not empty product
        if not product_name:
            raise PublishValidationError(
                "Instance product name is empty: {0}".format(product_name)
            )

        # Validate product characters
        if not validate_name(product_name):
            raise PublishValidationError((
                "Instance product name contains invalid characters: {0}"
            ).format(product_name))
