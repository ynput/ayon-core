import os
import pyblish.api
from ayon_core.lib import EnumDef
from ayon_core.pipeline import publish, OptionalPyblishPluginMixin
from ayon_core.hosts.zbrush.api.lib import execute_publish_model_with_dialog


class ExtractPolyMesh(publish.Extractor,
                      OptionalPyblishPluginMixin):
    """
    Extract PolyMesh(.ma, .fbx, .abc, .obj) in Zbrush
    """

    order = pyblish.api.ExtractorOrder - 0.05
    label = "Extract PolyMesh"
    hosts = ["zbrush"]
    families = ["model"]
    export_format = "fbx"
    optional = True

    def process(self, instance):
        if not self.is_active(instance.data):
            return

        attr_values = self.get_attr_values_from_data(instance.data)
        export_format = attr_values.get("exportFormat")
        stagingdir = self.staging_dir(instance)
        filename = f"{instance.name}.{export_format}"
        filepath = os.path.join(stagingdir, filename)

        if "representations" not in instance.data:
            instance.data["representations"] = []

        resolve_filepath = filepath.replace("\\", "/")
        execute_publish_model_with_dialog(resolve_filepath)
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

    @classmethod
    def get_attribute_defs(cls):
        defs = super(ExtractPolyMesh, cls).get_attribute_defs()
        export_format_enum = ["abc", "fbx", "ma", "obj"]
        defs.extend([
            EnumDef("exportFormat",
                    export_format_enum,
                    default=cls.export_format,
                    label="Export Format Options"),
        ])

        return defs
