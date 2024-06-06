import json
from pathlib import Path

import unreal
from unreal import EditorLevelLibrary
import ayon_api

from ayon_core.pipeline import (
    discover_loader_plugins,
    loaders_from_representation,
    load_container,
    get_representation_path,
    AYON_CONTAINER_ID,
)
from ayon_unreal.api import plugin
from ayon_unreal.api import pipeline as upipeline


class ExistingLayoutLoader(plugin.Loader):
    """
    Load Layout for an existing scene, and match the existing assets.
    """

    product_types = {"layout"}
    representations = {"json"}

    label = "Load Layout on Existing Scene"
    icon = "code-fork"
    color = "orange"
    ASSET_ROOT = "/Game/Ayon"

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
    def _create_container(
        asset_name,
        asset_dir,
        folder_path,
        representation,
        version_id,
        product_type
    ):
        container_name = f"{asset_name}_CON"

        if not unreal.EditorAssetLibrary.does_asset_exist(
            f"{asset_dir}/{container_name}"
        ):
            container = upipeline.create_container(container_name, asset_dir)
        else:
            ar = unreal.AssetRegistryHelpers.get_asset_registry()
            obj = ar.get_asset_by_object_path(
                f"{asset_dir}/{container_name}.{container_name}")
            container = obj.get_asset()

        data = {
            "schema": "ayon:container-2.0",
            "id": AYON_CONTAINER_ID,
            "folder_path": folder_path,
            "namespace": asset_dir,
            "container_name": container_name,
            "asset_name": asset_name,
            # "loader": str(self.__class__.__name__),
            "representation": representation,
            "parent": version_id,
            "product_type": product_type,
            # TODO these shold be probably removed
            "asset": folder_path,
            "family": product_type,
        }

        upipeline.imprint(
            "{}/{}".format(asset_dir, container_name), data)

        return container.get_path_name()

    @staticmethod
    def _get_current_level():
        ue_version = unreal.SystemLibrary.get_engine_version().split('.')
        ue_major = ue_version[0]

        if ue_major == '4':
            return EditorLevelLibrary.get_editor_world()
        elif ue_major == '5':
            return unreal.LevelEditorSubsystem().get_current_level()

        raise NotImplementedError(
            f"Unreal version {ue_major} not supported")

    def _transform_from_basis(self, transform, basis):
        """Transform a transform from a basis to a new basis."""
        # Get the basis matrix
        basis_matrix = unreal.Matrix(
            basis[0],
            basis[1],
            basis[2],
            basis[3]
        )
        transform_matrix = unreal.Matrix(
            transform[0],
            transform[1],
            transform[2],
            transform[3]
        )

        new_transform = (
            basis_matrix.get_inverse() * transform_matrix * basis_matrix)

        return new_transform.transform()

    def _spawn_actor(self, obj, lasset):
        actor = EditorLevelLibrary.spawn_actor_from_object(
            obj, unreal.Vector(0.0, 0.0, 0.0)
        )

        actor.set_actor_label(lasset.get('instance_name'))

        transform = lasset.get('transform_matrix')
        basis = lasset.get('basis')

        computed_transform = self._transform_from_basis(transform, basis)

        actor.set_actor_transform(computed_transform, False, True)

    @staticmethod
    def _get_fbx_loader(loaders, family):
        name = ""
        if family == 'rig':
            name = "SkeletalMeshFBXLoader"
        elif family == 'model' or family == 'staticMesh':
            name = "StaticMeshFBXLoader"
        elif family == 'camera':
            name = "CameraLoader"

        if name == "":
            return None

        for loader in loaders:
            if loader.__name__ == name:
                return loader

        return None

    @staticmethod
    def _get_abc_loader(loaders, family):
        name = ""
        if family == 'rig':
            name = "SkeletalMeshAlembicLoader"
        elif family == 'model':
            name = "StaticMeshAlembicLoader"

        if name == "":
            return None

        for loader in loaders:
            if loader.__name__ == name:
                return loader

        return None

    def _load_asset(self, repr_data, representation, instance_name, family):
        repr_format = repr_data.get('name')

        all_loaders = discover_loader_plugins()
        loaders = loaders_from_representation(
            all_loaders, representation)

        loader = None

        if repr_format == 'fbx':
            loader = self._get_fbx_loader(loaders, family)
        elif repr_format == 'abc':
            loader = self._get_abc_loader(loaders, family)

        if not loader:
            self.log.error(f"No valid loader found for {representation}")
            return []

        # This option is necessary to avoid importing the assets with a
        # different conversion compared to the other assets. For ABC files,
        # it is in fact impossible to access the conversion settings. So,
        # we must assume that the Maya conversion settings have been applied.
        options = {
            "default_conversion": True
        }

        assets = load_container(
            loader,
            representation,
            namespace=instance_name,
            options=options
        )

        return assets

    def _get_valid_repre_entities(self, project_name, version_ids):
        valid_formats = ['fbx', 'abc']

        repre_entities = list(ayon_api.get_representations(
            project_name,
            representation_names=valid_formats,
            version_ids=version_ids
        ))
        repre_entities_by_version_id = {}
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            repre_entities_by_version_id[version_id] = repre_entity
        return repre_entities_by_version_id

    def _process(self, lib_path, project_name):
        ar = unreal.AssetRegistryHelpers.get_asset_registry()

        actors = EditorLevelLibrary.get_all_level_actors()

        with open(lib_path, "r") as fp:
            data = json.load(fp)

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

        # Prequery valid repre documents for all elements at once
        valid_repre_entities_by_version_id = self._get_valid_repre_entities(
            project_name, version_ids)
        containers = []
        actors_matched = []

        for (repre_entity, lasset) in layout_data:
            # For every actor in the scene, check if it has a representation in
            # those we got from the JSON. If so, create a container for it.
            # Otherwise, remove it from the scene.
            found = False
            repre_id = repre_entity["id"]
            repre_parents = repre_parents_by_id[repre_id]
            folder_path = repre_parents.folder["path"]
            folder_name = repre_parents.folder["name"]
            product_name = repre_parents.product["name"]
            product_type = repre_parents.product["productType"]

            for actor in actors:
                if not actor.get_class().get_name() == 'StaticMeshActor':
                    continue
                if actor in actors_matched:
                    continue

                # Get the original path of the file from which the asset has
                # been imported.
                smc = actor.get_editor_property('static_mesh_component')
                mesh = smc.get_editor_property('static_mesh')
                import_data = mesh.get_editor_property('asset_import_data')
                filename = import_data.get_first_filename()
                path = Path(filename)

                if (not path.name or
                        path.name not in repre_entity["attrib"]["path"]):
                    continue

                actor.set_actor_label(lasset.get('instance_name'))

                mesh_path = Path(mesh.get_path_name()).parent.as_posix()

                # Create the container for the asset.
                container = self._create_container(
                    f"{folder_name}_{product_name}",
                    mesh_path,
                    folder_path,
                    repre_entity["id"],
                    repre_entity["versionId"],
                    product_type
                )
                containers.append(container)

                # Set the transform for the actor.
                transform = lasset.get('transform_matrix')
                basis = lasset.get('basis')

                computed_transform = self._transform_from_basis(
                    transform, basis)
                actor.set_actor_transform(computed_transform, False, True)

                actors_matched.append(actor)
                found = True
                break

            # If an actor has not been found for this representation,
            # we check if it has been loaded already by checking all the
            # loaded containers. If so, we add it to the scene. Otherwise,
            # we load it.
            if found:
                continue

            all_containers = upipeline.ls()

            loaded = False

            for container in all_containers:
                repre_id = container.get('representation')

                if not repre_id == repre_entity["id"]:
                    continue

                asset_dir = container.get('namespace')

                arfilter = unreal.ARFilter(
                    class_names=["StaticMesh"],
                    package_paths=[asset_dir],
                    recursive_paths=False)
                assets = ar.get_assets(arfilter)

                for asset in assets:
                    obj = asset.get_asset()
                    self._spawn_actor(obj, lasset)

                loaded = True
                break

            # If the asset has not been loaded yet, we load it.
            if loaded:
                continue

            version_id = lasset.get('version')
            assets = self._load_asset(
                valid_repre_entities_by_version_id.get(version_id),
                lasset.get('representation'),
                lasset.get('instance_name'),
                lasset.get('family')
            )

            for asset in assets:
                obj = ar.get_asset_by_object_path(asset).get_asset()
                if not obj.get_class().get_name() == 'StaticMesh':
                    continue
                self._spawn_actor(obj, lasset)

                break

        # Check if an actor was not matched to a representation.
        # If so, remove it from the scene.
        for actor in actors:
            if not actor.get_class().get_name() == 'StaticMeshActor':
                continue
            if actor not in actors_matched:
                self.log.warning(f"Actor {actor.get_name()} not matched.")
                if self.delete_unmatched_assets:
                    EditorLevelLibrary.destroy_actor(actor)

        return containers

    def load(self, context, name, namespace, options):
        print("Loading Layout and Match Assets")

        folder_name = context["folder"]["name"]
        folder_path = context["folder"]["path"]
        product_type = context["product"]["productType"]
        asset_name = f"{folder_name}_{name}" if folder_name else name
        container_name = f"{folder_name}_{name}_CON"

        curr_level = self._get_current_level()

        if not curr_level:
            raise AssertionError("Current level not saved")

        project_name = context["project"]["name"]
        path = self.filepath_from_context(context)
        containers = self._process(path, project_name)

        curr_level_path = Path(
            curr_level.get_outer().get_path_name()).parent.as_posix()

        if not unreal.EditorAssetLibrary.does_asset_exist(
            f"{curr_level_path}/{container_name}"
        ):
            upipeline.create_container(
                container=container_name, path=curr_level_path)

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
        upipeline.imprint(f"{curr_level_path}/{container_name}", data)

    def update(self, container, context):
        asset_dir = container.get('namespace')

        project_name = context["project"]["name"]
        repre_entity = context["representation"]

        source_path = get_representation_path(repre_entity)
        containers = self._process(source_path, project_name)

        data = {
            "representation": repre_entity["id"],
            "loaded_assets": containers,
            "parent": repre_entity["versionId"],
        }
        upipeline.imprint(
            "{}/{}".format(asset_dir, container.get('container_name')), data)
