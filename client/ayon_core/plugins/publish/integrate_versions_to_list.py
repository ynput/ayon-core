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

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.structures import ListConfig, ListConfigFolder


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
def update_entity_list_folder(
    project_name: str,
    folder_id: str,
    data: dict,
) -> None:
    response = ayon_api.patch(
        f"projects/{project_name}/entityListFolders/{folder_id}",
        data=data,
    )
    response.raise_for_status()


# TODO: ayon_api future compatibility, remove once ayon_api supports it
def create_entity_list_folder(
    project_name: str,
    list_folder: ListConfigFolder,
    parent_folder_id: str | None,
) -> str:
    data = {}
    for key, value in (
        ("color", list_folder.color),
        ("icon", list_folder.icon),
        ("scope", list_folder.scope),
    ):
        if value is not None:
            data[key] = value

    kwargs = {
        "id": create_entity_id(),
        "label": list_folder.label,
    }
    if data:
        kwargs["data"] = data

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
    settings_category = "core"

    def process(self, context):
        list_config_by_list_name: dict[str, ListConfig] = {}
        version_ids_by_list_name: dict[str, list[str]] = defaultdict(list)

        anatomy: Anatomy = context.data["anatomy"]
        for instance in context:
            version_lists: list[ListConfig] = instance.data.get(
                "versionLists", []
            )
            if not version_lists:
                continue

            version_entity = instance.data.get("versionEntity")
            if not version_entity:
                continue

            has_webreview = instance.data.get("hasWebreview", False)
            for list_config in version_lists:
                # Skip review-session lists if instance does not have review
                if (
                    not has_webreview
                    and list_config.list_type == "review-session"
                ):
                    continue
                # Construct the list config with the formatted name and parent
                # folder names
                template_data = deepcopy(instance.data["anatomyData"])
                template_data.update({
                    "root": anatomy.roots,
                    "platform": platform.system().lower(),
                })
                try:
                    list_name: str = str(
                        StringTemplate.format_strict_template(
                            list_config.name, template_data
                        )
                    )
                except Exception:
                    self.log.error(
                        "Failed to fill entity list name template: "
                        f"{list_config.name}",
                        exc_info=True,
                    )
                    continue

                existing_config = list_config_by_list_name.get(list_name)
                if (
                    existing_config
                    and existing_config.list_type != list_config.list_type
                ):
                    self.log.error(
                        "Conflicting list_type for entity list label "
                        f"'{list_name}': '{existing_config.list_type}' vs "
                        f"'{list_config.list_type}'. Skipping."
                    )
                    continue

                # Add version to lists mapping
                version_ids_by_list_name[list_name].append(
                    version_entity["id"]
                )

                # Fill label using template data
                candidate_config = deepcopy(list_config)
                for folder in list_config.list_folders:
                    folder.label = str(StringTemplate.format_template(
                        folder.label, template_data
                    ))

                # Use candadate config
                if existing_config is None:
                    list_config_by_list_name[list_name] = candidate_config
                    continue

                # Compare folders of the existing config and the candidate
                #   config. Does not affect output but logs a warning if
                #   they differ.
                existing_labels = [
                    folder.label
                    for folder in existing_config.list_folders
                ]
                candidate_labels = [
                    folder.label
                    for folder in candidate_config.list_folders
                ]
                if existing_labels != candidate_labels:
                    self.log.warning(
                        "Configuration does contain different folders from"
                        f" existing list '{list_name}'. Keeping existing list"
                        f" folders. Existing: {existing_labels}"
                        f" vs Candidate: {candidate_labels}"
                    )

        if not list_config_by_list_name:
            return

        # Get all list entities for the project from server
        project_name: str = context.data["projectName"]
        existing_list_entities_by_label: dict[str, dict] = {
            entity_list["label"]: entity_list
            for entity_list in ayon_api.get_entity_lists(project_name)
        }
        existing_list_folders = get_entity_list_folders(project_name)

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
                entity_list_folder_id = self._create_list_folders(
                    project_name=project_name,
                    list_config=list_config,
                    existing_list_folders=existing_list_folders,
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

    def _create_list_folders(
        self,
        project_name: str,
        list_config: ListConfig,
        existing_list_folders: list[dict],
    ) -> str | None:
        """Returns folder id of the last folder in the hierarchy."""
        if not list_config.list_folders:
            return None

        parent_folder_id = None
        for list_folder in list_config.list_folders:
            # make sure to get existing folder id if it exists
            # and use it instead of creating a new one
            for existing_list_folder in existing_list_folders:
                if (
                    existing_list_folder["parentId"] == parent_folder_id
                    and existing_list_folder["label"] == list_folder.label
                ):
                    # If folder exists, check if scope needs to be updated
                    #   with the list type.
                    # NOTE If scope is None or empty list it is scoped for
                    #   everything. So the list type is added to scope only
                    #   if scope exists and does not contain the list type.
                    scope = existing_list_folder["data"].get("scope")
                    if scope and list_config.list_type not in scope:
                        scope.append(list_config.list_type)
                        update_entity_list_folder(
                            project_name,
                            existing_list_folder["id"],
                            data={"scope": scope},
                        )
                    parent_folder_id = existing_list_folder["id"]
                    break
            else:
                # if folder does not exist, create it under the parent folder
                new_folder_id = create_entity_list_folder(
                    project_name=project_name,
                    list_folder=list_folder,
                    parent_folder_id=parent_folder_id,
                )
                # Add new fake folder entity to existing folders
                existing_list_folders.append({
                    "label": list_folder.label,
                    "parentId": parent_folder_id,
                    "id": new_folder_id,
                    "data": {
                        "scope": list(list_folder.scope),
                    },
                })
                parent_folder_id = new_folder_id
        return parent_folder_id

    def _append_to_entity_list(
        self,
        project_name: str,
        list_entity: dict,
        version_ids: list[str],
    ) -> None:
        """Append version ids to the entity list as items."""
        for entity_id in version_ids:
            item_id = create_entity_list_item(
                project_name=project_name,
                list_id=list_entity["id"],
                entity_id=entity_id,
            )
            self.log.debug(
                f"Created entity list item {item_id} for version {entity_id}"
                f" in list {list_entity['label']}"
            )

    def _create_entity_list(
        self,
        project_name: str,
        entity_type: str,
        label: str,
        items: list[dict],
        list_type: str,
        entity_list_folder_id: str | None,
    ) -> dict:
        """Create a new list parented to the entity list folder."""
        kwargs = {
            "id": create_entity_id(),
            "entityType": entity_type,
            "label": label,
            "items": items,
            "entityListType": list_type,
        }
        for key, value in (
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
