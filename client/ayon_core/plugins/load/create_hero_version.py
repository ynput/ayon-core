
import os
import copy
import shutil
import errno
import itertools
from concurrent.futures import ThreadPoolExecutor

from speedcopy import copyfile
import clique
import ayon_api
from ayon_api.operations import OperationsSession, new_version_entity
from ayon_api.utils import create_entity_id
from qtpy import QtWidgets, QtCore
from ayon_core import style
from ayon_core.pipeline import load, Anatomy
from ayon_core.lib import create_hard_link, source_hash, StringTemplate
from ayon_core.lib.file_transaction import wait_for_future_errors
from ayon_core.pipeline.publish import get_publish_template_name
from ayon_core.pipeline.template_data import get_template_data


def prepare_changes(old_entity, new_entity):
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

    ignored_representation_names = []
    db_representation_context_keys = [
        "project", "folder", "asset", "hierarchy", "task", "product",
        "subset", "family", "representation", "username", "user", "output"
    ]
    use_hardlinks = False

    def message(self, text):
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(text)
        msgBox.setStyleSheet(style.load_stylesheet())
        msgBox.setWindowFlags(
            msgBox.windowFlags() | QtCore.Qt.FramelessWindowHint
        )
        msgBox.exec_()

    def load(self, context, name=None, namespace=None, options=None) -> None:
        """Load hero version from context (dict as in context.py)."""
        success = True
        errors = []

        # Extract project, product, version, folder from context
        project = context.get("project")
        product = context.get("product")
        version = context.get("version")
        folder = context.get("folder")
        task_entity = ayon_api.get_task_by_id(
            task_id=version.get("taskId"), project_name=project["name"])

        anatomy = Anatomy(project["name"])

        version_id = version["id"]
        project_name = project["name"]
        repres = list(
            ayon_api.get_representations(
                project_name, version_ids={version_id}
            )
        )
        anatomy_data = get_template_data(
                project_entity=project,
                folder_entity=folder,
                task_entity=task_entity,
            )
        anatomy_data["product"] = {
            "name": product["name"],
            "type": product["productType"],
        }
        published_representations = {}
        for repre in repres:
            repre_anatomy = copy.deepcopy(anatomy_data)
            if "ext" not in repre_anatomy:
                repre_anatomy["ext"] = repre.get("context", {}).get("ext", "")
            published_representations[repre["id"]] = {
                "representation": repre,
                "published_files": [f["path"] for f in repre.get("files", [])],
                "anatomy_data": repre_anatomy
            }

        instance_data = {
            "productName": product["name"],
            "productType": product["productType"],
            "anatomyData": anatomy_data,
            "publishDir": "",  # TODO: Set to actual publish directory
            "published_representations": published_representations,
            "versionEntity": version,
        }

        try:
            self.create_hero_version(instance_data, anatomy, context)
        except Exception as exc:
            success = False
            errors.append(str(exc))
        if success:
            self.message("Hero version created successfully.")
        else:
            self.message(
                f"Failed to create hero version:\n{chr(10).join(errors)}")

    def create_hero_version(self, instance_data, anatomy, context):
        """Create hero version from instance data."""
        published_repres = instance_data.get("published_representations")
        if not published_repres:
            raise RuntimeError("No published representations found.")

        project_name = anatomy.project_name
        template_key = get_publish_template_name(
            project_name,
            context.get("hostName"),
            instance_data.get("productType"),
            instance_data.get("anatomyData", {}).get("task", {}).get("name"),
            instance_data.get("anatomyData", {}).get("task", {}).get("type"),
            project_settings=context.get("project_settings", {}),
            hero=True,
            logger=None
        )
        hero_template = anatomy.get_template_item(
            "hero", template_key, "path", default=None
        )
        if hero_template is None:
            raise RuntimeError("Project anatomy does not have hero "
                               f"template key: {template_key}")

        print(f"Hero template: {hero_template.template}")

        hero_publish_dir = self.get_publish_dir(
            instance_data, anatomy, template_key
        )

        print(f"Hero publish dir: {hero_publish_dir}")

        src_version_entity = instance_data.get("versionEntity")
        filtered_repre_ids = []
        for repre_id, repre_info in published_repres.items():
            repre = repre_info["representation"]
            if repre["name"].lower() in self.ignored_representation_names:
                filtered_repre_ids.append(repre_id)
        for repre_id in filtered_repre_ids:
            published_repres.pop(repre_id, None)
        if not published_repres:
            raise RuntimeError(
                "All published representations were filtered by name."
            )

        if src_version_entity is None:
            src_version_entity = self.version_from_representations(
                project_name, published_repres)
        if not src_version_entity:
            raise RuntimeError("Can't find origin version in database.")
        if src_version_entity["version"] == 0:
            raise RuntimeError("Version 0 cannot have hero version.")

        all_copied_files = []
        transfers = instance_data.get("transfers", list())
        for _src, dst in transfers:
            dst = os.path.normpath(dst)
            if dst not in all_copied_files:
                all_copied_files.append(dst)
        hardlinks = instance_data.get("hardlinks", list())
        for _src, dst in hardlinks:
            dst = os.path.normpath(dst)
            if dst not in all_copied_files:
                all_copied_files.append(dst)

        all_repre_file_paths = []
        for repre_info in published_repres.values():
            published_files = repre_info.get("published_files") or []
            for file_path in published_files:
                file_path = os.path.normpath(file_path)
                if file_path not in all_repre_file_paths:
                    all_repre_file_paths.append(file_path)

        instance_publish_dir = os.path.normpath(instance_data["publishDir"])
        other_file_paths_mapping = []
        for file_path in all_copied_files:
            if not file_path.startswith(instance_publish_dir):
                continue
            if file_path in all_repre_file_paths:
                continue
            dst_filepath = file_path.replace(
                instance_publish_dir, hero_publish_dir
            )
            other_file_paths_mapping.append((file_path, dst_filepath))

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
            task_id=src_version_entity.get("taskId"),
            data=copy.deepcopy(src_version_entity["data"]),
            attribs=copy.deepcopy(src_version_entity["attrib"]),
            entity_id=entity_id,
        )
        if old_version:
            update_data = prepare_changes(old_version, new_hero_version)
            op_session.update_entity(
                project_name, "version", old_version["id"], update_data
            )
        else:
            op_session.create_entity(project_name, "version", new_hero_version)

        # Store hero entity to instance_data
        instance_data["heroVersionEntity"] = new_hero_version

        old_repres_to_replace = {}
        old_repres_to_delete = {}
        for repre_info in published_repres.values():
            repre = repre_info["representation"]
            repre_name_low = repre["name"].lower()
            if repre_name_low in old_repres_by_name:
                old_repres_to_replace[repre_name_low] = (
                    old_repres_by_name.pop(repre_name_low)
                )
        if old_repres_by_name:
            old_repres_to_delete = old_repres_by_name

        backup_hero_publish_dir = None
        if os.path.exists(hero_publish_dir):
            backup_hero_publish_dir = hero_publish_dir + ".BACKUP"
            max_idx = 10
            idx = 0
            _backup_hero_publish_dir = backup_hero_publish_dir
            while os.path.exists(_backup_hero_publish_dir):
                try:
                    shutil.rmtree(_backup_hero_publish_dir)
                    backup_hero_publish_dir = _backup_hero_publish_dir
                    break
                except Exception as exc:
                    _backup_hero_publish_dir = (
                        backup_hero_publish_dir + str(idx)
                    )
                    if not os.path.exists(_backup_hero_publish_dir):
                        backup_hero_publish_dir = _backup_hero_publish_dir
                        break
                    if idx > max_idx:
                        raise AssertionError(
                            "Backup folders are fully occupied to max index "
                            f"{max_idx}"
                        ) from exc
                    idx += 1
            try:
                os.rename(hero_publish_dir, backup_hero_publish_dir)
            except PermissionError:
                raise AssertionError(
                    "Could not create hero version because it is "
                    "not possible to replace current hero files.")

        try:
            src_to_dst_file_paths = []
            repre_integrate_data = []
            path_template_obj = anatomy.get_template_item(
                "hero", template_key, "path")
            anatomy_root = {"root": anatomy.roots}
            for repre_info in published_repres.values():
                published_files = repre_info["published_files"]
                if len(published_files) == 0:
                    continue
                anatomy_data = copy.deepcopy(repre_info["anatomy_data"])
                anatomy_data.pop("version", None)
                template_filled = path_template_obj.format_strict(anatomy_data)
                repre_context = template_filled.used_values
                for key in self.db_representation_context_keys:
                    value = anatomy_data.get(key)
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
                dst_paths = []

                if len(published_files) == 1:
                    dst_paths.append(str(template_filled))
                    mapped_published_file = StringTemplate(
                        published_files[0]).format_strict(
                        anatomy_root
                    )
                    src_to_dst_file_paths.append(
                        (mapped_published_file, template_filled)
                    )
                    print(
                        f"Single published file: {mapped_published_file} -> "
                        f"{template_filled}"
                    )
                else:
                    collections, remainders = clique.assemble(published_files)
                    if remainders or not collections or len(collections) > 1:
                        raise Exception(
                            (
                                "Integrity error. Files of published "
                                "representation is combination of frame "
                                "collections and single files."
                            )
                        )
                    src_col = collections[0]
                    frame_splitter = "_-_FRAME_SPLIT_-_"
                    anatomy_data["frame"] = frame_splitter
                    _template_filled = path_template_obj.format_strict(
                        anatomy_data
                    )
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
                        src_to_dst_file_paths.append((src_file, dst_file))
                        dst_paths.append(dst_file)
                        print(
                            f"Collection published file: {src_file} "
                            f"-> {dst_file}"
                        )
                repre_integrate_data.append((repre_entity, dst_paths))

            # Copy files
            with ThreadPoolExecutor(max_workers=8) as executor:
                futures = [
                    executor.submit(self.copy_file, src_path, dst_path)
                    for src_path, dst_path in itertools.chain(
                        src_to_dst_file_paths, other_file_paths_mapping)
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
            if backup_hero_publish_dir is not None and os.path.exists(
                backup_hero_publish_dir):
                if os.path.exists(hero_publish_dir):
                    shutil.rmtree(hero_publish_dir)
                os.rename(backup_hero_publish_dir, hero_publish_dir)
            raise

    def get_files_info(self, filepaths, anatomy):
        file_infos = []
        for filepath in filepaths:
            file_info = self.prepare_file_info(filepath, anatomy)
            file_infos.append(file_info)
        return file_infos

    def prepare_file_info(self, path, anatomy):
        return {
            "id": create_entity_id(),
            "name": os.path.basename(path),
            "path": self.get_rootless_path(anatomy, path),
            "size": os.path.getsize(path),
            "hash": source_hash(path),
            "hash_type": "op3",
        }

    def get_publish_dir(self, instance_data, anatomy, template_key):
        template_data = copy.deepcopy(instance_data.get("anatomyData", {}))
        if "originalBasename" in instance_data:
            template_data["originalBasename"] = (
                instance_data["originalBasename"]
            )
        template_obj = anatomy.get_template_item(
            "hero", template_key, "directory"
        )
        return os.path.normpath(template_obj.format_strict(template_data))

    def get_rootless_path(self, anatomy, path):
        success, rootless_path = anatomy.find_root_template_from_path(path)
        if success:
            path = rootless_path
        return path

    def copy_file(self, src_path, dst_path):
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

    def version_from_representations(self, project_name, repres):
        for repre_info in repres.values():
            version = ayon_api.get_version_by_id(
                project_name, repre_info["representation"]["versionId"]
            )
            if version:
                return version

    def current_hero_ents(self, project_name, version):
        hero_version = ayon_api.get_hero_version_by_product_id(
            project_name, version["productId"]
        )
        if not hero_version:
            return (None, [])
        hero_repres = list(
            ayon_api.get_representations(
                project_name, version_ids={hero_version["id"]}
            )
        )
        return (hero_version, hero_repres)
