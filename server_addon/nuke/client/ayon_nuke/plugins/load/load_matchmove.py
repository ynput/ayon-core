import nuke
from ayon_core.pipeline import load


class MatchmoveLoader(load.LoaderPlugin):
    """
    This will run matchmove script to create track in script.
    """

    product_types = {"matchmove"}
    representations = {"*"}
    extensions = {"py"}

    settings_category = "nuke"

    defaults = ["Camera", "Object"]

    label = "Run matchmove script"
    icon = "empire"
    color = "orange"

    def load(self, context, name, namespace, data):
        path = self.filepath_from_context(context)
        if path.lower().endswith(".py"):
            exec(open(path).read())

        else:
            msg = "Unsupported script type"
            self.log.error(msg)
            nuke.message(msg)

        return True
