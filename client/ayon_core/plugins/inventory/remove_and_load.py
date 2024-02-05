from ayon_core.pipeline import InventoryAction
from ayon_core.pipeline import get_current_project_name
from ayon_core.pipeline.load.plugins import discover_loader_plugins
from ayon_core.pipeline.load.utils import (
    get_loader_identifier,
    remove_container,
    load_container,
)
from ayon_core.client import get_representation_by_id


class RemoveAndLoad(InventoryAction):
    """Delete inventory item and reload it."""

    label = "Remove and load"
    icon = "refresh"

    def process(self, containers):
        project_name = get_current_project_name()
        loaders_by_name = {
            get_loader_identifier(plugin): plugin
            for plugin in discover_loader_plugins(project_name=project_name)
        }
        for container in containers:
            # Get loader
            loader_name = container["loader"]
            loader = loaders_by_name.get(loader_name, None)
            if not loader:
                raise RuntimeError(
                    "Failed to get loader '{}', can't remove "
                    "and load container".format(loader_name)
                )

            # Get representation
            representation = get_representation_by_id(
                project_name, container["representation"]
            )
            if not representation:
                self.log.warning(
                    "Skipping remove and load because representation id is not"
                    " found in database: '{}'".format(
                        container["representation"]
                    )
                )
                continue

            # Remove container
            remove_container(container)

            # Load container
            load_container(loader, representation)
