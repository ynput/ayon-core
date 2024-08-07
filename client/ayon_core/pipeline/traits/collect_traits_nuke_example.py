import pyblish.api
from ayon_core.pipeline import publish
from openassetio.trait import TraitsData
from ayon_core.pipeline.traits.generated import (
    openassetio_mediacreation as mediacreation,
    Ayon as ayon_traits,
)


class CollectImageTraits(publish.api.Instance):
    """Collect image specific traits for the instance.

    This prepares traits related to the instance itself.
    All representation specific are to be handled in the
    Extractors or plugins that are responsible for the
    specific representation. For example if representation
    should be used for review, respective trait should be
    added in the place where this is decided. Also, if
    for any reason representation has different frame range,
    appropriate trait data should be set for that representation.
    At correct place.

    TODO:
        - Add OpenAssetIO traits

    """
    order = pyblish.api.CollectorOrder + 0.1
    label = "Collect Image Traits"
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

        clip_trait = ayon_traits.traits.time.ClipTrait(data)
        clip_trait.setFrameStart(instance.data["frameStart"])
        clip_trait.setFrameEnd(instance.data["frameEnd"])
        clip_trait.setFrameRate(instance.data["fps"])
        clip_trait.setStep(instance.data["step"])
        clip_trait.setHandlesStart(instance.context.data["handleStart"])
        clip_trait.setHandlesEnd(instance.context.data["handleEnd"])

        # Add OpenAssetIO traits
        # ----------------------
        # Here, we'll add all MediaCreation traits that are relevant to the
        # instance. This is where you would add traits that are not
        # representation specific.

        # planar bitmap image information
        # TODO: DisplayWindowHeight and Width are meant to contain resolution
        #       without pixel aspect ratio factored in. Also without any
        #       overscan factored in. We need to check the workflow in Nuke
        #       and see if we need to tweak this logic.
        image_spec = mediacreation.specifications.twoDimensional.PlanarBitmapImageResourceSpecification(data)  # noqa: E501
        pixel_based = image_spec.pixelBasedTrait()
        pixel_based.setPixelAspectRatio(instance.data["pixelAspectRatio"])
        pixel_based.setDisplayWindowHeight(instance.data["width"])
        pixel_based.setResolutionHeight(instance.data["height"])

        # Store traits data on instance.
        instance.data["traits_data"] = data
        instance.data["families"].append("traits")
