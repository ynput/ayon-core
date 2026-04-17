"""Plugin to create hero version from selected context."""
from __future__ import annotations
import os
import collections
from concurrent.futures import ThreadPoolExecutor
import copy
import errno
import shutil
from typing import Any, Optional

import clique
import ayon_api
from ayon_api.utils import create_entity_id
from ayon_api.operations import OperationsSession, new_version_entity

from ayon_core.lib import create_hard_link, source_hash, StringTemplate
from ayon_core.lib.file_transaction import wait_for_future_errors, copyfile
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.publish import get_publish_template_name
from ayon_core.pipeline.template_data import get_template_data

from ayon_core.pipeline.actions import (
    LoaderActionPlugin,
    LoaderActionItem,
    LoaderActionSelection,
    LoaderActionResult,
)


class HeroCreationError(Exception):
    pass

def prepare_changes(old_entity: dict, new_entity: dict) -> dict:
    """Prepare changes dict for update entity operation.

    Args:
        old_entity (dict): Existing entity data from database.
        new_entity (dict): New entity data to compare against old.

    Returns:
        dict: Changes to apply to old entity to make it like new entity.

    """
    changes = {}
    for key in set(new_entity.keys()):
        if key == "attrib":
            continue
        if key in new_entity and new_entity[key] != old_entity.get(key):
            changes[key] = new_entity[key]
    attrib_changes = {}
    if "attrib" in new_entity:
        for key, value in new_entity["attrib"].items():
            if value != old_entity["attrib"].get(key):
                attrib_changes[key] = value
    if attrib_changes:
        changes["attrib"] = attrib_changes
    return changes


