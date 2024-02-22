    import os
import nuke
import pyblish.api
from openpype.hosts.nuke import api as napi
from openpype.pipeline import publish
from openassetio.trait import TraitsData
from openpype.pipeline.traits.generated import (
    openassetio_mediacreation as traits,
    ayon as ayon_traits,
)


class CollectTraits(publish.api.Instance):
    """Collect traits for the instance.

    This prepares traits related to the instance itself.
    All representation specific needs to be handled in the
    Extractors or plugins that are responsible for the
    specific representation.

    TODO:
        - Add OpenAssetIO traits

    """
    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Traits"
    hosts = ["nuke", "nukeassist"]
    families = ["render", "prerender", "image"]

    def process(self, instance):
        data = TraitsData()

        # Add Ayon traits
        # ---------------
        # TransientTrait marks the data as transient, meaning it will be
        # deleted after the process is done. It should be changed to permanent
        # when the data is integrated into the database.
        transient = ayon_traits.traits.core.TransientTrait(data)
        transient.setLifetime("process")

        # ProductTrait is used to mark the data as a product, and to set the
        # product name. Formerly, this was subset name.
        ayon_traits.traits.core.ProductTrait(
            data).setProductName = instance.data["productName"]

        # Add OpenAssetIO traits
        # ----------------------
        # Here, we'll add all MediaCreation traits that are relevant to the
        # instance. This is where you would add traits that are not
        # representation specific.

        # Store trait set on instance.
        instance.data["trait_set"] = trait_set
