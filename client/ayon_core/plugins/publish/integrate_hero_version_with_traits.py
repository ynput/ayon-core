"""Integrate Hero version with representation traits."""
from __future__ import annotations
import copy
from ayon_core.pipeline.publish import get_trait_representations
from ayon_core.pipeline.traits import (
    Persistent,
    Representation,
    TraitBase,
)
from ayon_api.operations import (
    OperationsSession,
    new_version_entity,
)

import pyblish.api
import ayon_api
from ayon_api.utils import create_entity_id
from typing import TYPE_CHECKING, Optional

from ayon_core.pipeline.publish import (
    get_publish_template_name,
    OptionalPyblishPluginMixin,
    KnownPublishError,
)

if TYPE_CHECKING:
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

    def process(self, instance: pyblish.api.Instance) -> None:
        """Integrate Hero version with representation traits.

        Args:
            instance (pyblish.api.Instance): The instance to process.

        """
        if not self.is_active(instance.data):
            return

        anatomy = instance.context.data["anatomy"]
        project_name = anatomy.project_name

        template_key = self._get_template_key(project_name, instance)
        hero_template = anatomy.get_template_item(
            "hero", template_key, "path", default=None
        )

        if hero_template is None:
            self.log.warning(
                f"Anatomy of project '{project_name}' does not have set "
                f"'{template_key}' template key!")
            return

        self.log.debug(
            f"'hero' template check was successful. '{hero_template}'"
        )

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

        # Current version
        old_version, old_repres = self.current_hero_entities(
            project_name, src_version_entity
        )

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
        repre_entities = ayon_api.get_representations(
            project_name=project_name,
            version_ids={new_hero_version["id"]})

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
        old_repres_to_delete = {}

        for repre in filtered_representations:
            repre_name_low = repre.name.lower()
            if repre_name_low in old_repres_by_name:
                old_repres_to_replace[repre_name_low] = (
                    old_repres_by_name.pop(repre_name_low)
                )

        if old_repres_by_name:
            old_repres_to_delete = old_repres_by_name

        if old_repres_by_name:
            old_repres_to_delete = old_repres_by_name


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
        product_base_type = instance.data.get("productBaseType")
        if not product_base_type:
            product_base_type = instance.data["productType"]

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