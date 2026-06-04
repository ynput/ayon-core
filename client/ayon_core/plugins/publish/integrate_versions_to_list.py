"""Pyblish context plugin that adds published versions to AYON entity lists.

For each instance with ``versionLists`` data, creates or updates the named
lists (optionally typed as ``review-session``) and organizes them under the
requested folder hierarchy on the server.
"""

from __future__ import annotations

import platform
from collections import defaultdict
from copy import deepcopy
from typing import TYPE_CHECKING

import ayon_api
import pyblish.api
from ayon_api.utils import create_entity_id
from ayon_core.lib import StringTemplate
from ayon_core.pipeline.structures import ListConfig

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy


# TODO: ayon_api future compatibility, remove once ayon_api supports it
def create_entity_list_item(
    project_name: str,
    list_id: str,
    entity_id: str,
) -> str:
    """Create entity list item.

    Args:
        project_name (str): Project name where entity list lives.
        list_id (str): Entity list id where item will be added.
        entity_id (str): Id of entity added to the list.

    Returns:
        str: Item id.

    """
    item_id = create_entity_id()
    kwargs = {
        "id": item_id,
        "entityId": entity_id,
    }

    response = ayon_api.post(
        f"projects/{project_name}/lists/{list_id}/items",
        **kwargs
    )
    response.raise_for_status()
    return item_id


# TODO: ayon_api future compatibility, remove once ayon_api supports it
def create_entity_list_folder(
    project_name: str,
    folder_name: str,
    parent_folder_id: str | None = None,
) -> str:
    kwargs = {
        "id": create_entity_id(),
        "label": folder_name,
    }
    if parent_folder_id:
        kwargs["parentId"] = parent_folder_id
    response = ayon_api.post(
        f"projects/{project_name}/entityListFolders",
        **kwargs,
    )
    response.raise_for_status()
    return response.data["id"]


# TODO: ayon_api future compatibility, remove once ayon_api supports it
def get_entity_list_folders(project_name: str) -> list[dict]:
    response = ayon_api.get(
        f"projects/{project_name}/entityListFolders",
    )
    response.raise_for_status()
    return response.data["folders"]


