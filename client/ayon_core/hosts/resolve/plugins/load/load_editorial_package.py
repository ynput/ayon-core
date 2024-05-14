from ayon_core.pipeline import (
    load,
    get_representation_path,
)



class LoadEditorialPackage(load.LoaderPlugin):
    """Load editorial package to timeline.

    Loading timeline from OTIO file included media sources
    and timeline structure.
    """

    product_types = {"editorial_pckg"}

    representations = {"*"}
    extensions = {"otio"}

    label = "Load as Timeline"
    order = -10
    icon = "code-fork"
    color = "orange"

    def load(self, context, name, namespace, data):
        # load clip to timeline and get main variables
        files = get_representation_path(context["representation"])

        print("Loading editorial package: ", files)
