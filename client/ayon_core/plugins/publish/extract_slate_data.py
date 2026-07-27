import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.pipeline.publish.representation import repre_get, repre_set


class ExtractSlateData(publish.Extractor):
    """Add slate data for integration."""

    label = "Slate Data"
    # Offset from ExtractReviewSlate and ExtractGenerateSlate.
    order = pyblish.api.ExtractorOrder + 0.49
    families = ["slate", "review"]
    hosts = ["nuke", "shell"]

    def process(self, instance):
        for representation in instance.data.get("representations", []):
            if "slate-frame" not in repre_get(representation, "tags", []):
                continue

            data = repre_get(representation, "data") or {}
            data["slateFrames"] = 1
            repre_set(representation, "data", data)
