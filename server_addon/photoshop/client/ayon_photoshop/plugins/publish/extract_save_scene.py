from ayon_core.pipeline import publish
from ayon_photoshop import api as photoshop


class ExtractSaveScene(publish.Extractor):
    """Save scene before extraction."""

    order = publish.Extractor.order - 0.49
    label = "Extract Save Scene"
    hosts = ["photoshop"]
    families = ["workfile"]

    def process(self, instance):
        photoshop.stub().save()
