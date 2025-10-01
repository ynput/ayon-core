from __future__ import annotations

import os
import collections
import json
import shutil
from typing import Optional, Any

from ayon_api.operations import OperationsSession

from ayon_core.lib import (
    format_file_size,
    AbstractAttrDef,
    NumberDef,
    BoolDef,
    TextDef,
    UILabelDef,
)
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.actions import (
    LoaderSelectedType,
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
    LoaderActionForm,
)


class DeleteOldVersions(LoaderActionPlugin):
    """Deletes specific number of old version"""

    is_multiple_contexts_compatible = True
    sequence_splitter = "__sequence_splitter__"

    requires_confirmation = True

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        # Do not show in hosts
        if self.host_name is not None:
            return []

        versions = None
        if selection.selected_type == LoaderSelectedType.version:
            versions = selection.entities.get_versions(
                selection.selected_ids
            )

        if not versions:
            return []

        product_ids = {
            version["productId"]
            for version in versions
        }

        return [
            LoaderActionItem(
                label="Delete Versions",
                order=35,
                data={
                    "product_ids": list(product_ids),
                    "action": "delete-versions",
                },
                icon={
                    "type": "material-symbols",
                    "name": "delete",
                    "color": "#d8d8d8",
                }
            ),
            LoaderActionItem(
                label="Calculate Versions size",
                order=30,
                data={
                    "product_ids": list(product_ids),
                    "action": "calculate-versions-size",
                },
                icon={
                    "type": "material-symbols",
                    "name": "auto_delete",
                    "color": "#d8d8d8",
                }
            )
        ]

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        step = form_values.get("step")
        action = data["action"]
        versions_to_keep = form_values.get("versions_to_keep")
        remove_publish_folder = form_values.get("remove_publish_folder")
        if step is None:
            return self._first_step(
                action,
                versions_to_keep,
                remove_publish_folder,
            )

        if versions_to_keep is None:
            versions_to_keep = 2
        if remove_publish_folder is None:
            remove_publish_folder = False

        product_ids = data["product_ids"]
        if step == "prepare-data":
            return self._prepare_data_step(
                action,
                versions_to_keep,
                remove_publish_folder,
                product_ids,
                selection,
            )

        if step == "delete-versions":
            return self._delete_versions_step(
                selection.project_name, form_values
            )
        return None

    def _first_step(
        self,
        action: str,
        versions_to_keep: Optional[int],
        remove_publish_folder: Optional[bool],
    ) -> LoaderActionResult:
        fields: list[AbstractAttrDef] = [
            TextDef(
                "step",
                visible=False,
            ),
            NumberDef(
                "versions_to_keep",
                label="Versions to keep",
                minimum=0,
                default=2,
            ),
        ]
        if action == "delete-versions":
            fields.append(
                BoolDef(
                    "remove_publish_folder",
                    label="Remove publish folder",
                    default=False,
                )
            )

        form_values = {
            key: value
            for key, value in (
                ("remove_publish_folder", remove_publish_folder),
                ("versions_to_keep", versions_to_keep),
            )
            if value is not None
        }
        form_values["step"] = "prepare-data"
        return LoaderActionResult(
            form=LoaderActionForm(
                title="Delete Old Versions",
                fields=fields,
            ),
            form_values=form_values
        )

    def _prepare_data_step(
        self,
        action: str,
        versions_to_keep: int,
        remove_publish_folder: bool,
        entity_ids: set[str],
        selection: LoaderActionSelection,
    ):
        versions_by_product_id = collections.defaultdict(list)
        for version in selection.entities.get_products_versions(entity_ids):
            # Keep hero version
            if versions_to_keep != 0 and version["version"] < 0:
                continue
            versions_by_product_id[version["productId"]].append(version)

        versions_to_delete = []
        for product_id, versions in versions_by_product_id.items():
            if versions_to_keep == 0:
                versions_to_delete.extend(versions)
                continue

            if len(versions) <= versions_to_keep:
                continue

            versions.sort(key=lambda v: v["version"])
            for _ in range(versions_to_keep):
                if not versions:
                    break
                versions.pop(-1)
            versions_to_delete.extend(versions)

        self.log.debug(
            f"Collected versions to delete ({len(versions_to_delete)})"
        )

        version_ids = {
            version["id"]
            for version in versions_to_delete
        }
        if not version_ids:
            return LoaderActionResult(
                message="Skipping. Nothing to delete.",
                success=False,
            )

        project = selection.entities.get_project()
        anatomy = Anatomy(project["name"], project_entity=project)

        repres = selection.entities.get_versions_representations(version_ids)

        self.log.debug(
            f"Collected representations to remove ({len(repres)})"
        )

        filepaths_by_repre_id = {}
        repre_ids_by_version_id = {
            version_id: []
            for version_id in version_ids
        }
        for repre in repres:
            repre_ids_by_version_id[repre["versionId"]].append(repre["id"])
            filepaths_by_repre_id[repre["id"]] = [
                anatomy.fill_root(repre_file["path"])
                for repre_file in repre["files"]
            ]

        size = 0
        for filepaths in filepaths_by_repre_id.values():
            for filepath in filepaths:
                if os.path.exists(filepath):
                    size += os.path.getsize(filepath)

        if action == "calculate-versions-size":
            return LoaderActionResult(
                message="Calculated size",
                success=True,
                form=LoaderActionForm(
                    title="Calculated versions size",
                    fields=[
                        UILabelDef(
                            f"Total size of files: {format_file_size(size)}"
                        ),
                    ],
                    submit_label=None,
                    cancel_label="Close",
                ),
            )

        form, form_values = self._get_delete_form(
            size,
            remove_publish_folder,
            list(version_ids),
            repre_ids_by_version_id,
            filepaths_by_repre_id,
        )
        return LoaderActionResult(
            form=form,
            form_values=form_values
        )

    def _delete_versions_step(
        self, project_name: str, form_values: dict[str, Any]
    ) -> LoaderActionResult:
        delete_data = json.loads(form_values["delete_data"])
        remove_publish_folder = form_values["remove_publish_folder"]
        if form_values["delete_value"].lower() != "delete":
            size = delete_data["size"]
            form, form_values = self._get_delete_form(
                size,
                remove_publish_folder,
                delete_data["version_ids"],
                delete_data["repre_ids_by_version_id"],
                delete_data["filepaths_by_repre_id"],
                True,
            )
            return LoaderActionResult(
                form=form,
                form_values=form_values,
            )

        version_ids = delete_data["version_ids"]
        repre_ids_by_version_id = delete_data["repre_ids_by_version_id"]
        filepaths_by_repre_id = delete_data["filepaths_by_repre_id"]
        op_session = OperationsSession()
        total_versions = len(version_ids)
        try:
            for version_idx, version_id in enumerate(version_ids):
                self.log.info(
                    f"Progressing version {version_idx + 1}/{total_versions}"
                )
                for repre_id in repre_ids_by_version_id[version_id]:
                    for filepath in filepaths_by_repre_id[repre_id]:
                        publish_folder = os.path.dirname(filepath)
                        if remove_publish_folder:
                            if os.path.exists(publish_folder):
                                shutil.rmtree(
                                    publish_folder, ignore_errors=True
                                )
                            continue

                        if os.path.exists(filepath):
                            os.remove(filepath)

                    op_session.delete_entity(
                        project_name, "representation", repre_id
                    )
                op_session.delete_entity(
                    project_name, "version", version_id
                )
            self.log.info("All done")

        except Exception:
            self.log.error("Failed to delete versions.", exc_info=True)
            return LoaderActionResult(
                message="Failed to delete versions.",
                success=False,
            )

        finally:
            op_session.commit()

        return LoaderActionResult(
            message="Deleted versions",
            success=True,
        )

    def _get_delete_form(
        self,
        size: int,
        remove_publish_folder: bool,
        version_ids: list[str],
        repre_ids_by_version_id: dict[str, list[str]],
        filepaths_by_repre_id: dict[str, list[str]],
        repeated: bool = False,
    ) -> tuple[LoaderActionForm, dict[str, Any]]:
        versions_len = len(repre_ids_by_version_id)
        fields = [
            UILabelDef(
                f"Going to delete {versions_len} versions<br/>"
                f"- total size of files: {format_file_size(size)}<br/>"
            ),
            UILabelDef("Are you sure you want to continue?"),
            TextDef(
                "delete_value",
                placeholder="Type 'delete' to confirm...",
            ),
        ]
        if repeated:
            fields.append(UILabelDef(
                "*Please fill in '**delete**' to confirm deletion.*"
            ))
        fields.extend([
            TextDef(
                "delete_data",
                visible=False,
            ),
            TextDef(
                "step",
                visible=False,
            ),
            BoolDef(
                "remove_publish_folder",
                label="Remove publish folder",
                default=False,
                visible=False,
            )
        ])

        form = LoaderActionForm(
            title="Delete versions",
            submit_label="Delete",
            cancel_label="Close",
            fields=fields,
        )
        form_values = {
            "delete_data": json.dumps({
                "size": size,
                "version_ids": version_ids,
                "repre_ids_by_version_id": repre_ids_by_version_id,
                "filepaths_by_repre_id": filepaths_by_repre_id,
            }),
            "step": "delete-versions",
            "remove_publish_folder": remove_publish_folder,
        }
        return form, form_values
