"""Integrate Hero version with representation traits."""
from __future__ import annotations
from itertools import count

import json
import os
from pprint import pformat
import shutil
import copy
from ayon_core.pipeline.traits import (
    Representation,
    get_transfers_from_representations,
)
from ayon_core.lib.file_transaction import (
    DuplicateDestinationError,
    FileTransaction,
)
from ayon_api.operations import (
    OperationsSession,
    new_version_entity,
)

import pyblish.api
import ayon_api

from typing import TYPE_CHECKING, Optional

from ayon_core.pipeline.publish import (
    get_publish_template_name,
    OptionalPyblishPluginMixin,
    KnownPublishError,
)

if TYPE_CHECKING:
    from ayon_core.pipeline import Anatomy
    from ayon_core.pipeline.anatomy.templates import (
        AnatomyStringTemplate,
        TemplateItem as AnatomyTemplateItem,
    )
    import logging


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


class IntegrateHeroVersionTraits(
    OptionalPyblishPluginMixin,
    pyblish.api.InstancePlugin):
    """Integrate Hero version with representation traits."""

    order = pyblish.api.IntegratorOrder + 0.1
    label = "Integrate Hero version with representation traits"
    setting_category = "core"
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

    ignored_representation_names: set[str] = set()
    log: "logging.Logger"

    use_hardlinks = False

    def process(self, instance: pyblish.api.Instance) -> None:
        """Integrate Hero version with representation traits.

        Args:
            instance (pyblish.api.Instance): The instance to process.

        """
        if not self.is_active(instance.data):
            return

        anatomy: Anatomy = instance.context.data["anatomy"]
        project_name = anatomy.project_name

        template_key = self._get_template_key(project_name, instance)
        hero_template: AnatomyTemplateItem = anatomy.get_template_item(
            "hero", template_key)

        if hero_template is None:
            self.log.warning(
                f"Anatomy of project '{project_name}' does not have set "
                f"'{template_key}' template key!")
            return

        hero_publish_dir = self.get_publish_dir(instance, template_key)

        src_version_entity = instance.data.get("versionEntity")

        if src_version_entity is None:
            msg = (
                f"Instance '{instance.name}' does not have 'versionEntity' "
                "data. It has to go first through product integrator."
            )
            self.log.error(msg)
            raise KnownPublishError(msg)

        if src_version_entity["version"] == 0:
            self.log.warning("Version 0 cannot have hero version. Skipping.")
            return

        # Current hero version data
        old_version, old_repres = self.current_hero_entities(
            project_name, src_version_entity
        )

        # old representations are coming from already existing hero version
        # new representations are coming from current version that is
        # being published

        op_session = OperationsSession()

        entity_id = old_version["id"] if old_version else None
        new_hero_version = new_version_entity(
            - src_version_entity["version"],
            src_version_entity["productId"],
            task_id=src_version_entity.get("taskId"),
            data=copy.deepcopy(src_version_entity["data"]),
            attribs=copy.deepcopy(src_version_entity["attrib"]),
            entity_id=entity_id,
        )
        self.log.debug(f"Prepared hero version entity: {new_hero_version}")

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

        # Store hero entity to 'instance.data'
        instance.data["heroVersionEntity"] = new_hero_version

        # get published representations with traits for the version
        repre_entities = list(ayon_api.get_representations(
            project_name=project_name,
            version_ids={src_version_entity["id"]}))

        self.log.debug(
            f"Found {len(repre_entities)} representations for hero version."
        )

        if not repre_entities:
            msg = (
                f"Version '{new_hero_version['id']}' does not have any "
                "representations. At least one representation with traits "
                "has to be published to create hero version."
            )
            self.log.error(msg)
            raise KnownPublishError(msg)

        # Separate old representations into `to replace` and `to delete`
        inactive_old_repres_by_name = {}
        old_repres_by_name = {}
        for repre in old_repres:
            low_name = repre["name"].lower()
            if repre["active"]:
                old_repres_by_name[low_name] = repre
            else:
                inactive_old_repres_by_name[low_name] = repre

        old_repres_to_replace = {}

        for repre in repre_entities:
            repre_name_low = repre["name"].lower()
            if repre_name_low in old_repres_by_name:
                old_repres_to_replace[repre_name_low] = (
                    old_repres_by_name.pop(repre_name_low)
                )

        old_repres_to_delete = old_repres_by_name or {}
        backup_hero_publish_dir = None
        if os.path.exists(hero_publish_dir):
            backup_hero_publish_dir = self._backup_hero_version_dir(
                hero_publish_dir)

        for repe in repre_entities:
            self.log.debug(f"representation: {pformat(repe, indent=4)}")

        representations = [
            Representation.from_dict(
                name=repre["name"],
                representation_id=repre["id"],
                trait_data=json.loads(repre["traits"])
            )
            for repre in repre_entities
            if repre["name"] not in self.ignored_representation_names and repre["traits"]
        ]

        self.log.debug(
            "Prepared representations for hero version: %s",
            [repre.name for repre in representations]
        )
        self.log.debug(f"Hero template: {hero_template['path']}")

        transfers = get_transfers_from_representations(
            instance,
            template=hero_template,
            representations=representations)

        self.log.debug(f"got {len(transfers)} file transfers to "
                       "process for hero version.")
        file_transactions = FileTransaction(
            log=self.log,
            # Enforce unique transfers
            allow_queue_replacements=False
        )
        mode = FileTransaction.MODE_COPY
        if self.use_hardlinks:
            mode = FileTransaction.MODE_HARDLINK

        try:
            for transfer in transfers:
                self.log.debug(
                    "Transferring file: %s -> %s",
                    transfer.source,
                    transfer.destination
                )
                file_transactions.add(
                    transfer.source.as_posix(),
                    transfer.destination.as_posix(),
                    mode=mode,
                )
            file_transactions.process()
        except DuplicateDestinationError as e:
            msg = (
                "Multiple representations are trying to transfer files to "
                "the same destination. This is not allowed because it can "
                "cause conflicts and unintended overwrites. Please check the "
                "representations and their traits to ensure they are unique."
            )
            self.log.error(msg)
            raise KnownPublishError(msg) from e
        except Exception as e:
            msg = (
                "An error occurred during file transfer for hero version. "
                "Please check the logs for more details."
            )
            self.log.error(msg)
            raise KnownPublishError(msg) from e
        finally:
            file_transactions.finalize()

    def _backup_hero_version_dir(self, hero_publish_dir: str) -> str:
        """Backup current hero version publish directory.

        Args:
            hero_publish_dir (str): The path to current hero
                version publish directory.
        """
        backup_hero_publish_dir = f"{hero_publish_dir}.BACKUP"
        # max backup dirs present
        max_idx = 10
        idx = 0
        _backup_hero_publish_dir = backup_hero_publish_dir
        while os.path.exists(_backup_hero_publish_dir):
            self.log.debug(
                "Backup folder already exists. "
                f'Trying to remove "{_backup_hero_publish_dir}"'
            )

            try:
                shutil.rmtree(_backup_hero_publish_dir)
                backup_hero_publish_dir = _backup_hero_publish_dir
                break
            except Exception:
                self.log.info(
                    "Could not remove previous backup folder. "
                    "Trying to add index to folder name."
                )

            _backup_hero_publish_dir = (
                    backup_hero_publish_dir + str(idx)
            )
            if not os.path.exists(_backup_hero_publish_dir):
                backup_hero_publish_dir = _backup_hero_publish_dir
                break

            if idx > max_idx:
                msg = (
                    "Backup folders are fully occupied "
                    f'to max index "{max_idx}"'
                )
                raise AssertionError(msg)
            idx += 1

        self.log.debug(f'Backup folder path is \"{backup_hero_publish_dir}\"')
        try:
            os.rename(hero_publish_dir, backup_hero_publish_dir)
        except PermissionError as e:
            msg = (
                "Could not create hero version because it is not "
                "possible to replace current hero files."
            )
            raise AssertionError(msg) from e

        return backup_hero_publish_dir

    @staticmethod
    def version_from_representations(
            project_name: str,
            repres: list[Representation]) -> Optional[dict]:
        """Get version entity from representations.

        Args:
            project_name (str): The name of the project.
            repres (list[Representation]): List of representations
                to check.

        Returns:
            Optional[dict]: The version entity if found, otherwise None.

        """
        for rep in repres:
            version = ayon_api.get_version_by_id(
                project_name, rep["versionId"]
            )
            if version:
                return version

        return None

    def _get_template_key(
            self,
            project_name: str,
            instance: pyblish.api.Instance) -> str:
        """Get template key for hero template.

        Args:
            project_name (str): The name of the project.
            instance (pyblish.api.Instance): The instance to get data from.

        Returns:
            str: The template key to use for hero template.

        """
        anatomy_data = instance.data["anatomyData"]
        task_info = anatomy_data.get("task") or {}
        host_name = instance.context.data["hostName"]
        product_base_type = (
                instance.data.get("productBaseType")
                or instance.data["productType"]
        )

        return get_publish_template_name(
            project_name,
            host_name,
            product_base_type=product_base_type,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
            project_settings=instance.context.data["project_settings"],
            hero=True,
            logger=self.log
        )

    @staticmethod
    def current_hero_entities(
            project_name: str,
            version: dict) -> tuple[Optional[dict], list[dict]]:
        """Get current hero version and representations.

        Args:
            project_name (str): The name of the project.
            version (dict): The version entity to find hero version for.

        Returns:
            tuple[Optional[dict], list[dict]]: The hero version entity and list
                of its representations. If hero version is not found, returns
                (None, []).

        """
        hero_version = ayon_api.get_hero_version_by_product_id(
            project_name, version["productId"]
        )

        if not hero_version:
            return None, []

        hero_repres = list(ayon_api.get_representations(
            project_name, version_ids={hero_version["id"]}
        ))
        return hero_version, hero_repres

    def get_publish_dir(
            self,
            instance: pyblish.api.Instance,
            template_key: str) -> str:
        """Get publish directory for hero version.

        Args:
            instance (pyblish.api.Instance): The instance to get data from.
            template_key (str): The template key to use for hero template.

        Returns:
            str: The path to publish directory for hero version.

        """
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

        self.log.debug(f'hero publish dir: "{publish_folder}"')

        return publish_folder
