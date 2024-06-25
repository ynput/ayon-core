"""Shared functionality for pipeline plugins for Blender."""

import itertools
from pathlib import Path
from typing import Dict, List, Optional

import pyblish.api
import bpy

from ayon_core.pipeline import (
    Creator,
    CreatedInstance,
    LoaderPlugin,
    AVALON_INSTANCE_ID,
    AYON_INSTANCE_ID,
)
from ayon_core.pipeline.publish import Extractor
from ayon_core.lib import BoolDef

from .pipeline import (
    AVALON_CONTAINERS,
    AVALON_INSTANCES,
    AVALON_PROPERTY,
)
from .ops import (
    MainThreadItem,
    execute_in_main_thread
)
from .lib import imprint

VALID_EXTENSIONS = [".blend", ".json", ".abc", ".fbx",
                    ".usd", ".usdc", ".usda"]


def prepare_scene_name(
    folder_name: str, product_name: str, namespace: Optional[str] = None
) -> str:
    """Return a consistent name for an asset."""
    name = f"{folder_name}"
    if namespace:
        name = f"{name}_{namespace}"
    name = f"{name}_{product_name}"

    # Blender name for a collection or object cannot be longer than 63
    # characters. If the name is longer, it will raise an error.
    if len(name) > 63:
        raise ValueError(f"Scene name '{name}' would be too long.")

    return name


def get_unique_number(
    folder_name: str, product_name: str
) -> str:
    """Return a unique number based on the folder name."""
    avalon_container = bpy.data.collections.get(AVALON_CONTAINERS)
    if not avalon_container:
        return "01"
    # Check the names of both object and collection containers
    obj_asset_groups = avalon_container.objects
    obj_group_names = {
        c.name for c in obj_asset_groups
        if c.type == 'EMPTY' and c.get(AVALON_PROPERTY)}
    coll_asset_groups = avalon_container.children
    coll_group_names = {
        c.name for c in coll_asset_groups
        if c.get(AVALON_PROPERTY)}
    container_names = obj_group_names.union(coll_group_names)
    count = 1
    name = f"{folder_name}_{count:0>2}_{product_name}"
    while name in container_names:
        count += 1
        name = f"{folder_name}_{count:0>2}_{product_name}"
    return f"{count:0>2}"


def prepare_data(data, container_name=None):
    name = data.name
    local_data = data.make_local()
    if container_name:
        local_data.name = f"{container_name}:{name}"
    else:
        local_data.name = f"{name}"
    return local_data


def create_blender_context(active: Optional[bpy.types.Object] = None,
                           selected: Optional[bpy.types.Object] = None,
                           window: Optional[bpy.types.Window] = None):
    """Create a new Blender context. If an object is passed as
    parameter, it is set as selected and active.
    """

    if not isinstance(selected, list):
        selected = [selected]

    override_context = bpy.context.copy()

    windows = [window] if window else bpy.context.window_manager.windows

    for win in windows:
        for area in win.screen.areas:
            if area.type == 'VIEW_3D':
                for region in area.regions:
                    if region.type == 'WINDOW':
                        override_context['window'] = win
                        override_context['screen'] = win.screen
                        override_context['area'] = area
                        override_context['region'] = region
                        override_context['scene'] = bpy.context.scene
                        override_context['active_object'] = active
                        override_context['selected_objects'] = selected
                        return override_context
    raise Exception("Could not create a custom Blender context.")


def get_parent_collection(collection):
    """Get the parent of the input collection"""
    check_list = [bpy.context.scene.collection]

    for c in check_list:
        if collection.name in c.children.keys():
            return c
        check_list.extend(c.children)

    return None


def get_local_collection_with_name(name):
    for collection in bpy.data.collections:
        if collection.name == name and collection.library is None:
            return collection
    return None


def deselect_all():
    """Deselect all objects in the scene.

    Blender gives context error if trying to deselect object that it isn't
    in object mode.
    """
    modes = []
    active = bpy.context.view_layer.objects.active

    for obj in bpy.data.objects:
        if obj.mode != 'OBJECT':
            modes.append((obj, obj.mode))
            bpy.context.view_layer.objects.active = obj
            context_override = create_blender_context(active=obj)
            with bpy.context.temp_override(**context_override):
                bpy.ops.object.mode_set(mode='OBJECT')

    context_override = create_blender_context()
    with bpy.context.temp_override(**context_override):
        bpy.ops.object.select_all(action='DESELECT')

    for p in modes:
        bpy.context.view_layer.objects.active = p[0]
        context_override = create_blender_context(active=p[0])
        with bpy.context.temp_override(**context_override):
            bpy.ops.object.mode_set(mode=p[1])

    bpy.context.view_layer.objects.active = active


class BlenderInstancePlugin(pyblish.api.InstancePlugin):
    settings_category = "blender"


class BlenderContextPlugin(pyblish.api.ContextPlugin):
    settings_category = "blender"


class BlenderExtractor(Extractor):
    settings_category = "blender"


