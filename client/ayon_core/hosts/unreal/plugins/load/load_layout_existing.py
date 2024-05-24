# -*- coding: utf-8 -*-
"""Loader for apply layout to already existing assets."""
import json
from pathlib import Path
import ayon_api

from ayon_core.pipeline import (
    discover_loader_plugins,
    loaders_from_representation,
    load_container,
    get_representation_path,
    AYON_CONTAINER_ID,
)
from ayon_core.hosts.unreal.api.plugin import UnrealBaseLoader
from ayon_core.hosts.unreal.api.pipeline import (
    send_request,
    containerise,
)


class ExistingLayoutLoader(UnrealBaseLoader):
    """
    Load Layout for an existing scene, and match the existing assets.
    """

    product_types = {"layout"}
    representations = {"json"}

    label = "Load Layout on Existing Scene"
    icon = "code-fork"
    color = "orange"

    delete_unmatched_assets = True

    @classmethod
    def apply_settings(cls, project_settings):
        super(ExistingLayoutLoader, cls).apply_settings(
            project_settings
        )
        cls.delete_unmatched_assets = (
            project_settings["unreal"]["delete_unmatched_assets"]
        )

    @staticmethod
    def _get_fbx_loader(loaders, family):
        name = ""
        if family == 'camera':
            name = "CameraLoader"
        elif family == 'model':
            name = "StaticMeshFBXLoader"
        elif family == 'rig':
            name = "SkeletalMeshFBXLoader"
        return (
            next(
                (
                    loader for loader in loaders if loader.__name__ == name
                ),
                None
            )
            if name
            else None
        )

    @staticmethod
    def _get_abc_loader(loaders, family):
        name = ""
        if family == 'model':
            name = "StaticMeshAlembicLoader"
        elif family == 'rig':
            name = "SkeletalMeshAlembicLoader"
        return (
            next(
                (
                    loader for loader in loaders if loader.__name__ == name
                ),
                None
            )
            if name
            else None
        )

    def _get_representation(self, element, repre_entities_by_version_id):
        representation = None
        repr_format = None
        if element.get('representation'):
            version_id = element.get("version")
            repre_entities = repre_entities_by_version_id[version_id]
            if not repre_entities:
                self.log.error(
                    f"No valid representation found for version "
                    f"{version_id}")
                return None, None
            repre_entity = repre_entities[0]
            representation = str(repre_entity["_id"])
            repr_format = repre_entity["name"]

        # This is to keep compatibility with old versions of the
        # json format.
        elif element.get('reference_fbx'):
            representation = element.get('reference_fbx')
            repr_format = 'fbx'
        elif element.get('reference_abc'):
            representation = element.get('reference_abc')
            repr_format = 'abc'

        return representation, repr_format

    def _load_representation(
        self, family, representation, repr_format, instance_name, all_loaders
    ):
        loaders = loaders_from_representation(
            all_loaders, representation)

        loader = None

        if repr_format == 'fbx':
            loader = self._get_fbx_loader(loaders, family)
        elif repr_format == 'abc':
            loader = self._get_abc_loader(loaders, family)

        if not loader:
            self.log.error(
                f"No valid loader found for {representation}")
            return []

        return load_container(loader, representation, namespace=instance_name)

    @staticmethod
    def _get_valid_repre_entities(project_name, version_ids):
        valid_formats = ['fbx', 'abc']

        repre_entities = list(ayon_api.get_representations(
            project_name,
            representation_names=valid_formats,
            version_ids=version_ids
        ))

        return {
            str(repre_entity["parent"]):
                repre_entity for repre_entity in repre_entities}

    @staticmethod
    def _get_layout_data(data, project_name):
        elements = []
        repre_ids = set()
        # Get all the representations in the JSON from the database.
        for element in data:
            repre_id = element.get('representation')
            if repre_id:
                repre_ids.add(repre_id)
                elements.append(element)

        repre_entities = ayon_api.get_representations(
            project_name, representation_ids=repre_ids
        )
        repre_entities_by_id = {
            repre_entity["id"]: repre_entity
            for repre_entity in repre_entities
        }
        layout_data = []
        version_ids = set()
        for element in elements:
            repre_id = element.get("representation")
            repre_entity = repre_entities_by_id.get(repre_id)
            if not repre_entity:
                raise AssertionError("Representation not found")
            if not (
                repre_entity.get("attrib")
                or repre_entity["attrib"].get("path")
            ):
                raise AssertionError("Representation does not have path")
            if not repre_entity.get('context'):
                raise AssertionError("Representation does not have context")

            layout_data.append((repre_entity, element))
            version_ids.add(repre_entity["versionId"])

        repre_parents_by_id = ayon_api.get_representation_parents(
            project_name, repre_entities_by_id.keys()
        )

        return layout_data, version_ids, repre_parents_by_id

    def _process(self, lib_path, project_name):
        with open(lib_path, "r") as fp:
            data = json.load(fp)

        all_loaders = discover_loader_plugins()

        layout_data, version_ids, repre_parents_by_id = (
            self._get_layout_data(data, project_name))

        # Prequery valid repre documents for all elements at once
        valid_repre_doc_by_version_id = self._get_valid_repre_entities(
            project_name, version_ids)

        containers = []
        actors_matched = []

        for (repre_entity, lasset) in layout_data:
            # For every actor in the scene, check if it has a representation
            # in those we got from the JSON. If so, create a container for it.
            # Otherwise, remove it from the scene.

            matched, mesh_path = send_request(
                "match_actor",
                params={
                    "actors_matched": actors_matched,
                    "lasset": lasset,
                    "repr_data": repre_entity})

            # If an actor has not been found for this representation,
            # we check if it has been loaded already by checking all the
            # loaded containers. If so, we add it to the scene. Otherwise,
            # we load it.
            if matched:
                repre_id = repre_entity["id"]
                repre_parents = repre_parents_by_id[repre_id]
                folder_path = repre_parents.folder["path"]
                folder_name = repre_parents.folder["name"]
                product_name = repre_parents.product["name"]
                product_type = repre_parents.product["productType"]

                container = self._create_container(
                    f"{folder_name}_{product_name}",
                    mesh_path,
                    folder_path,
                    repre_entity["id"],
                    repre_entity["versionId"],
                    product_type
                )
                containers.append(container)

                continue

            loaded = send_request(
                "spawn_existing_actors",
                params={
                    "repre_entity": repre_entity,
                    "lasset": lasset})

            if loaded:
                # The asset was already loaded, and we spawned it in the scene,
                # so we can continue.
                continue

            # If we get here, it means that the asset was not loaded yet,
            # so we load it and spawn it in the scene.
            representation, repr_format = self._get_representation(
                lasset, valid_repre_doc_by_version_id)

            family = lasset.get('family')
            instance_name = lasset.get('instance_name')

            assets = self._load_representation(
                family, representation, repr_format, instance_name,
                all_loaders)

            send_request(
                "spawn_actors",
                params={
                    "assets": assets, "lasset": lasset})

        # Remove not matched actors, if the option is set.
        if self.delete_unmatched_assets:
            send_request(
                "remove_unmatched_actors",
                params={"actors_matched": actors_matched})

        return containers

    def load(self, context, name, namespace, options):
        """Load and containerise representation into Content Browser.

        Load and apply layout to already existing assets in Unreal.
        It will create a container for each asset in the scene, and a
        container for the layout.

        Args:
            context (dict): application context
            name (str): subset name
            namespace (str): in Unreal this is basically path to container.
                             This is not passed here, so namespace is set
                             by `containerise()` because only then we know
                             real path.
            options (dict): Those would be data to be imprinted. This is not
                            used now, data are imprinted by `containerise()`.
        """
        folder_name = context["folder"]["name"]
        folder_path = context["folder"]["path"]
        product_type = context["product"]["productType"]
        asset_name = f"{folder_name}_{name}" if folder_name else name
        container_name = f"{folder_name}_{name}_CON"

        curr_level = send_request("get_current_level")

        if not curr_level:
            raise AssertionError("Current level not saved")

        project_name = context["project"]["name"]
        path = self.filepath_from_context(context)
        containers = self._process(path, project_name)

        curr_level_path = Path(curr_level).parent.as_posix()

        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "folder_path": folder_path,
            "namespace": curr_level_path,
            "container_name": container_name,
            "asset_name": asset_name,
            "loader": str(self.__class__.__name__),
            "representation": context["representation"]["id"],
            "parent": context["representation"]["versionId"],
            "product_type": product_type,
            "loaded_assets": containers,
            # TODO these shold be probably removed
            "asset": folder_path,
            "family": product_type,
        }

        containerise(curr_level_path, container_name, data)

    def update(self, container, context):
        asset_dir = container.get('namespace')
        container_name = container['objectName']

        project_name = context["project"]["name"]
        repre_entity = context["representation"]

        source_path = get_representation_path(repre_entity)
        containers = self._process(source_path, project_name)

        data = {
            "representation": repre_entity["id"],
            "loaded_assets": containers,
            "parent": repre_entity["versionId"],
        }

        containerise(asset_dir, container_name, data)
