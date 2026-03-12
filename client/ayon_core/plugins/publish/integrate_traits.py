"""Integrate representations with traits."""
from __future__ import annotations

import json
from pathlib import Path
from pprint import pformat
from typing import TYPE_CHECKING, Any

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
    new_representation_entity,
    new_version_entity,
)
from ayon_api.utils import create_entity_id
from ayon_core.lib import source_hash
from ayon_core.lib.file_transaction import (
    FileTransaction,
)
from ayon_core.pipeline import is_product_base_type_supported
from ayon_core.pipeline.publish import (
    PublishError,
    get_instance_families,
    has_trait_representations,
    get_trait_representations,
    set_trait_representations,
    get_rootless_path,
    get_version_data_from_instance,
    get_template_name,
)
from ayon_core.pipeline.traits import (
    Persistent,
    Representation,
    TransferItem,

    get_transfers_from_representations,
    get_template_data_from_representation,
)

if TYPE_CHECKING:
    import logging

    from ayon_core.pipeline import Anatomy


class RepresentationEntity:
    """Representation entity data."""
    id: str
    versionId: str  # noqa: N815
    name: str
    files: dict[str, Any]
    attrib: dict[str, Any]
    data: str
    tags: list[str]
    status: str

    def __init__(self,
        id: str,
        versionId: str,  # noqa: N815
        name: str,
        files: dict[str, Any],
        attrib: dict[str, Any],
        data: str,
        tags: list[str],
        status: str):
        """Initialize RepresentationEntity.

        Args:
            id (str): Entity ID.
            versionId (str): Version ID.
            name (str): Representation name.
            files (dict[str, Any]): Files in the representation.
            attrib (dict[str, Any]): Attributes of the representation.
            data (str): Data of the representation.
            tags (list[str]): Tags of the representation.
            status (str): Status of the representation.

        """
        self.id = id
        self.versionId = versionId
        self.name = name
        self.files = files
        self.attrib = attrib
        self.data = data
        self.tags = tags
        self.status = status


def get_changed_attributes(
        old_entity: dict, new_entity: dict) -> dict[str, Any]:
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
        attrib_changes = {
            key: value
            for key, value in new_entity["attrib"].items()
            if value != old_entity["attrib"].get(key)
        }
    if attrib_changes:
        changes["attrib"] = attrib_changes
    return changes


def prepare_for_json(data: dict[str, Any]) -> dict[str, Any]:
    """Prepare data for JSON serialization.

    If there are values that json cannot serialize, this function will
    convert them to strings.

    Args:
        data (dict[str, Any]): Data to prepare.

    Returns:
        dict[str, Any]: Prepared data.

    Raises:
        TypeError: If the data cannot be converted to JSON.

    """
    prepared = {}
    for key, value in data.items():
        if isinstance(value, dict):
            value = prepare_for_json(value)
        try:
            json.dumps(value)
        except TypeError:
            value = value.as_posix() if issubclass(
                value.__class__, Path) else str(value)
        prepared[key] = value
    return prepared