class BlenderCreator(Creator):
    """Base class for Blender Creator plug-ins."""
    defaults = ['Main']

    settings_category = "blender"
    create_as_asset_group = False

    @staticmethod
    def cache_instance_data(shared_data):
        """Cache instances for Creators shared data.

        Create `blender_cached_instances` key when needed in shared data and
        fill it with all collected instances from the scene under its
        respective creator identifiers.

        If legacy instances are detected in the scene, create
        `blender_cached_legacy_instances` key and fill it with
        all legacy products from this family as a value.  # key or value?

        Args:
            shared_data(Dict[str, Any]): Shared data.

        """
        if not shared_data.get('blender_cached_instances'):
            cache = {}
            cache_legacy = {}

            avalon_instances = bpy.data.collections.get(AVALON_INSTANCES)
            avalon_instance_objs = (
                avalon_instances.objects if avalon_instances else []
            )

            for obj_or_col in itertools.chain(
                    avalon_instance_objs,
                    bpy.data.collections
            ):
                avalon_prop = obj_or_col.get(AVALON_PROPERTY, {})
                if not avalon_prop:
                    continue

                if avalon_prop.get('id') not in {
                    AYON_INSTANCE_ID, AVALON_INSTANCE_ID
                }:
                    continue

                creator_id = avalon_prop.get('creator_identifier')
                if creator_id:
                    # Creator instance
                    cache.setdefault(creator_id, []).append(obj_or_col)
                else:
                    family = avalon_prop.get('family')
                    if family:
                        # Legacy creator instance
                        cache_legacy.setdefault(family, []).append(obj_or_col)

            shared_data["blender_cached_instances"] = cache
            shared_data["blender_cached_legacy_instances"] = cache_legacy

        return shared_data

    def create(
        self, product_name: str, instance_data: dict, pre_create_data: dict
    ):
        """Override abstract method from Creator.
        Create new instance and store it.

        Args:
            product_name (str): Product name of created instance.
            instance_data (dict): Instance base data.
            pre_create_data (dict): Data based on pre creation attributes.
                Those may affect how creator works.
        """
        # Get Instance Container or create it if it does not exist
        instances = bpy.data.collections.get(AVALON_INSTANCES)
        if not instances:
            instances = bpy.data.collections.new(name=AVALON_INSTANCES)
            bpy.context.scene.collection.children.link(instances)

        # Create asset group
        folder_name = instance_data["folderPath"].split("/")[-1]

        name = prepare_scene_name(folder_name, product_name)
        if self.create_as_asset_group:
            # Create instance as empty
            instance_node = bpy.data.objects.new(name=name, object_data=None)
            instance_node.empty_display_type = 'SINGLE_ARROW'
            instances.objects.link(instance_node)
        else:
            # Create instance collection
            instance_node = bpy.data.collections.new(name=name)
            instances.children.link(instance_node)

        self.set_instance_data(product_name, instance_data)

        instance = CreatedInstance(
            self.product_type, product_name, instance_data, self
        )
        instance.transient_data["instance_node"] = instance_node
        self._add_instance_to_context(instance)

        imprint(instance_node, instance_data)

        return instance_node

    def collect_instances(self):
        """Override abstract method from BlenderCreator.
        Collect existing instances related to this creator plugin."""

        # Cache instances in shared data
        self.cache_instance_data(self.collection_shared_data)

        # Get cached instances
        cached_instances = self.collection_shared_data.get(
            "blender_cached_instances"
        )
        if not cached_instances:
            return

        # Process only instances that were created by this creator
        for instance_node in cached_instances.get(self.identifier, []):
            property = instance_node.get(AVALON_PROPERTY)
            # Create instance object from existing data
            instance = CreatedInstance.from_existing(
                instance_data=property.to_dict(),
                creator=self
            )
            instance.transient_data["instance_node"] = instance_node

            # Add instance to create context
            self._add_instance_to_context(instance)

    def update_instances(self, update_list):
        """Override abstract method from BlenderCreator.
        Store changes of existing instances so they can be recollected.

        Args:
            update_list(List[UpdateData]): Changed instances
                and their changes, as a list of tuples.
        """

        for created_instance, changes in update_list:
            data = created_instance.data_to_store()
            node = created_instance.transient_data["instance_node"]
            if not node:
                # We can't update if we don't know the node
                self.log.error(
                    f"Unable to update instance {created_instance} "
                    f"without instance node."
                )
                return

            # Rename the instance node in the scene if product
            #   or folder changed.
            # Do not rename the instance if the family is workfile, as the
            # workfile instance is included in the AVALON_CONTAINER collection.
            if (
                "productName" in changes.changed_keys
                or "folderPath" in changes.changed_keys
            ) and created_instance.product_type != "workfile":
                folder_name = data["folderPath"].split("/")[-1]
                name = prepare_scene_name(
                    folder_name, data["productName"]
                )
                node.name = name

            imprint(node, data)

    def remove_instances(self, instances: List[CreatedInstance]):

        for instance in instances:
            node = instance.transient_data["instance_node"]

            if isinstance(node, bpy.types.Collection):
                for children in node.children_recursive:
                    if isinstance(children, bpy.types.Collection):
                        bpy.data.collections.remove(children)
                    else:
                        bpy.data.objects.remove(children)

                bpy.data.collections.remove(node)
            elif isinstance(node, bpy.types.Object):
                bpy.data.objects.remove(node)

            self._remove_instance_from_context(instance)

    def set_instance_data(
        self,
        product_name: str,
        instance_data: dict
    ):
        """Fill instance data with required items.

        Args:
            product_name(str): Product name of created instance.
            instance_data(dict): Instance base data.
            instance_node(bpy.types.ID): Instance node in blender scene.
        """
        if not instance_data:
            instance_data = {}

        instance_data.update(
            {
                "id": AVALON_INSTANCE_ID,
                "creator_identifier": self.identifier,
                "productName": product_name,
            }
        )

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection",
                    label="Use selection",
                    default=True)
        ]


