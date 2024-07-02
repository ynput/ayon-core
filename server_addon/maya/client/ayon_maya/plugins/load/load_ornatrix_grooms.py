
from ayon_core.settings import get_project_settings
from ayon_maya.api import lib
from ayon_maya.api.pipeline import containerise
from ayon_maya.api import plugin
from ayon_maya.api.plugin import get_load_color_for_product_type
from maya import cmds, mel


class OxOrnatrixGrooms(plugin.Loader):
    """Load Ornatrix Grooms"""

    product_types = {"oxrig"}
    representations = {"oxg.zip"}

    label = "Load Ornatrix Grooms"
    order = -9
    icon = "code-fork"

    def load(self, context, name=None, namespace=None, data=None):
        # Check if the plugin for Ornatrix is available on the pc
        try:
            cmds.loadPlugin("Ornatrix", quiet=True)
        except Exception as exc:
            self.log.error("Encountered exception:\n%s" % exc)
            return

        # prevent loading the presets with the selected meshes
        cmds.select(deselect=True)

        product_type = context["product"]["productType"]
        # Build namespace
        folder_name = context["folder"]["name"]
        if namespace is None:
            namespace = self.create_namespace(folder_name)


        path = self.filepath_from_context(context)
        path = path.replace("\\", "/")

        nodes = [mel.eval(f'OxLoadGroom -path "{path}";')]

        group_name = "{}:{}".format(namespace, name)
        group_node = cmds.group(nodes, name=group_name)
        project_name = context["project"]["name"]

        settings = get_project_settings(project_name)
        color = get_load_color_for_product_type(product_type, settings)
        if color is not None:
            red, green, blue = color
            cmds.setAttr(group_node + ".useOutlinerColor", 1)
            cmds.setAttr(group_node + ".outlinerColor", red, green, blue)

        nodes.append(group_node)

        self[:] = nodes

        return containerise(
            name=name,
            namespace=namespace,
            nodes=nodes,
            context=context,
            loader=self.__class__.__name__
        )


    def remove(self, container):

        namespace = container["namespace"]
        nodes = container["nodes"]

        self.log.info("Removing '%s' from Maya.." % container["name"])

        nodes = cmds.ls(nodes, long=True)

        try:
            cmds.delete(nodes)
        except ValueError:
            # Already implicitly deleted by Maya upon removing reference
            pass

        cmds.namespace(removeNamespace=namespace, deleteNamespaceContent=True)

    def create_namespace(self, folder_name):
        """Create a unique namespace
        Args:
            asset (dict): asset information

        """

        asset_name = "{}_".format(folder_name)
        prefix = "_" if asset_name[0].isdigit() else ""
        namespace = lib.unique_namespace(
            asset_name,
            prefix=prefix,
            suffix="_"
        )

        return namespace
