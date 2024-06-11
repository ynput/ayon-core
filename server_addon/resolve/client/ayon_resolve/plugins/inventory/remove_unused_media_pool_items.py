from ayon_core.pipeline import (
    InventoryAction,
)
from ayon_core.pipeline.load.utils import remove_container


class RemoveUnusedMedia(InventoryAction):

    label = "Remove Unused Media"
    icon = "trash"

    @staticmethod
    def is_compatible(container):
        return (
            container.get("loader") == "LoadMedia"
        )

    def process(self, containers):
        any_removed = False
        for container in containers:
            media_pool_item = container["_item"]
            usage = int(media_pool_item.GetClipProperty("Usage"))
            name = media_pool_item.GetName()
            if usage == 0:
                print(f"Removing {name}")
                remove_container(container)
                any_removed = True
            else:
                print(f"Keeping {name} with usage: {usage}")

        return any_removed
