import os
import shutil

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
import ayon_core.hosts.harmony.api as harmony


class ImportPaletteLoader(load.LoaderPlugin):
    """Import palettes."""

    product_types = {"palette", "harmony.palette"}
    representations = {"plt"}
    label = "Import Palette"

    def load(self, context, name=None, namespace=None, data=None):
        name = self.load_palette(context["representation"])

        return harmony.containerise(
            name,
            namespace,
            name,
            context,
            self.__class__.__name__
        )

    def load_palette(self, context):
        product_name = context["product"]["name"]
        repre_entity = context["representation"]
        name = product_name.replace("palette", "")

        # Overwrite palette on disk.
        scene_path = harmony.send(
            {"function": "scene.currentProjectPath"}
        )["result"]
        src = get_representation_path(repre_entity)
        dst = os.path.join(
            scene_path,
            "palette-library",
            "{}.plt".format(name)
        )
        shutil.copy(src, dst)

        harmony.save_scene()

        msg = "Updated {}.".format(product_name)
        msg += " You need to reload the scene to see the changes.\n"
        msg += "Please save workfile when ready and use Workfiles "
        msg += "to reopen it."

        harmony.send(
            {
                "function": "PypeHarmony.message",
                "args": msg
            })
        return name

    def remove(self, container):
        harmony.remove(container["name"])

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        self.remove(container)
        name = self.load_palette(context)

        repre_entity = context["representation"]
        container["representation"] = repre_entity["id"]
        container["name"] = name
        harmony.imprint(name, container)
