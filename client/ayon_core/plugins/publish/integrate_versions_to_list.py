from __future__ import annotations

from typing import TYPE_CHECKING

import ayon_api
from ayon_api.utils import create_entity_id
import pyblish.api

if TYPE_CHECKING:
    from ayon_core.plugins.publish.collect_version_to_list import ListConfig



class IntegrateVersionToList(pyblish.api.ContextPlugin):
    """Integrate published versions to a list

    This plugin integrates published versions to a list in the server.
    """

    label = "Integrate Versions to List"
    order = pyblish.api.IntegratorOrder + 0.49

    def process(self, context):
        project_name = context.data["projectName"]
        list_name_mapping = {}
        # TODO:
        #    - check if list with the name already exists
        #    - if exists:
        #         - append version to the list
        #         - parent folders are ignored
        #    - if not exists:
        #         - create a new list and create
        #         - create parent folders if specified
        for instance in context:
            version_lists: list[ListConfig] = instance.data.get(
                "versionLists", [])
            version_entity = instance.data.get("versionEntity")
            if not version_entity or not version_lists:
                continue
            for list_config in version_lists:
                list_data = list_name_mapping.setdefault(
                    list_config.name, {})
                list_data.update({
                    "parent_folders": list_config.parent_folders,
                    "is_review_list": list_config.is_review_list,
                })
                version_ids = list_data.setdefault(
                    "version_ids", [])
                version_ids.append(version_entity["id"])

        for list_label, list_data in list_name_mapping.items():
            version_ids = list_data["version_ids"]
            is_review_list = list_data["is_review_list"]
            parent_folders = list_data["parent_folders"]
            # check first if list exists
            existing_list = self._existing_list(
                project_name=project_name,
                list_label=list_label,
                list_type="review-session" if is_review_list else None,
            )
            if existing_list:
                self._update_entity_list(
                    project_name=project_name,
                    list_entity=existing_list,
                    version_ids=version_ids,
                )
            else:
                entity_list_folder_id = None
                # make sure parent folder exists
                if parent_folders:
                    entity_list_folder_id = self._get_or_create_parent_folder(
                        project_name=project_name,
                        parent_folders=parent_folders,
                    )
                # then create list under a parent folder
                self._create_entity_list(
                    list_type="review-session" if is_review_list else None,
                    project_name=project_name,
                    entity_type="version",
                    label=list_label,
                    entity_list_folder_id=entity_list_folder_id,
                    items=[
                        {"entityId": version_id}
                        for version_id in version_ids
                    ],
                )

    def _get_or_create_parent_folder(
        self,
        project_name: str,
        parent_folders: list[str],
    ) -> str | None:
        if not parent_folders:
            return None
        existing_list_folders = self._get_list_folders_helper(
            project_name=project_name
        )
        parent_folder_id = None
        for folder_name in parent_folders:
            # make sure to get existing folder id if it exists
            # and use it instead of creating a new one
            existing_list_folder_id = None
            for list_folder in existing_list_folders:
                if list_folder["label"] == folder_name:
                    existing_list_folder_id = list_folder["id"]
                    break
            if existing_list_folder_id:
                parent_folder_id = existing_list_folder_id
                continue
            # if folder does not exist, create it
            # under the existing parent folder
            parent_folder_id = self._create_list_folder_helper(
                project_name=project_name,
                folder_name=folder_name,
                parent_folder_id=parent_folder_id,
            )
        return parent_folder_id

    def _create_list_folder_helper(
        self,
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
        self.log.debug(f"List folder created: {response.json()}")
        return response.json()["id"]

    def _get_list_folders_helper(
        self,
        project_name: str,
    ) -> list[dict]:
        response = ayon_api.get(
            f"projects/{project_name}/entityListFolders",
        )
        response.raise_for_status()
        self.log.debug(f"List folders: {response.json()}")
        return response.json()["folders"]

    def _update_entity_list(
        self,
        project_name: str,
        list_entity: dict,
        version_ids: list[str] | None = None,
    ):
        if version_ids is None:
            return

        for entity_id in version_ids:
            item_id = ayon_api.create_entity_list_item(
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
        list_type: str | None = None,
        entity_list_folder_id: str | None = None,
        items: list[dict] | None = None,
    ) -> dict:
        kwargs = {
            "id": create_entity_id(),
            "entityType": entity_type,
            "label": label,
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
        self.log.debug(f"Entity list created: {response.json()}")
        return response.json()

    @staticmethod
    def _existing_list(
        project_name: str,
        list_label: str,
        list_type: str | None = None,
    ) -> dict | None:
        all_lists = ayon_api.get_entity_lists(
            project_name=project_name,
        )
        # iterate via all lists and check if the label matches
        for list_data in all_lists:
            if list_type and list_data["entityListType"] != list_type:
                continue
            if list_data["label"] != list_label:
                continue
            return list_data
        return None
