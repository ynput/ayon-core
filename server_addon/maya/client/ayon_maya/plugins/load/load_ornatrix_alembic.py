from maya import cmds
from ayon_core.pipeline import get_representation_path
from ayon_maya.api import plugin
from ayon_maya.api.lib import unique_namespace, maintained_selection
from ayon_core.lib import EnumDef



class OxAlembicLoader(plugin.ReferenceLoader):
    """Ornatrix Alembic Loader"""

    product_types = {"oxcache"}
    representations = {"abc"}

    label = "Ornatrix Alembic Loader"
    order = -10
    icon = "code-fork"
    color = "orange"

    @classmethod
    def get_options(cls, contexts):
        return cls.options + [
            EnumDef(
                "import_options",
                items={
                    0: "Hair",
                    1: "Guides"
                },
                default=0
            )
        ]

    def process_reference(self, context, name, namespace, options):
        cmds.loadPlugin("Ornatrix", quiet=True)
        folder_name = context["folder"]["name"]
        namespace = namespace or unique_namespace(
            folder_name + "_",
            prefix="_" if folder_name[0].isdigit() else "",
            suffix="_",
        )

        attach_to_root = options.get("attach_to_root", True)
        group_name = options["group_name"]

        # no group shall be created
        if not attach_to_root:
            group_name = namespace

        path = self.filepath_from_context(context)
        ox_import_options = "; importAs={}".format(
            options.get("import_options"))

        with maintained_selection():
            file_url = self.prepare_root_value(
                path, context["project"]["name"]
            )
            nodes = cmds.file(
                file_url,
                type="Ornatrix Alembic Import",
                namespace=namespace,
                groupName=group_name,
                options=ox_import_options
            )

        color = plugin.get_load_color_for_product_type("oxcache")
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_name + ".useOutlinerColor", 1)
            cmds.setAttr(
                group_name + ".outlinerColor", red, green, blue
            )

        self[:] = nodes

        return nodes

    def update(self, container, context):
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        members = cmds.sets(container['objectName'], query=True)
        ox_nodes = cmds.ls(members, type="BakedHairNode", long=True)
        for node in ox_nodes:
            cmds.setAttr(f"{node}.sourceFilePath1", path, type="string")

    def switch(self, container, context):
        self.update(container, context)
