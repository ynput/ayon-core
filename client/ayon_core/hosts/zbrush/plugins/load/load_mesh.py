import os
from ayon_core.pipeline import load, get_representation_path
from ayon_core.hosts.zbrush.api.pipeline import (
    containerise, remove_container_data, imprint
)
from ayon_core.hosts.zbrush.api.lib import execute_zscript, remove_subtool


class MeshLoader(load.LoaderPlugin):
    """Zbrush Model Loader."""

    families = ["model"]
    representations = ["abc", "fbx", "obj", "ma"]
    order = -9
    icon = "code-fork"
    color = "white"

    def load(self, context, name=None, namespace=None, data=None):
        file_path = os.path.normpath(self.filepath_from_context(context))
        load_zscript = ("""
[IFreeze,
[VarSet, filename, "{filepath}"]
[FileNameSetNext, #filename]
[IKeyPress, 13, [IPress, Tool:Import:Import]]
]

""").format(filepath=file_path, name=name)
        execute_zscript(load_zscript)

        return containerise(
            name,
            context,
            loader=self.__class__.__name__)

    def update(self, container, context):
        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        load_zscript = ("""
[IFreeze,
[VarSet, filename, "{filepath}"]
[FileNameSetNext, #filename]
[IKeyPress, 13, [IPress, Tool:Import:Import]]
]

""").format(filepath=path)
        execute_zscript(load_zscript)
        representation_id = str(repre_entity["_id"])
        imprint(container, representation_id)

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        # TODO: figure out how to delete imported object
        # remove the bind with the container data
        remove_subtool(container["objectName"])
        return remove_container_data(container["objectName"])