class CreateHeroVersion(LoaderActionPlugin):
    """Create hero version from selected context."""

    is_multiple_contexts_compatible = False
    ignored_representation_names: list[str] = []
    db_representation_context_keys = [
        "project",
        "folder",
        "hierarchy",
        "task",
        "product",
        "representation",
        "username",
        "user",
        "output"
    ]
    use_hardlinks = False

    def get_action_items(
        self, selection: LoaderActionSelection
    ) -> list[LoaderActionItem]:
        # Do not show in hosts
        if self.host_name is not None:
            return []

        versions = selection.get_selected_version_entities()
        if not versions:
            return []

        return [
            LoaderActionItem(
                label="Create Hero Version",
                order=36,
                icon={
                    "type": "awesome-font",
                    "name": "fa5.star",
                    "color": "#ffd700",
                }
            ),
        ]

    def execute_action(
        self,
        selection: LoaderActionSelection,
        data: dict[str, Any],
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        project_name = selection.project_name
        project_settings = selection.get_project_settings()
        project_entity = ayon_api.get_project(project_name)
        anatomy = selection.get_project_anatomy()
        version_entities = selection.get_selected_version_entities()

        # Prepare all necessary entities
        product_ids = set()
        task_ids = set()
        version_ids = set()
        for version in version_entities:
            product_ids.add(version["productId"])
            task_ids.add(version["taskId"])
            version_ids.add(version["id"])

        task_ids.discard(None)

        product_entities_by_id = {
            product_entity["id"]: product_entity
            for product_entity in ayon_api.get_products(
                project_name, product_ids=product_ids
            )
        }
        folder_ids = {
            product_entity["folderId"]
            for product_entity in product_entities_by_id.values()
        }
        folder_entities_by_id = {
            folder_entity["id"]: folder_entity
            for folder_entity in ayon_api.get_folders(
                project_name, folder_ids=folder_ids
            )
        }
        task_entities_by_id = {
            task_entity["id"]: task_entity
            for task_entity in ayon_api.get_tasks(
                project_name, task_ids=task_ids
            )
        }

        hero_version_ids = set()
        hero_versions_by_product_id = {
            product_id: None
            for product_id in product_ids
        }
        for hero_version_entity in ayon_api.get_hero_versions(
            project_name,
            product_ids=product_ids,
        ):
            product_id = hero_version_entity["productId"]
            hero_versions_by_product_id[product_id] = hero_version_entity
            hero_version_ids.add(hero_version_entity["id"])

        repres_by_version_id = collections.defaultdict(list)
        for repre in ayon_api.get_representations(
            project_name, version_ids=version_ids | hero_version_ids
        ):
            version_id = repre["versionId"]
            repres_by_version_id[version_id].append(repre)

        # Begin the conversion version by version
        errors = []
        for version_entity in version_entities:
            version_id = version_entity["id"]
            product_id = version_entity["productId"]
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = folder_entities_by_id[folder_id]
            task_id = version_entity["taskId"]
            task_entity = task_entities_by_id.get(task_id)

            hero_version_entity = hero_versions_by_product_id[product_id]
            hero_representations = []
            if hero_version_entity:
                hero_version_id = hero_version_entity["id"]
                hero_representations = repres_by_version_id[hero_version_id]

            template_data = get_template_data(
                project_entity=project_entity,
                folder_entity=folder_entity,
                task_entity=task_entity,
            )

            product_type = product_entity.get("productType")
            if not product_type:
                product_type = product_entity["type"]

            product_base_type = product_entity.get("productBaseType")
            if not product_base_type:
                product_base_type = product_type

            template_data["product"] = {
                "name": product_entity["name"],
                "type": product_type,
                "basetype": product_base_type,
            }
            template_data["version"] = version_entity["version"]

            src_representations = {}
            for repre in repres_by_version_id[version_id]:
                repre_template_data = copy.deepcopy(template_data)
                ext = repre.get("context", {}).get("ext")
                if ext:
                    repre_template_data["ext"] = ext

                src_representations[repre["id"]] = {
                    "representation": repre,
                    "published_files": [
                        file_info["path"]
                        for file_info in repre.get("files", [])
                    ],
                    "template_data": repre_template_data
                }

            try:
                self.create_hero_version(
                    anatomy,
                    project_settings,
                    task_entity,
                    version_entity,
                    src_representations,
                    template_data,
                    hero_version_entity,
                    hero_representations,
                )
            except HeroCreationError as exc:
                self.log.warning(
                    f"Failed to convert version to hero version: {exc}"
                )
                errors.append(str(exc))

            except Exception:
                self.log.warning(
                    "Failed to convert version to hero version.",
                    exc_info=True,
                )
                errors.append("Unexpected error")

        if not errors:
            if len(version_entities) == 1:
                message = "Hero version created successfully."
            else:
                message = (
                    f"{len(version_entities)} Hero versions"
                    " created successfully."
                )
            return LoaderActionResult(success=True, message=message)

        if len(version_entities) == 1:
            message = "Failed to create hero version"
        else:
            message = (
                f"Failed to create {len(errors)}/{len(version_entities)}"
                f" hero versions"
            )
        return LoaderActionResult(
            success=False,
            message=f"{message}:\n{chr(10).join(errors)}"
        )

    def create_hero_version(
        self,
        anatomy: Anatomy,
        project_settings: dict[str, Any],
        task_entity: dict[str, Any] | None,
        version_entity: dict[str, Any],
        src_representations: dict[str, dict],
        template_data: dict[str, Any],
        hero_version_entity: dict[str, Any],
        hero_representations: list[dict[str, Any]],
    ) -> None:
        """Create hero version from instance data.

        Args:
            anatomy (Anatomy): Anatomy object for the project.
            version_entity (dict): Source version entity.
            task_entity (dict[str, Any] | None): Source task entity
                if there was any.
            src_representations (dict[str, dict]): Representations by id.
            template_data (dict[str, Any]): Base template data of source
                context.

        Raises:
            HeroCreationError: If any required data is missing or an error occurs
                during the hero version creation process.

        """
        if not version_entity:
            raise HeroCreationError("Can't find origin version in database.")

        if version_entity["version"] == 0:
            raise HeroCreationError("Version 0 cannot have hero version.")

        if not src_representations:
            raise HeroCreationError("No published representations found.")

        for repre_id, repre_info in tuple(src_representations.items()):
            repre = repre_info["representation"]
            if repre["name"].lower() in self.ignored_representation_names:
                src_representations.pop(repre_id, None)

        if not src_representations:
            raise HeroCreationError(
                "All published representations were filtered by name."
            )

        project_name = anatomy.project_name

        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        product_base_type = template_data["product"]["basetype"]

        # TODO how to get host name?
        host_name = None

        # get the publish directory
        publish_template_key = get_publish_template_name(
            project_name,
            host_name,
            product_base_type=product_base_type,
            task_name=task_name,
            task_type=task_type,
            project_settings=project_settings,
            logger=self.log
        )
        published_template_obj = anatomy.get_template_item(
            "publish", publish_template_key, "path", default=None
        )
        if published_template_obj is None:
            raise HeroCreationError(
                "Project anatomy does not have"
                f" publish template key: {publish_template_key}"
            )

        hero_template_key = get_publish_template_name(
            project_name,
            host_name,
            product_base_type=product_base_type,
            task_name=task_name,
            task_type=task_type,
            project_settings=project_settings,
            hero=True,
        )
        hero_template = anatomy.get_template_item(
            "hero", hero_template_key, "path", default=None
        )
        if hero_template is None:
            raise HeroCreationError(
                "Project anatomy does not have"
                f" hero template key: {hero_template_key}"
            )

        self.log.info(f"Hero template: {hero_template.template}")

        hero_template_obj = anatomy.get_template_item(
            "hero", hero_template_key, "directory"
        )
        hero_publish_dir = os.path.normpath(
            hero_template_obj.format_strict(template_data)
        )

        self.log.info(f"Hero publish dir: {hero_publish_dir}")

        all_repre_file_paths = []
        for repre_info in src_representations.values():
            for file_path in repre_info["published_files"]:
                file_path = os.path.normpath(file_path)
                if file_path not in all_repre_file_paths:
                    all_repre_file_paths.append(file_path)

        inactive_old_repres_by_name = {}
        old_repres_by_name = {}
        for repre in hero_representations:
            low_name = repre["name"].lower()
            if repre["active"]:
                old_repres_by_name[low_name] = repre
            else:
                inactive_old_repres_by_name[low_name] = repre

        op_session = OperationsSession()
        hero_version_id = None
        if hero_version_entity:
            hero_version_id = hero_version_entity["id"]

        new_hero_version = new_version_entity(
            -version_entity["version"],
            version_entity["productId"],
            task_id=version_entity["taskId"],
            data=copy.deepcopy(version_entity["data"]),
            attribs=copy.deepcopy(version_entity["attrib"]),
            entity_id=hero_version_id,
        )
        if hero_version_entity:
            update_data = prepare_changes(
                hero_version_entity,
                new_hero_version
            )
            op_session.update_entity(
                project_name,
                "version",
                hero_version_id,
                update_data
            )
        else:
            op_session.create_entity(
                project_name,
                "version",
                new_hero_version
            )

        old_repres_to_replace = {}
        for repre_info in src_representations.values():
            repre = repre_info["representation"]
            repre_name_low = repre["name"].lower()
            if repre_name_low in old_repres_by_name:
                old_repres_to_replace[repre_name_low] = (
                    old_repres_by_name.pop(repre_name_low)
                )

        old_repres_to_delete = old_repres_by_name or {}
        backup_hero_publish_dir = None
        if os.path.exists(hero_publish_dir):
            base_backup_dir = f"{hero_publish_dir}.BACKUP"
            max_idx = 10
            # Find the first available backup directory name
            for idx in range(max_idx + 1):
                candidate_backup_dir = base_backup_dir
                if idx > 0:
                    candidate_backup_dir = f"{base_backup_dir}{idx}"
                if not os.path.exists(candidate_backup_dir):
                    backup_hero_publish_dir = candidate_backup_dir
                    break
            else:
                raise HeroCreationError(
                    f"Backup folders are fully occupied to max index {max_idx}"
                )

            try:
                os.rename(hero_publish_dir, backup_hero_publish_dir)
            except PermissionError as e:
                raise HeroCreationError(
                    "Could not create hero version because it is "
                    "not possible to replace current hero files."
                ) from e

        try:
            src_to_dst_file_paths = []
            repre_integrate_data = []
            anatomy_root = {"root": anatomy.roots}
            for repre_info in src_representations.values():
                published_files = repre_info["published_files"]
                if len(published_files) == 0:
                    continue
                template_data = copy.deepcopy(repre_info["template_data"])
                template_data.pop("version", None)
                template_filled = hero_template.format_strict(
                    template_data
                )
                repre_context = template_filled.used_values
                for key in self.db_representation_context_keys:
                    value = template_data.get(key)
                    if value is not None:
                        repre_context[key] = value
                repre_entity = copy.deepcopy(repre_info["representation"])
                repre_entity.pop("id", None)
                repre_entity["versionId"] = new_hero_version["id"]
                repre_entity["context"] = repre_context
                repre_entity["attrib"] = {
                    "path": str(template_filled),
                    "template": hero_template.template
                }
                rootless_dst_paths = []

                if len(published_files) == 1:
                    rootless_dst_paths.append(str(template_filled.rootless))
                    mapped_published_file = StringTemplate(
                        published_files[0]
                    ).format_strict(anatomy_root)
                    src_to_dst_file_paths.append(
                        (mapped_published_file, template_filled)
                    )
                    self.log.info(
                        f"Single published file: {mapped_published_file} -> "
                        f"{template_filled}"
                    )
                else:
                    collections, remainders = clique.assemble(published_files)
                    if remainders or not collections or len(collections) > 1:
                        raise HeroCreationError(
                            "Integrity error. Files of published "
                            "representation is combination of frame "
                            "collections and single files."
                        )

                    src_col = collections[0]
                    frame_splitter = "_-_FRAME_SPLIT_-_"
                    template_data["frame"] = frame_splitter
                    _template_filled = hero_template.format_strict(
                        template_data
                    ).rootless
                    head, tail = _template_filled.split(frame_splitter)
                    padding = anatomy.templates_obj.frame_padding
                    dst_col = clique.Collection(
                        head=head, padding=padding, tail=tail
                    )
                    dst_col.indexes.clear()
                    dst_col.indexes.update(src_col.indexes)
                    for src_file, dst_file in zip(src_col, dst_col):
                        src_file = StringTemplate(src_file).format_strict(
                            anatomy_root
                        )
                        src_to_dst_file_paths.append(
                            (src_file, dst_file.format(root=anatomy.roots))
                        )
                        rootless_dst_paths.append(dst_file)
                        self.log.info(
                            f"Collection published file: {src_file} "
                            f"-> {dst_file}"
                        )
                repre_integrate_data.append(
                    (repre_entity, rootless_dst_paths)
                )

            # Copy files
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(
                        self.copy_file,
                        src_path,
                        dst_path
                    )
                    for src_path, dst_path in src_to_dst_file_paths
                ]
                wait_for_future_errors(executor, futures)

            # Update/create representations
            for repre_entity, dst_paths in repre_integrate_data:
                repre_files = self.get_files_info(dst_paths, anatomy)
                repre_entity["files"] = repre_files
                repre_name_low = repre_entity["name"].lower()
                if repre_name_low in old_repres_to_replace:
                    old_repre = old_repres_to_replace.pop(repre_name_low)
                    repre_entity["id"] = old_repre["id"]
                    update_data = prepare_changes(old_repre, repre_entity)
                    op_session.update_entity(
                        project_name,
                        "representation",
                        old_repre["id"],
                        update_data
                    )

                elif repre_name_low in inactive_old_repres_by_name:
                    inactive_repre = inactive_old_repres_by_name.pop(
                        repre_name_low
                    )
                    repre_entity["id"] = inactive_repre["id"]
                    update_data = prepare_changes(inactive_repre, repre_entity)
                    op_session.update_entity(
                        project_name,
                        "representation",
                        inactive_repre["id"],
                        update_data
                    )

                else:
                    op_session.create_entity(
                        project_name,
                        "representation",
                        repre_entity
                    )

            for repre in old_repres_to_delete.values():
                op_session.update_entity(
                    project_name,
                    "representation",
                    repre["id"],
                    {"active": False}
                )

            op_session.commit()

            if backup_hero_publish_dir is not None and os.path.exists(
                backup_hero_publish_dir
            ):
                shutil.rmtree(backup_hero_publish_dir)

        except Exception:
            if (
                backup_hero_publish_dir is not None
                and os.path.exists(backup_hero_publish_dir)
            ):
                if os.path.exists(hero_publish_dir):
                    shutil.rmtree(hero_publish_dir)
                os.rename(backup_hero_publish_dir, hero_publish_dir)
            raise

    def get_files_info(
        self,
        filepaths: list[str],
        anatomy: Anatomy,
    ) -> list[dict]:
        """Get list of file info dictionaries for given file paths.

        Args:
            filepaths (list[str]): List of absolute file paths.
            anatomy (Anatomy): Anatomy object for the project.

        Returns:
            list[dict]: List of file info dictionaries.

        """
        file_infos = [
            self.prepare_file_info(filepath, anatomy)
            for filepath in filepaths
        ]
        return file_infos

    def prepare_file_info(self, path: str, anatomy: Anatomy) -> dict:
        """Prepare file info dictionary for given path.

        Args:
            path (str): Absolute file path.
            anatomy (Anatomy): Anatomy object for the project.

        Returns:
            dict: File info dictionary with keys:
                - id (str): Unique identifier for the file.
                - name (str): Base name of the file.
                - path (str): Rootless file path.
                - size (int): Size of the file in bytes.
                - hash (str): Hash of the file content.
                - hash_type (str): Type of the hash used.

        """
        realpath = path.format(root=anatomy.roots)
        return {
            "id": create_entity_id(),
            "name": os.path.basename(path),
            "path": path,
            "size": os.path.getsize(realpath),
            "hash": source_hash(realpath),
            "hash_type": "op3",
        }

    def copy_file(self, src_path: str, dst_path: str) -> None:
        """Copy file from src to dst with creating directories.

        Args:
            src_path (str): Source file path.
            dst_path (str): Destination file path.

        Raises:
            OSError: If copying or linking fails.

        """
        dirname = os.path.dirname(dst_path)
        os.makedirs(dirname, exist_ok=True)

        if self.use_hardlinks:
            try:
                create_hard_link(src_path, dst_path)
                return
            except OSError as exc:
                if exc.errno not in [errno.EXDEV, errno.EINVAL]:
                    raise
        copyfile(src_path, dst_path)

    @staticmethod
    def current_hero_ents(
        project_name: str,
        version_entity: dict[str, Any]
    ) -> tuple[Any, list[dict[str, Any]]]:
        hero_version = ayon_api.get_hero_version_by_product_id(
            project_name, version_entity["productId"]
        )
        hero_repres = []
        if hero_version:
            hero_repres = list(ayon_api.get_representations(
                project_name, version_ids={hero_version["id"]}
            ))
        return hero_version, hero_repres
