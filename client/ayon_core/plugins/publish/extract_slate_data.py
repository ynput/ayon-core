import pyblish.api

from ayon_core.pipeline import publish


class ExtractSlateData(publish.Extractor):
    """Add slate data for integration."""

    label = "Slate Data"
    # Offset from ExtractReviewSlate and ExtractGenerateSlate.
    order = pyblish.api.ExtractorOrder + 0.49
    families = ["slate", "review"]
    hosts = ["nuke", "shell"]

    def process(self, instance):
        for representation in instance.data.get("representations", []):
            if "slate-frame" not in representation.get("tags", []):
                continue

            data = representation.get("data", {})
            data["slateFrames"] = 1
            representation["data"] = data