class BlenderLoader(LoaderPlugin):
    """A basic AssetLoader for Blender

    This will implement the basic logic for linking/appending assets
    into another Blender scene.

    The `update` method should be implemented by a sub-class, because
    it's different for different types (e.g. model, rig, animation,
    etc.).
    """
    settings_category = "blender"

    @staticmethod
    def _get_instance_empty(instance_name: str, nodes: List) -> Optional[bpy.types.Object]:
        """Get the 'instance empty' that holds the collection instance."""
        for node in nodes:
            if not isinstance(node, bpy.types.Object):
                continue
            if (node.type == 'EMPTY' and node.instance_type == 'COLLECTION'
                    and node.instance_collection and node.name == instance_name):
                return node
        return None

    @staticmethod
    def _get_instance_collection(instance_name: str, nodes: List) -> Optional[bpy.types.Collection]:
        """Get the 'instance collection' (container) for this asset."""
        for node in nodes:
            if not isinstance(node, bpy.types.Collection):
                continue
            if node.name == instance_name:
                return node
        return None

    @staticmethod
    def _get_library_from_container(container: bpy.types.Collection) -> bpy.types.Library:
        """Find the library file from the container.

        It traverses the objects from this collection, checks if there is only
        1 library from which the objects come from and returns the library.

        Warning:
            No nested collections are supported at the moment!
        """
        assert not container.children, "Nested collections are not supported."
        assert container.objects, "The collection doesn't contain any objects."
        libraries = set()
        for obj in container.objects:
            assert obj.library, f"'{obj.name}' is not linked."
            libraries.add(obj.library)

        assert len(
            libraries) == 1, "'{container.name}' contains objects from more then 1 library."

        return list(libraries)[0]

    def process_asset(self,
                      context: dict,
                      name: str,
                      namespace: Optional[str] = None,
                      options: Optional[Dict] = None):
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def load(self,
             context: dict,
             name: Optional[str] = None,
             namespace: Optional[str] = None,
             options: Optional[Dict] = None) -> Optional[bpy.types.Collection]:
        """ Run the loader on Blender main thread"""
        mti = MainThreadItem(self._load, context, name, namespace, options)
        execute_in_main_thread(mti)

    def _load(self,
              context: dict,
              name: Optional[str] = None,
              namespace: Optional[str] = None,
              options: Optional[Dict] = None
    ) -> Optional[bpy.types.Collection]:
        """Load asset via database

        Arguments:
            context: Full parenthood of representation to load
            name: Use pre-defined name
            namespace: Use pre-defined namespace
            options: Additional settings dictionary
        """
        # TODO: make it possible to add the asset several times by
        # just re-using the collection
        filepath = self.filepath_from_context(context)
        assert Path(filepath).exists(), f"{filepath} doesn't exist."

        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]
        unique_number = get_unique_number(
            folder_name, product_name
        )
        namespace = namespace or f"{folder_name}_{unique_number}"
        name = name or prepare_scene_name(
            folder_name, product_name, unique_number
        )

        nodes = self.process_asset(
            context=context,
            name=name,
            namespace=namespace,
            options=options,
        )

        # Only containerise if anything was loaded by the Loader.
        if not nodes:
            return None

        # Only containerise if it's not already a collection from a .blend file.
        # representation = context["representation"]["name"]
        # if representation != "blend":
        #     from ayon_blender.api.pipeline import containerise
        #     return containerise(
        #         name=name,
        #         namespace=namespace,
        #         nodes=nodes,
        #         context=context,
        #         loader=self.__class__.__name__,
        #     )

        # folder_name = context["folder"]["name"]
        # product_name = context["product"]["name"]
        # instance_name = prepare_scene_name(
        #     folder_name, product_name, unique_number
        # ) + '_CON'

        # return self._get_instance_collection(instance_name, nodes)

    def exec_update(self, container: Dict, context: Dict):
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def update(self, container: Dict, context: Dict):
        """ Run the update on Blender main thread"""
        mti = MainThreadItem(self.exec_update, container, context)
        execute_in_main_thread(mti)

    def exec_remove(self, container: Dict) -> bool:
        """Must be implemented by a sub-class"""
        raise NotImplementedError("Must be implemented by a sub-class")

    def remove(self, container: Dict) -> bool:
        """ Run the remove on Blender main thread"""
        mti = MainThreadItem(self.exec_remove, container)
        execute_in_main_thread(mti)
