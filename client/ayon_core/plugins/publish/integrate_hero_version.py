import os
import copy
import errno
import shutil

import clique
import pyblish.api
import ayon_api
from ayon_api.operations import (
    OperationsSession,
    new_version_entity,
)
from ayon_api.utils import create_entity_id

from ayon_core.lib import create_hard_link, source_hash
from ayon_core.pipeline.publish import (
    get_publish_template_name,
    OptionalPyblishPluginMixin,
)


def prepare_changes(old_entity, new_entity):
    """Prepare changes for entity update.

    Args:
        old_entity: Existing entity.
        new_entity: New entity.

    Returns:
        dict[str, Any]: Changes that have new entity.

    """
    changes = {}
    for key in set(new_entity.keys()):
        if key == "attrib":
            continue

        if key in new_entity and new_entity[key] != old_entity.get(key):
            changes[key] = new_entity[key]
            continue

    attrib_changes = {}
    if "attrib" in new_entity:
        for key, value in new_entity["attrib"].items():
            if value != old_entity["attrib"].get(key):
                attrib_changes[key] = value
    if attrib_changes:
        changes["attrib"] = attrib_changes
    return changes


class IntegrateHeroVersion(
    OptionalPyblishPluginMixin, pyblish.api.InstancePlugin
):
    label = "Integrate Hero Version"
    # Must happen after IntegrateNew
    order = pyblish.api.IntegratorOrder + 0.1

    optional = True
    active = True

    # Families are modified using settings
    families = [
        "model",
        "rig",
        "setdress",
        "look",
        "pointcache",
        "animation"
    ]

    # Can specify representation names that will be ignored (lower case)
    ignored_representation_names = []
    db_representation_context_keys = [
        "project",
        "folder",
        "asset",
        "hierarchy",
        "task",
        "product",
        "subset",
        "family",
        "representation",
        "username",
        "user",
        "output"
    ]
    # QUESTION/TODO this process should happen on server if crashed due to
    # permissions error on files (files were used or user didn't have perms)
    # *but all other plugins must be sucessfully completed

    def process(self, instance):
        self.log.debug(
            "--- Integration of Hero version for product `{}` begins.".format(
                instance.data["productName"]
            )
        )
        published_repres = instance.data.get("published_representations")
        if not published_repres:
            self.log.debug(
                "*** There are no published representations on the instance."
            )
            return

        anatomy = instance.context.data["anatomy"]
        project_name = anatomy.project_name

        template_key = self._get_template_key(project_name, instance)
        hero_template = anatomy.get_template_item(
            "hero", template_key, "path", default=None
        )

        if hero_template is None:
            self.log.warning((
                "!!! Anatomy of project \"{}\" does not have set"
                " \"{}\" template key!"
            ).format(project_name, template_key))
            return

        self.log.debug("`hero` template check was successful. `{}`".format(
            hero_template
        ))

        self.integrate_instance(
            instance, project_name, template_key, hero_template
        )

    def integrate_instance(
        self, instance, project_name, template_key, hero_template
    ):
        anatomy = instance.context.data["anatomy"]
        published_repres = instance.data["published_representations"]
        hero_publish_dir = self.get_publish_dir(instance, template_key)

        src_version_entity = instance.data.get("versionEntity")
        filtered_repre_ids = []
        for repre_id, repre_info in published_repres.items():
            repre = repre_info["representation"]
            if repre["name"].lower() in self.ignored_representation_names:
                self.log.debug(
                    "Filtering representation with name: `{}`".format(
                        repre["name"].lower()
                    )
                )
                filtered_repre_ids.append(repre_id)

        for repre_id in filtered_repre_ids:
            published_repres.pop(repre_id, None)

        if not published_repres:
            self.log.debug(
                "*** All published representations were filtered by name."
            )
            return

        if src_version_entity is None:
            self.log.debug((
                "Published version entity was not sent in representation data."
                " Querying entity from database."
            ))
            src_version_entity = self.version_from_representations(
                project_name, published_repres
            )

        if not src_version_entity:
            self.log.warning((
                "!!! Can't find origin version in database."
                " Skipping hero version publish."
            ))
            return

        if src_version_entity["version"] == 0:
            self.log.debug(
                "Version 0 cannot have hero version. Skipping."
            )
            return

        all_copied_files = []
        transfers = instance.data.get("transfers", list())
        for _src, dst in transfers:
            dst = os.path.normpath(dst)
            if dst not in all_copied_files:
                all_copied_files.append(dst)

        hardlinks = instance.data.get("hardlinks", list())
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

        # TODO this is not best practice of getting resources for publish
        # WARNING due to this we must remove all files from hero publish dir
        instance_publish_dir = os.path.normpath(
            instance.data["publishDir"]
        )
        other_file_paths_mapping = []
        for file_path in all_copied_files:
            # Check if it is from publishDir
            if not file_path.startswith(instance_publish_dir):
                continue

            if file_path in all_repre_file_paths:
                continue

            dst_filepath = file_path.replace(
                instance_publish_dir, hero_publish_dir
            )
            other_file_paths_mapping.append((file_path, dst_filepath))

        # Current version
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

        entity_id = None
        if old_version:
            entity_id = old_version["id"]

        new_hero_version = new_version_entity(
            - src_version_entity["version"],
            src_version_entity["productId"],
            task_id=src_version_entity.get("taskId"),
            data=copy.deepcopy(src_version_entity["data"]),
            attribs=copy.deepcopy(src_version_entity["attrib"]),
            entity_id=entity_id,
        )

        if old_version:
            self.log.debug("Replacing old hero version.")
            update_data = prepare_changes(
                old_version, new_hero_version
            )
            op_session.update_entity(
                project_name,
                "version",
                old_version["id"],
                update_data
            )
        else:
            self.log.debug("Creating first hero version.")
            op_session.create_entity(
                project_name, "version", new_hero_version
            )

        # Separate old representations into `to replace` and `to delete`
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
                self.log.debug((
                    "Backup folder already exists."
                    " Trying to remove \"{}\""
                ).format(_backup_hero_publish_dir))

                try:
                    shutil.rmtree(_backup_hero_publish_dir)
                    backup_hero_publish_dir = _backup_hero_publish_dir
                    break
                except Exception:
                    self.log.info(
                        "Could not remove previous backup folder."
                        " Trying to add index to folder name."
                    )

                _backup_hero_publish_dir = (
                    backup_hero_publish_dir + str(idx)
                )
                if not os.path.exists(_backup_hero_publish_dir):
                    backup_hero_publish_dir = _backup_hero_publish_dir
                    break

                if idx > max_idx:
                    raise AssertionError((
                        "Backup folders are fully occupied to max index \"{}\""
                    ).format(max_idx))
                    break

                idx += 1

            self.log.debug("Backup folder path is \"{}\"".format(
                backup_hero_publish_dir
            ))
            try:
                os.rename(hero_publish_dir, backup_hero_publish_dir)
            except PermissionError:
                raise AssertionError((
                    "Could not create hero version because it is not"
                    " possible to replace current hero files."
                ))

        try:
            src_to_dst_file_paths = []
            repre_integrate_data = []
            path_template_obj = anatomy.get_template_item(
                "hero", template_key, "path"
            )
            for repre_info in published_repres.values():

                # Skip if new repre does not have published repre files
                published_files = repre_info["published_files"]
                if len(published_files) == 0:
                    continue

                # Prepare anatomy data
                anatomy_data = copy.deepcopy(repre_info["anatomy_data"])
                anatomy_data.pop("version", None)

                # Get filled path to repre context
                template_filled = path_template_obj.format_strict(
                    anatomy_data
                )
                repre_context = template_filled.used_values
                for key in self.db_representation_context_keys:
                    value = anatomy_data.get(key)
                    if value is not None:
                        repre_context[key] = value

                # Prepare new repre
                repre_entity = copy.deepcopy(repre_info["representation"])
                repre_entity.pop("id", None)
                repre_entity["versionId"] = new_hero_version["id"]
                repre_entity["context"] = repre_context
                repre_entity["attrib"] = {
                    "path": str(template_filled),
                    "template": hero_template.template
                }

                dst_paths = []
                # Prepare paths of source and destination files
                if len(published_files) == 1:
                    dst_paths.append(str(template_filled))
                    src_to_dst_file_paths.append(
                        (published_files[0], template_filled)
                    )
                else:
                    collections, remainders = clique.assemble(published_files)
                    if remainders or not collections or len(collections) > 1:
                        raise Exception((
                            "Integrity error. Files of published"
                            " representation is combination of frame"
                            " collections and single files. Collections:"
                            " `{}` Single files: `{}`"
                        ).format(str(collections), str(remainders)))

                    src_col = collections[0]

                    # Get head and tail for collection
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
                        src_to_dst_file_paths.append(
                            (src_file, dst_file)
                        )
                        dst_paths.append(dst_file)

                repre_integrate_data.append(
                    (repre_entity, dst_paths)
                )

            self.path_checks = []

            # Copy(hardlink) paths of source and destination files
            # TODO should we *only* create hardlinks?
            # TODO should we keep files for deletion until this is successful?
            for src_path, dst_path in src_to_dst_file_paths:
                self.copy_file(src_path, dst_path)

            for src_path, dst_path in other_file_paths_mapping:
                self.copy_file(src_path, dst_path)

            # Update prepared representation etity data with files
            #   and integrate it to server.
            # NOTE: This must happen with existing files on disk because of
            #   file hash.
            for repre_entity, dst_paths in repre_integrate_data:
                repre_files = self.get_files_info(dst_paths, anatomy)
                repre_entity["files"] = repre_files

                repre_name_low = repre_entity["name"].lower()
                # Replace current representation
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

                # Activate representation
                elif repre_name_low in inactive_old_repres_by_name:
                    inactive_repre = inactive_old_repres_by_name.pop(
                        repre_name_low
                    )
                    repre_entity["id"] = inactive_repre["id"]
                    update_data = prepare_changes(
                        inactive_repre, repre_entity
                    )
                    op_session.update_entity(
                        project_name,
                        "representation",
                        inactive_repre["id"],
                        update_data
                    )

                # Create representation
                else:
                    op_session.create_entity(
                        project_name,
                        "representation",
                        repre_entity
                    )

            # Deactivate not replaced representations
            for repre in old_repres_to_delete.values():
                op_session.update_entity(
                    project_name,
                    "representation",
                    repre["id"],
                    {"active": False}
                )

            op_session.commit()

            # Remove backuped previous hero
            if (
                backup_hero_publish_dir is not None and
                os.path.exists(backup_hero_publish_dir)
            ):
                shutil.rmtree(backup_hero_publish_dir)

        except Exception:
            if (
                backup_hero_publish_dir is not None and
                os.path.exists(backup_hero_publish_dir)
            ):
                if os.path.exists(hero_publish_dir):
                    shutil.rmtree(hero_publish_dir)
                os.rename(backup_hero_publish_dir, hero_publish_dir)
            self.log.error((
                "!!! Creating of hero version failed."
                " Previous hero version maybe lost some data!"
            ))
            raise

        self.log.debug((
            "--- hero version integration for product `{}`"
            " seems to be successful."
        ).format(
            instance.data["productName"]
        ))

    def get_files_info(self, filepaths, anatomy):
        """Prepare 'files' info portion for representations.

        Arguments:
            filepaths (Iterable[str]): List of transferred file paths.
            anatomy (Anatomy): Project anatomy.

        Returns:
            list[dict[str, Any]]: Representation 'files' information.

        """
        file_infos = []
        for filepath in filepaths:
            file_info = self.prepare_file_info(filepath, anatomy)
            file_infos.append(file_info)
        return file_infos

    def prepare_file_info(self, path, anatomy):
        """ Prepare information for one file (asset or resource)

        Arguments:
            path (str): Destination url of published file.
            anatomy (Anatomy): Project anatomy part from instance.

        Returns:
            dict[str, Any]: Representation file info dictionary.

        """
        return {
            "id": create_entity_id(),
            "name": os.path.basename(path),
            "path": self.get_rootless_path(anatomy, path),
            "size": os.path.getsize(path),
            "hash": source_hash(path),
            "hash_type": "op3",
        }

    def get_publish_dir(self, instance, template_key):
        anatomy = instance.context.data["anatomy"]
        template_data = copy.deepcopy(instance.data["anatomyData"])

        if "originalBasename" in instance.data:
            template_data.update({
                "originalBasename": instance.data.get("originalBasename")
            })

        template_obj = anatomy.get_template_item(
            "hero", template_key, "directory"
        )
        publish_folder = os.path.normpath(
            template_obj.format_strict(template_data)
        )

        self.log.debug("hero publish dir: \"{}\"".format(publish_folder))

        return publish_folder

    def _get_template_key(self, project_name, instance):
        anatomy_data = instance.data["anatomyData"]
        task_info = anatomy_data.get("task") or {}
        host_name = instance.context.data["hostName"]
        product_type = instance.data["productType"]

        return get_publish_template_name(
            project_name,
            host_name,
            product_type,
            task_info.get("name"),
            task_info.get("type"),
            project_settings=instance.context.data["project_settings"],
            hero=True,
            logger=self.log
        )

    def get_rootless_path(self, anatomy, path):
        """Returns, if possible, path without absolute portion from root
            (eg. 'c:\' or '/opt/..')

         This information is platform dependent and shouldn't be captured.
         Example:
             'c:/projects/MyProject1/Assets/publish...' >
             '{root}/MyProject1/Assets...'

        Args:
            anatomy (Anatomy): Project anatomy.
            path (str): Absolute path.

        Returns:
            str: Path where root path is replaced by formatting string.

        """
        success, rootless_path = anatomy.find_root_template_from_path(path)
        if success:
            path = rootless_path
        else:
            self.log.warning((
                "Could not find root path for remapping \"{}\"."
                " This may cause issues on farm."
            ).format(path))
        return path

    def copy_file(self, src_path, dst_path):
        # TODO check drives if are the same to check if cas hardlink
        dirname = os.path.dirname(dst_path)

        try:
            os.makedirs(dirname)
            self.log.debug("Folder(s) created: \"{}\"".format(dirname))
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                self.log.error("An unexpected error occurred.", exc_info=True)
                raise

            self.log.debug("Folder already exists: \"{}\"".format(dirname))

        self.log.debug("Copying file \"{}\" to \"{}\"".format(
            src_path, dst_path
        ))

        # First try hardlink and copy if paths are cross drive
        try:
            create_hard_link(src_path, dst_path)
            # Return when successful
            return

        except OSError as exc:
            # re-raise exception if different than
            # EXDEV - cross drive path
            # EINVAL - wrong format, must be NTFS
            self.log.debug("Hardlink failed with errno:'{}'".format(exc.errno))
            if exc.errno not in [errno.EXDEV, errno.EINVAL]:
                raise

        shutil.copy(src_path, dst_path)

    def version_from_representations(self, project_name, repres):
        for repre in repres:
            version = ayon_api.get_version_by_id(
                project_name, repre["versionId"]
            )
            if version:
                return version

    def current_hero_ents(self, project_name, version):
        hero_version = ayon_api.get_hero_version_by_product_id(
            project_name, version["productId"]
        )

        if not hero_version:
            return (None, [])

        hero_repres = list(ayon_api.get_representations(
            project_name, version_ids={hero_version["id"]}
        ))
        return (hero_version, hero_repres)

    def _get_name_without_ext(self, value):
        file_name = os.path.basename(value)
        file_name, _ = os.path.splitext(file_name)
        return file_name
