import os
import pyblish.api
from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import (
    AYONPyblishPluginMixin
)

from ayon_core.hosts.zbrush.api.lib import export_tool


class ExtractModel(publish.Extractor,
                   AYONPyblishPluginMixin):
    """
    Extract PolyMesh(.fbx, .abc, .obj) in Zbrush
    """

    order = pyblish.api.ExtractorOrder - 0.05
    label = "Extract Model"
    hosts = ["zbrush"]
    families = ["model"]

    def process(self, instance):
        creator_attrs = instance.data["creator_attributes"]
        subd_level = creator_attrs.get("subd_level")
        export_format = creator_attrs.get("exportFormat")
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.{export_format}"
        filepath = os.path.join(stagingdir, filename)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        export_tool(filepath, subd_level)
        representation = {
            "name": export_format,
            "ext": export_format,
            "files": filename,
            "stagingDir": stagingdir,
        }

        instance.data["representations"].append(representation)
        self.log.info(
            "Extracted instance '%s' to: %s" % (instance.name, filepath)
        )
