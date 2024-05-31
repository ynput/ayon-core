import tempfile
import pyblish.api
from ayon_houdini.api import lib, plugin
from ayon_houdini.api.pipeline import IS_HEADLESS


class ExtractActiveViewThumbnail(plugin.HoudiniExtractorPlugin):
    """Set instance thumbnail to a screengrab of current active viewport.

    This makes it so that if an instance does not have a thumbnail set yet that
    it will get a thumbnail of the currently active view at the time of
    publishing as a fallback.

    """
    order = pyblish.api.ExtractorOrder + 0.49
    label = "Extract Active View Thumbnail"
    families = ["workfile"]

    def process(self, instance):
        if IS_HEADLESS:
            self.log.debug(
                "Skip extraction of active view thumbnail, due to being in"
                "headless mode."
            )
            return

        thumbnail = instance.data.get("thumbnailPath")
        if thumbnail:
            # A thumbnail was already set for this instance
            return

        view_thumbnail = self.get_view_thumbnail(instance)
        if not view_thumbnail:
            return
        self.log.debug("Setting instance thumbnail path to: {}"
                       .format(view_thumbnail)
        )
        instance.data["thumbnailPath"] = view_thumbnail

    def get_view_thumbnail(self, instance):

        sceneview = lib.get_scene_viewer()
        if sceneview is None:
            self.log.debug("Skipping Extract Active View Thumbnail"
                           " because no scene view was detected.")
            return

        with tempfile.NamedTemporaryFile("w", suffix=".jpg", delete=False) as tmp:
            lib.sceneview_snapshot(sceneview, tmp.name)
            thumbnail_path = tmp.name

        instance.context.data["cleanupFullPaths"].append(thumbnail_path)
        return thumbnail_path
