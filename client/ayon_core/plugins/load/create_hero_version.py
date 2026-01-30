"""Plugin to create hero version from selected context."""
from __future__ import annotations
import os
import copy
import shutil
import errno
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Optional, Union

from speedcopy import copyfile
import clique
import ayon_api
from ayon_api.operations import OperationsSession, new_version_entity
from ayon_api.utils import create_entity_id
from qtpy import QtWidgets, QtCore

from ayon_core import style
from ayon_core.pipeline import load, Anatomy
from ayon_core.settings import get_project_settings
from ayon_core.lib import create_hard_link, source_hash, StringTemplate
from ayon_core.lib.file_transaction import wait_for_future_errors
from ayon_core.pipeline.publish import get_publish_template_name
from ayon_core.pipeline.template_data import get_template_data


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


class CreateHeroVersion(load.ProductLoaderPlugin):
    """Create hero version from selected context."""

    is_multiple_contexts_compatible = False
    representations = {"*"}
    product_types = {"*"}
    label = "Create Hero Version"
    order = 36
    icon = "star"
    color = "#ffd700"

    ignored_representation_names: list[str] = []
    db_representation_context_keys = [
        "project", "folder", "hierarchy", "task", "product",
        "representation", "username", "user", "output"
    ]
    use_hardlinks = False

    @staticmethod
    def message(text: str) -> None:
        """Show message box with text."""
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(text)
        msgBox.setStyleSheet(style.load_stylesheet())
        msgBox.setWindowFlags(
            msgBox.windowFlags() | QtCore.Qt.WindowType.FramelessWindowHint
            | QtCore.Qt.WindowType.WindowStaysOnTopHint
        )
        msgBox.exec_()

    def load(self, context, name=None, namespace=None, options=None) -> None:
        """Load hero version from context (dict as in context.py)."""
        success = True
        errors = []

        # Extract project, product, version, folder from context
        project_entity = context["project"]
        project_name = project_entity["name"]
        folder_entity = context["folder"]
        product_entity = context["product"]
        version_entity = context["version"]

        task_id = version_entity["taskId"]
        task_entity = None
        if task_id:
            task_entity = ayon_api.get_task_by_id(project_name, task_id)

        anatomy = Anatomy(project_name, project_entity=project_entity)

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
        for repre in ayon_api.get_representations(
            project_name, version_ids={version_entity["id"]}
        ):
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
                task_entity,
                version_entity,
                src_representations,
                template_data,
            )
        except Exception as exc:
            success = False
            errors.append(str(exc))
        if success:
            self.message("Hero version created successfully.")
        else:
            self.message(
                f"Failed to create hero version:\n{chr(10).join(errors)}")

    def create_hero_version(
        self,
        anatomy: Anatomy,
        src_task_entity: Union[dict[str, Any], None],
        src_version_entity: dict[str, Any],
        src_representations: dict[str, dict],
        template_data: dict[str, Any],
    ) -> None:
        """Create hero version from instance data.

        Args:
            anatomy (Anatomy): Anatomy object for the project.
            src_version_entity (dict): Source version entity.
            src_task_entity (Union[dict[str, Any], None]): Source task entity
                if there was any.
            src_representations (dict[str, dict]): Representations by id.
            template_data (dict[str, Any]): Base template data of source
                context.

        Raises:
            RuntimeError: If any required data is missing or an error occurs
                during the hero version creation process.

        """
        if not src_representations:
            raise RuntimeError("No published representations found.")

        for repre_id, repre_info in tuple(src_representations.items()):
            repre = repre_info["representation"]
            if repre["name"].lower() in self.ignored_representation_names:
                src_representations.pop(repre_id, None)

        if not src_representations:
            raise RuntimeError(
                "All published representations were filtered by name."
            )

        project_name = anatomy.project_name
        if src_version_entity is None:
            src_version_entity = self.version_from_representations(
                project_name, src_representations
            )

        if not src_version_entity:
            raise RuntimeError("Can't find origin version in database.")

        if src_version_entity["version"] == 0:
            raise RuntimeError("Version 0 cannot have hero version.")

        task_name = task_type = None
        if src_task_entity:
            task_name = src_task_entity["name"]
            task_type = src_task_entity["taskType"]

        product_base_type = template_data["product"]["basetype"]

        # TODO how to get host name?
        host_name = None

        project_settings = get_project_settings(project_name)

        # get the publish directory
        publish_template_key = get_publish_template_name(
            project_name,
            host_name,
            product_base_type=product_base_type,
            product_type=product_base_type,
            task_name=task_name,
            task_type=task_type,
            project_settings=project_settings,
            logger=self.log
        )
        published_template_obj = anatomy.get_template_item(
            "publish", publish_template_key, "path", default=None
        )
        if published_template_obj is None:
            raise RuntimeError(
                "Project anatomy does not have"
                f" publish template key: {publish_template_key}"
            )

        hero_template_key = get_publish_template_name(
            project_name,
            host_name,
            product_base_type=product_base_type,
            product_type=product_base_type,
            task_name=task_name,
            task_type=task_type,
            project_settings=project_settings,
            hero=True,
        )
        hero_template = anatomy.get_template_item(
            "hero", hero_template_key, "path", default=None
        )
        if hero_template is None:
            raise RuntimeError(
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

        old_version, old_repres = self.current_hero_ents(
            project_name, src_version_entity
        )
        inactive_old_repres_by_name = {}
        old_repres_by_name = {}
        for repre in old_repres:
            low_name = repre["name"].lower()
            if repre["active"]:
                old_repres_by_name[low_name] = repre
            else:
                inactive_old_repres_by_name[low_name] = repre

        op_session = OperationsSession()
        entity_id = old_version["id"] if old_version else None
        new_hero_version = new_version_entity(
            -src_version_entity["version"],
            src_version_entity["productId"],
            task_id=src_version_entity["taskId"],
            data=copy.deepcopy(src_version_entity["data"]),
            attribs=copy.deepcopy(src_version_entity["attrib"]),
            entity_id=entity_id,
        )
        if old_version:
            update_data = prepare_changes(
                old_version,
                new_hero_version
            )
            op_session.update_entity(
                project_name,
                "version",
                old_version["id"],
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
                raise AssertionError(
                    f"Backup folders are fully occupied to max index {max_idx}"
                )

            try:
                os.rename(hero_publish_dir, backup_hero_publish_dir)
            except PermissionError as e:
                raise AssertionError(
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
                        raise RuntimeError(
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
        try:
            os.makedirs(dirname)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
        if self.use_hardlinks:
            try:
                create_hard_link(src_path, dst_path)
                return
            except OSError as exc:
                if exc.errno not in [errno.EXDEV, errno.EINVAL]:
                    raise
        copyfile(src_path, dst_path)

    @staticmethod
    def version_from_representations(
        project_name: str,
        repres: dict
    ) -> Optional[dict[str, Any]]:
        """Find version from representations.

        Args:
            project_name (str): Name of the project.
            repres (dict): Dictionary of representations info.

        Returns:
            Optional[dict]: Version entity if found, else None.

        """
        for repre_info in repres.values():
            version = ayon_api.get_version_by_id(
                project_name, repre_info["representation"]["versionId"]
            )
            if version:
                return version
        return None

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
