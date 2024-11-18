"""Integrate representations with traits."""
from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any, List

import pyblish.api
from ayon_api import (
    get_attributes_for_type,
    get_product_by_name,
    # get_representations,
    get_version_by_name,
)
from ayon_api.operations import (
    OperationsSession,
    new_product_entity,
    # new_representation_entity,
    new_version_entity,
)
from ayon_core.pipeline.publish import (
    PublishError,
    get_publish_template_name,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    FileLocation,
    Persistent,
    Representation,
)
from pipeline.traits import MissingTraitError, PixelBased
from pipeline.traits.content import FileLocations

if TYPE_CHECKING:
    import logging
    from pathlib import Path

    from pipeline import Anatomy


def get_instance_families(instance: pyblish.api.Instance) -> List[str]:
    """Get all families of the instance.

    Todo:
        Move to the library.

    Args:
        instance (pyblish.api.Instance): Instance to get families from.

    Returns:
        List[str]: List of families.

    """
    family = instance.data.get("family")
    families = []
    if family:
        families.append(family)

    for _family in (instance.data.get("families") or []):
        if _family not in families:
            families.append(_family)

    return families


def get_changed_attributes(
        old_entity: dict, new_entity: dict) -> (dict[str, Any]):
    """Prepare changes for entity update.

    Todo:
        Move to the library.

    Args:
        old_entity (dict[str, Any]): Existing entity.
        new_entity (dict[str, Any]): New entity.

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




class IntegrateTraits(pyblish.api.InstancePlugin):
    """Integrate representations with traits."""

    label = "Integrate Asset"
    order = pyblish.api.IntegratorOrder
    log: logging.Logger

    def process(self, instance: pyblish.api.Instance) -> None:
        """Integrate representations with traits.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        """
        # 1) skip farm and integrate ==  False

        if not instance.data.get("integrate"):
            self.log.debug("Instance is marked to skip integrating. Skipping")
            return

        if instance.data.get("farm"):
            self.log.debug(
                "Instance is marked to be processed on farm. Skipping")
            return

        # TODO (antirotor): Find better name for the key  # noqa: FIX002, TD003
        if not instance.data.get("representations_with_traits"):
            self.log.debug(
                "Instance has no representations with traits. Skipping")
            return

        # 2) filter representations based on LifeCycle traits
        instance.data["representations_with_traits"] = self.filter_lifecycle(
            instance.data["representations_with_traits"]
        )

        representations: list[Representation] = instance.data["representations_with_traits"]  # noqa: E501
        if not representations:
            self.log.debug(
                "Instance has no persistent representations. Skipping")
            return

        # 3) get anatomy template
        template = self.get_template(instance)

        # 4) initialize OperationsSession()
        op_session = OperationsSession()

        # 5) Prepare product
        product_entity = self.prepare_product(instance, op_session)

        # 6) Prepare version
        version_entity = self.prepare_version(
            instance, op_session, product_entity
        )
        instance.data["versionEntity"] = version_entity

        instance_template_data = {}
        transfers = []
        # handle {originalDirname} requested in the template
        if "{originalDirname}" in template:
            instance_template_data = {
                "originalDirname": self._get_relative_to_root_original_dirname(
                    instance)
            }
        # 6.5) prepare template and data to format it
        for representation in representations:

            # validate representation first
            representation.validate()
            template_data = self.get_template_data_from_representation(
                representation, instance)
            # add instance based template data
            template_data.update(instance_template_data)
            if "{originalBasename}" in template:
                # Remove 'frame' from template data because original frame
                # number will be used.
                template_data.pop("frame", None)
                # WIP: use trait logic to get original frame range
                # check if files listes in FileLocations trait match frames
                # in sequence

            transfers += self.get_transfers_from_representation(
                representation, template, template_data)

        # 7) Get transfers from representations
        for representation in representations:
            # this should test version-less FileLocation probably
            if representation.contains_trait_by_id(
                    FileLocation.get_versionless_id()):
                self.log.debug(
                    "Representation: %s", representation)

    def _get_relative_to_root_original_dirname(
            self, instance: pyblish.api.Instance) -> str:
        """Get path stripped of root of the original directory name.

        If `originalDirname` or `stagingDir` is set in instance data,
        this will return it as rootless path. The path must reside
        within the project directory.
        """
        original_directory = (
                instance.data.get("originalDirname") or
                instance.data.get("stagingDir"))
        anatomy = instance.context.data["anatomy"]

        _rootless = self.get_rootless_path(anatomy, original_directory)
        # this check works because _rootless will be the same as
        # original_directory if the original_directory cannot be transformed
        # to the rootless path.
        if _rootless == original_directory:
            msg = (
                f"Destination path '{original_directory}' must "
                "be in project directory.")
            raise PublishError(msg)
        # the root is at the beginning - {root[work]}/rest/of/the/path
        relative_path_start = _rootless.rfind("}") + 2
        return _rootless[relative_path_start:]


        # 8) Transfer files
        # 9) Commit the session to AYON
        # 10) Finalize represetations - add integrated path Trait etc.

    @staticmethod
    def filter_lifecycle(
            representations: list[Representation]) -> list[Representation]:
        """Filter representations based on LifeCycle traits.

        Args:
            representations (list): List of representations.

        Returns:
            list: Filtered representations.

        """
        return [
            representation
            for representation in representations
            if representation.contains_trait(Persistent)
        ]

    def get_template_name(self, instance: pyblish.api.Instance) -> str:
        """Return anatomy template name to use for integration.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        Returns:
            str: Anatomy template name

        """
        # Anatomy data is pre-filled by Collectors
        context = instance.context
        project_name = context.data["projectName"]

        # Task can be optional in anatomy data
        host_name = context.data["hostName"]
        anatomy_data = instance.data["anatomyData"]
        product_type = instance.data["productType"]
        task_info = anatomy_data.get("task") or {}

        return get_publish_template_name(
            project_name,
            host_name,
            product_type,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
            project_settings=context.data["project_settings"],
            logger=self.log
        )

    def get_template(self, instance: pyblish.api.Instance) -> str:
        """Return anatomy template name to use for integration.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        Returns:
            str: Anatomy template name

        """
        # Anatomy data is pre-filled by Collectors
        template_name = self.get_template_name(instance)
        anatomy = instance.context.data["anatomy"]
        publish_template = anatomy.get_template_item("publish", template_name)
        path_template_obj = publish_template["path"]
        return path_template_obj.template.replace("\\", "/")

    def prepare_product(
            self,
            instance: pyblish.api.Instance,
            op_session: OperationsSession) -> dict:
        """Prepare product for integration.

        Args:
            instance (pyblish.api.Instance): Instance to process.
            op_session (OperationsSession): Operations session.

        Returns:
            dict: Product entity.

        """
        project_name = instance.context.data["projectName"]
        folder_entity = instance.data["folderEntity"]
        product_name = instance.data["productName"]
        product_type = instance.data["productType"]
        self.log.debug("Product: %s", product_name)

        # Get existing product if it exists
        existing_product_entity = get_product_by_name(
            project_name, product_name, folder_entity["id"]
        )

        # Define product data
        data = {
            "families": get_instance_families(instance)
        }
        attributes = {}

        product_group = instance.data.get("productGroup")
        if product_group:
            attributes["productGroup"] = product_group
        elif existing_product_entity:
            # Preserve previous product group if new version does not set it
            product_group = existing_product_entity.get("attrib", {}).get(
                "productGroup"
            )
            if product_group is not None:
                attributes["productGroup"] = product_group

        product_id = existing_product_entity["id"] if existing_product_entity else None  # noqa: E501
        product_entity = new_product_entity(
            product_name,
            product_type,
            folder_entity["id"],
            data=data,
            attribs=attributes,
            entity_id=product_id
        )

        if existing_product_entity is None:
            # Create a new product
            self.log.info(
                "Product '%s' not found, creating ...",
                product_name
            )
            op_session.create_entity(
                project_name, "product", product_entity
            )

        else:
            # Update existing product data with new data and set in database.
            # We also change the found product in-place so we don't need to
            # re-query the product afterward
            update_data = get_changed_attributes(
                existing_product_entity, product_entity
            )
            op_session.update_entity(
                project_name,
                "product",
                product_entity["id"],
                update_data
            )

        self.log.debug("Prepared product: %s", product_name)
        return product_entity

    def prepare_version(
            self,
            instance: pyblish.api.Instance,
            op_session: OperationsSession,
            product_entity: dict) -> dict:
        """Prepare version for integration.

        Args:
            instance (pyblish.api.Instance): Instance to process.
            op_session (OperationsSession): Operations session.
            product_entity (dict): Product entity.

        Returns:
            dict: Version entity.

        """
        project_name = instance.context.data["projectName"]
        version_number = instance.data["version"]
        task_entity = instance.data.get("taskEntity")
        task_id = task_entity["id"] if task_entity else None
        existing_version = get_version_by_name(
            project_name,
            version_number,
            product_entity["id"]
        )
        version_id = existing_version["id"] if existing_version else None
        all_version_data = self.get_version_data_from_instance(instance)
        version_data = {}
        version_attributes = {}
        attr_defs = self.get_attributes_for_type(instance.context, "version")
        for key, value in all_version_data.items():
            if key in attr_defs:
                version_attributes[key] = value
            else:
                version_data[key] = value

        version_entity = new_version_entity(
            version_number,
            product_entity["id"],
            task_id=task_id,
            status=instance.data.get("status"),
            data=version_data,
            attribs=version_attributes,
            entity_id=version_id,
        )

        if existing_version:
            self.log.debug("Updating existing version ...")
            update_data = get_changed_attributes(
                existing_version, version_entity)
            op_session.update_entity(
                project_name,
                "version",
                version_entity["id"],
                update_data
            )
        else:
            self.log.debug("Creating new version ...")
            op_session.create_entity(
                project_name, "version", version_entity
            )

        self.log.debug(
            "Prepared version: v%s",
            "{:03d}".format(version_entity["version"])
        )

        return version_entity

    def get_version_data_from_instance(
            self, instance: pyblish.api.Instance) -> dict:
        """Get version data from the Instance.

        Args:
            instance (pyblish.api.Instance): the current instance
                being published.

        Returns:
            dict: the required information for ``version["data"]``

        """
        context = instance.context

        # create relative source path for DB
        if "source" in instance.data:
            source = instance.data["source"]
        else:
            source = context.data["currentFile"]
            anatomy = instance.context.data["anatomy"]
            source = self.get_rootless_path(anatomy, source)
        self.log.debug("Source: %s", source)

        version_data = {
            "families": get_instance_families(instance),
            "time": context.data["time"],
            "author": context.data["user"],
            "source": source,
            "comment": instance.data["comment"],
            "machine": context.data.get("machine"),
            "fps": instance.data.get("fps", context.data.get("fps"))
        }

        intent_value = context.data.get("intent")
        if intent_value and isinstance(intent_value, dict):
            intent_value = intent_value.get("value")

        if intent_value:
            version_data["intent"] = intent_value

        # Include optional data if present in
        optionals = [
            "frameStart", "frameEnd", "step",
            "handleEnd", "handleStart", "sourceHashes"
        ]
        for key in optionals:
            if key in instance.data:
                version_data[key] = instance.data[key]

        # Include instance.data[versionData] directly
        version_data_instance = instance.data.get("versionData")
        if version_data_instance:
            version_data.update(version_data_instance)

        return version_data

    def get_rootless_path(self, anatomy: Anatomy, path: str) -> str:
        r"""Get rootless variant of the path.

        Returns, if possible, path without absolute portion from the root
        (e.g. 'c:\' or '/opt/..'). This is basically wrapper for the
        meth:`Anatomy.find_root_template_from_path` method that displays
        warning if root path is not found.

         This information is platform dependent and shouldn't be captured.
         For example::

             'c:/projects/MyProject1/Assets/publish...'
             will be transformed to:
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
                'Could not find root path for remapping "%s".'
                " This may cause issues on farm."
            ),path)
        return path

    def get_attributes_for_type(
            self, context: pyblish.api.Context, entity_type: str) -> dict:
        """Get AYON attributes for the given entity type."""
        return self.get_attributes_by_type(context)[entity_type]

    def get_attributes_by_type(
            self, context: pyblish.api.Context) -> dict:
        """Gets AYON attributes from the given context."""
        attributes = context.data.get("ayonAttributes")
        if attributes is None:
            attributes = {
                key: get_attributes_for_type(key)
                for key in (
                    "project",
                    "folder",
                    "product",
                    "version",
                    "representation",
                )
            }
            context.data["ayonAttributes"] = attributes
        return attributes

    def get_template_data_from_representation(
            self,
            representation: Representation,
            instance: pyblish.api.Instance) -> dict:
        """Get template data from representation.

        Using representation traits and data on instance
        prepare data for formatting template.

        Args:
            representation (Representation): Representation to process.
            instance (pyblish.api.Instance): Instance to process.

        Returns:
            dict: Template data.

        """
        template_data = copy.deepcopy(instance.data["anatomyData"])
        template_data["representation"] = representation.name

        # add colorspace data to template data
        if representation.contains_trait(ColorManaged):
            colorspace_data: ColorManaged = representation.get_trait(
                ColorManaged)

            template_data["colorspace"] = {
                "colorspace": colorspace_data.color_space,
                "config": colorspace_data.config
            }

            # add explicit list of traits properties to template data
            # there must be some better way to handle this
            try:
                # resolution from PixelBased trait
                template_data["resolution_width"] = representation.get_trait(
                    PixelBased).display_window_width
                template_data["resolution_height"] = representation.get_trait(
                    PixelBased).display_window_height
                # get fps from representation traits
                # is this the right way? Isn't it going against the
                # trait abstraction?
                traits = representation.get_traits()
                for trait in traits.values():
                    if hasattr(trait, "frames_per_second"):
                        template_data["fps"] = trait.fps

                # Note: handle "output" and "originalBasename"

            except MissingTraitError as e:
                self.log.debug("Missing traits: %s", e)

        return template_data

    def get_transfers_from_representation(
            self,
            representation: Representation,
            template: str,
            template_data: dict) -> list:
        """Get transfers from representation.

        Args:
            representation (Representation): Representation to process.
            template (str): Template to format.
            template_data (dict): Template data.

        Returns:
            list: List of transfers.

        """
        transfers = []
        # check if representation contains traits with files
        if not representation.contains_traits(
                [FileLocation, FileLocations]):
            return transfers

        files: list[Path] = []

        if representation.contains_trait(FileLocations):
            files = [
                location.file_path
                for location in representation.get_trait(
                    FileLocations).file_paths
            ]
        elif representation.contains_trait(FileLocation):
            file_location: FileLocation = representation.get_trait(
                FileLocation)
            files = [file_location.file_path]

        template_data_copy = copy.deepcopy(template_data)
        for file in files:
            if "{originalBasename}" in template:
                template_data_copy["originalBasename"] = file.stem
            """
            dst = path_template_obj.format_strict(template_data)
            src = os.path.join(stagingdir, src_file_name)
            """
        if representation.contains_trait_by_id(
                FileLocation.get_versionless_id()):
            file_location: FileLocation = representation.get_trait_by_id(
                FileLocation.get_versionless_id())
            """
            transfers += self.get_transfers_from_file_location(
                file_location, template, template_data)
            """
        return transfers