class IntegrateTraits(pyblish.api.InstancePlugin):
    """Integrate representations with traits."""

    label = "Integrate Traits of an Asset"
    order = pyblish.api.IntegratorOrder
    log: "logging.Logger"

    def process(self, instance: pyblish.api.Instance) -> None:
        """Integrate representations with traits.

        Args:
            instance (pyblish.api.Instance): Instance to process.

        """
        # 1) skip farm and integrate ==  False

        if instance.data.get("integrate", True) is False:
            self.log.debug(f"Instance '{instance.name}' is marked to skip "
                           "integrating. Skipping")
            return

        if instance.data.get("farm"):
            self.log.debug(
                f"Instance '{instance.name}' is marked to be processed on "
                "farm. Skipping")
            return

        if not has_trait_representations(instance):
            self.log.debug(
                f"Instance '{instance.name}' has no representations with "
                "traits. Skipping")
            return

        # 2) filter representations based on LifeCycle traits
        set_trait_representations(
            instance,
            self.filter_lifecycle(get_trait_representations(instance))
        )

        representations: list[Representation] = get_trait_representations(
            instance
        )
        if not representations:
            self.log.debug(
                f"Instance '{instance.name}' has no persistent "
                "representations. Skipping")
            return

        op_session = OperationsSession()

        product_entity = self.prepare_product(instance, op_session)

        version_entity = self.prepare_version(
            instance, op_session, product_entity
        )
        instance.data["versionEntity"] = version_entity

        template = get_template_name(instance)

        transfers = get_transfers_from_representations(
            instance, template, representations)

        # 8) Transfer files
        file_transactions = FileTransaction(
            log=self.log,
            # Enforce unique transfers
            allow_queue_replacements=False)
        for transfer in transfers:
            self.log.debug(
                "Transferring file: %s -> %s",
                transfer.source,
                transfer.destination
            )
            file_transactions.add(
                transfer.source.as_posix(),
                transfer.destination.as_posix(),
                mode=FileTransaction.MODE_COPY,
            )
        file_transactions.process()
        self.log.debug(
            "Transferred files %s", [file_transactions.transferred])

        # replace original paths with the destination in traits.
        for transfer in transfers:
            transfer.related_trait.file_path = transfer.destination

        # 9) Create representation entities
        for representation in representations:
            attributes = {
                "path": transfers[0].destination,
                "template": transfers[0].template,
            }

            data = {"context": get_template_data_from_representation(
                representation, instance)}

            # Original integrator at this moment took all additional data
            # on the representation and added them into either attribs or data.
            # This should be avoided - we need to identify anything that
            # is broken by this and move it to traits. Representation
            # context in data is already handled by TemplateData trait, so
            # the line above and any usage should be removed in the future.

            representation_entity = new_representation_entity(
                representation.name,
                version_entity["id"],
                files=self._get_legacy_files_for_representation(
                    transfers,
                    representation,
                    anatomy=instance.context.data["anatomy"]),
                attribs=attributes,
                data=data,
                tags=[],
                status="",
            )
            # add traits to representation entity
            representation_entity["traits"] = representation.traits_as_dict()
            op_session.create_entity(
                project_name=instance.context.data["projectName"],
                entity_type="representation",
                data=prepare_for_json(representation_entity),
            )

        # 10) Commit the session to AYON
        self.log.debug(pformat(op_session.to_data()))
        op_session.commit()

        # 11) Pass the list of published representations to the instance
        # for further processing in Integrate Hero versions for example.
        instance.data["publishedRepresentationsWithTraits"] = representations

    @staticmethod
    def _get_relative_to_root_original_dirname(
            instance: pyblish.api.Instance) -> str:
        """Get path stripped of root of the original directory name.

        If `originalDirname` or `stagingDir` is set in instance data,
        this will return it as rootless path. The path must reside
        within the project directory.

        Returns:
            str: Relative path to the root of the project directory.

        Raises:
            PublishError: If the path is not within the project directory.

        """
        original_directory = (
                instance.data.get("originalDirname") or
                instance.data.get("stagingDir"))
        anatomy = instance.context.data["anatomy"]

        rootless = get_rootless_path(anatomy, original_directory)
        # this check works because _rootless will be the same as
        # original_directory if the original_directory cannot be transformed
        # to the rootless path.
        if rootless == original_directory:
            msg = (
                f"Destination path '{original_directory}' must "
                "be in project directory.")
            raise PublishError(msg)
        # the root is at the beginning - {root[work]}/rest/of/the/path
        relative_path_start = rootless.rfind("}") + 2
        return rootless[relative_path_start:]

        # 8) Transfer files
        # 9) Commit the session to AYON
        # 10) Finalize represetations - add integrated path Trait etc.

    @staticmethod
    def filter_lifecycle(
            representations: list[Representation]
    ) -> list[Representation]:
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
        product_base_type = instance.data.get("productBaseType")
        self.log.debug("Product: %s", product_name)

        # Get existing product if it exists
        existing_product_entity = get_product_by_name(
            project_name, product_name, folder_entity["id"]
        )

        # Define product data
        data = {"families": get_instance_families(instance)}
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

        new_product_entity_kwargs = {
            "name": product_name,
            "product_type": product_type,
            "folder_id": folder_entity["id"],
            "data": data,
            "attribs": attributes,
            "entity_id": product_id,
            "product_base_type": product_base_type,
        }

        if not is_product_base_type_supported():
            new_product_entity_kwargs.pop("product_base_type")
            if (
                    product_base_type is not None
                    and product_base_type != product_type):
                self.log.warning((
                    "Product base type %s is not supported by the server, "
                    "but it's defined - and it differs from product type %s. "
                    "Using product base type as product type."
                ), product_base_type, product_type)

                new_product_entity_kwargs["product_type"] = (
                    product_base_type
                )

        product_entity = new_product_entity(**new_product_entity_kwargs)

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
        all_version_data = get_version_data_from_instance(instance)
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

    def get_attributes_for_type(
            self,
            context: pyblish.api.Context,
            entity_type: str) -> dict:
        """Get AYON attributes for the given entity type.

        Args:
            context (pyblish.api.Context): Context to get attributes from.
            entity_type (str): Entity type to get attributes for.

        Returns:
            dict: AYON attributes for the given entity type.

        """
        return self.get_attributes_by_type(context)[entity_type]

    @staticmethod
    def get_attributes_by_type(
            context: pyblish.api.Context) -> dict:
        """Gets AYON attributes from the given context.

        Args:
            context (pyblish.api.Context): Context to get attributes from.

        Returns:
            dict: AYON attributes.

        """
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

    @staticmethod
    def _prepare_file_info(
            path: Path, anatomy: "Anatomy") -> dict[str, Any]:
        """Prepare information for one file (asset or resource).

        Arguments:
            path (Path): Destination url of published file.
            anatomy (Anatomy): Project anatomy part from instance.

        Raises:
            PublishError: If file does not exist.

        Returns:
            dict[str, Any]: Representation file info dictionary.

        """
        if not path.exists():
            msg = f"File '{path}' does not exist."
            raise PublishError(msg)

        return {
            "id": create_entity_id(),
            "name": path.name,
            "path": get_rootless_path(anatomy, path.as_posix()),
            "size": path.stat().st_size,
            "hash": source_hash(path.as_posix()),
            "hash_type": "op3",
        }

    def _get_legacy_files_for_representation(
            self,
            transfer_items: list[TransferItem],
            representation: Representation,
            anatomy: "Anatomy",
        ) -> list[dict[str, str]]:
        """Get legacy files for a given representation.

        This expects the file to exist - it must run after the transfer
        is done.

        Returns:
            list: List of legacy files.

        """
        selected: list[TransferItem] = []
        selected.extend(
            item
            for item in transfer_items
            if item.representation == representation
        )
        files: list[dict[str, str]] = []
        files.extend(
            self._prepare_file_info(item.destination, anatomy)
            for item in selected
        )
        return files
