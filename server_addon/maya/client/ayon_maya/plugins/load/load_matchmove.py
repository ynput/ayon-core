from ayon_maya.api import plugin
from maya import mel


class MatchmoveLoader(plugin.Loader):
    """
    This will run matchmove script to create track in scene.

    Supported script types are .py and .mel
    """

    product_types = {"matchmove"}
    representations = {"py", "mel"}
    defaults = ["Camera", "Object", "Mocap"]

    label = "Run matchmove script"
    icon = "empire"
    color = "orange"

    def load(self, context, name, namespace, data):
        path = self.filepath_from_context(context)
        if path.lower().endswith(".py"):
            exec(open(path).read())

        elif path.lower().endswith(".mel"):
            mel.eval('source "{}"'.format(path))

        else:
            self.log.error("Unsupported script type")

        return True
