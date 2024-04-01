import ayon_api

from ayon_core.pipeline import get_current_project_name, InventoryAction
from ayon_core.pipeline.load.plugins import discover_loader_plugins
from ayon_core.pipeline.load.utils import (
    get_loader_identifier,
    remove_container,
    load_container,
)


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
        repre_ids = set()
        for container in containers:
            # Get loader
            loader_name = container["loader"]
            loader = loaders_by_name.get(loader_name, None)
            if not loader:
                raise RuntimeError(
                    "Failed to get loader '{}', can't remove "
                    "and load container".format(loader_name)
                )
            repre_ids.add(container["representation"])

        repre_entities_by_id = {
            repre_entity["id"]: repre_entity
            for repre_entity in ayon_api.get_representations(
                project_name, representation_ids=repre_ids
            )
        }
        for container in containers:
            # Get representation
            repre_id = container["representation"]
            repre_entity = repre_entities_by_id.get(repre_id)
            if not repre_entity:
                self.log.warning(
                    "Skipping remove and load because representation id is not"
                    " found in database: '{}'".format(
                        repre_id
                    )
                )
                continue

            # Remove container
            remove_container(container)

            # Load container
            load_container(loader, repre_entity)
