"""Import workfiles into your current comp.
As all imported nodes are free floating and will probably be changed there
is no update or reload function added for this plugin
"""

from ayon_core.pipeline import load

from ayon_fusion.api import (
    get_current_comp,
    get_bmd_library,
)


class FusionLoadWorkfile(load.LoaderPlugin):
    """Load the content of a workfile into Fusion"""

    product_types = {"workfile"}
    representations = {"*"}
    extensions = {"comp"}

    label = "Load Workfile"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        # Get needed elements
        bmd = get_bmd_library()
        comp = get_current_comp()
        path = self.filepath_from_context(context)

        # Paste the content of the file into the current comp
        comp.Paste(bmd.readfile(path))