class IntegrateVersionToList(pyblish.api.ContextPlugin):
    """Integrate published versions to a list.

    This plugin integrates published versions to a list in the server.

    Note that list names are unique; as such, even if multiple list configs
    are set to go to different folders but with the same list name - then all
    versions will be integrated to the same list regardless of what list folder
    it is in.
    """

    label = "Integrate Versions to List"
    order = pyblish.api.IntegratorOrder + 0.49

    def process(self, context):
        list_config_by_list_name: dict[str, ListConfig] = {}
        version_ids_by_list_name: dict[str, list[str]] = defaultdict(list)
        for instance in context:
            version_lists: list[ListConfig] = instance.data.get(
                "versionLists", [])
            version_entity = instance.data.get("versionEntity")
            if not version_entity or not version_lists:
                continue
            for list_config in version_lists:
                # Construct the list config with the formatted name and parent
                # folder names
                anatomy: Anatomy = instance.context.data["anatomy"]
                template_keys = deepcopy(instance.data["anatomyData"])
                template_keys.update({
                    "root": anatomy.roots,
                    "platform": platform.system().lower(),
                })
                list_name: str = str(
                    StringTemplate.format_strict_template(
                        list_config.name, template_keys
                    )
                )
                parent_folders: list[str] | None
                if parent_folders := list_config.parent_folders:
                    parent_folders = [
                        str(StringTemplate.format_template(
                            folder,
                            template_keys
                        ))
                        for folder in parent_folders
                    ]

                # Define the list config, and add the version id to the list
                list_config_by_list_name[list_name] = ListConfig(
                    name=list_name,
                    parent_folders=parent_folders,
                    list_type=list_config.list_type,
                )
                version_ids_by_list_name[list_name].append(
                    version_entity["id"]
                )

        # Get all list entities for the project from server
        project_name: str = context.data["projectName"]
        existing_list_entities_by_label: dict[str, dict] = {
            entity_list["label"]: entity_list
            for entity_list in ayon_api.get_entity_lists(
                project_name=project_name
            )
        }
        for list_name, list_config in list_config_by_list_name.items():
            version_ids = version_ids_by_list_name[list_name]
            if not version_ids:
                self.log.debug(f"No version ids for list: {list_name}")
                continue

            # If list exists, append to it but ensure it is of correct type
            existing_list = existing_list_entities_by_label.get(list_name)
            if existing_list:
                if existing_list["entityListType"] != list_config.list_type:
                    entity_list_type = existing_list["entityListType"]
                    self.log.error(
                        "Can't add versions to list because another entity"
                        f" list type '{entity_list_type}' with that label"
                        f" already exists: {list_config.name}"
                    )
                    continue

                if existing_list["entityType"] != "version":
                    entity_type = existing_list["entityType"]
                    self.log.error(
                        f"Can't add versions to list because a '{entity_type}'"
                        " list type with that label already exists: "
                        f"{list_config.name}"
                    )
                    continue

                self._append_to_entity_list(
                    project_name=project_name,
                    list_entity=existing_list,
                    version_ids=version_ids,
                )

            # Else create the new list
            else:
                # make sure parent folder exists
                entity_list_folder_id = self._get_or_create_parent_folder(
                    project_name=project_name,
                    parent_folders=list_config.parent_folders,
                )
                # then create list under a parent folder
                self._create_entity_list(
                    project_name=project_name,
                    entity_type="version",
                    label=list_config.name,
                    list_type=list_config.list_type,
                    entity_list_folder_id=entity_list_folder_id,
                    items=[
                        {"entityId": version_id}
                        for version_id in version_ids
                    ],
                )

    def _get_or_create_parent_folder(
        self,
        project_name: str,
        parent_folders: list[str] | None,
    ) -> str | None:
        # TODO: Should we apply 'data.scopes' to the folder to make the folder
        #  list only under e.g. generic list or review-sessions lists instead
        #  of scoped to both.
        if not parent_folders:
            return None

        existing_list_folders = get_entity_list_folders(
            project_name=project_name
        )
        parent_folder_id = None
        for folder_name in parent_folders:
            # make sure to get existing folder id if it exists
            # and use it instead of creating a new one
            for list_folder in existing_list_folders:
                if list_folder["parentId"] != parent_folder_id:
                    continue
                if list_folder["label"] != folder_name:
                    continue
                parent_folder_id = list_folder["id"]
                break
            else:
                # if folder does not exist, create it under the parent folder
                parent_folder_id = create_entity_list_folder(
                    project_name=project_name,
                    folder_name=folder_name,
                    parent_folder_id=parent_folder_id,
                )
        return parent_folder_id

    def _append_to_entity_list(
        self,
        project_name: str,
        list_entity: dict,
        version_ids: list[str] | None = None,
    ):
        """Append version ids to the entity list as items."""
        if version_ids is None:
            return

        for entity_id in version_ids:
            item_id = create_entity_list_item(
                project_name=project_name,
                list_id=list_entity["id"],
                entity_id=entity_id,
            )
            self.log.info(
                f"Created entity list item {item_id} for version {entity_id}"
                f" in list {list_entity['label']}"
            )

    def _create_entity_list(
        self,
        project_name: str,
        entity_type: str,
        label: str,
        items: list[dict],
        list_type: str | None = None,
        entity_list_folder_id: str | None = None,
    ) -> dict:
        """Create a new list parented to the entity list folder."""
        kwargs = {
            "id": create_entity_id(),
            "entityType": entity_type,
            "label": label,
            "items": items,
        }
        for key, value in (
            ("entityListType", list_type),
            ("entityListFolderId", entity_list_folder_id),
        ):
            if value is not None:
                kwargs[key] = value

        self.log.debug(f"Creating entity list: {kwargs}")
        response = ayon_api.post(
            f"projects/{project_name}/lists",
            **kwargs
        )
        response.raise_for_status()
        self.log.debug(f"Entity list created: {response.data}")
        return response.data
