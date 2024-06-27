# -*- coding: utf-8 -*-
"""Houdini specific Avalon/Pyblish plugin definitions."""
import sys
from abc import (
    ABCMeta
)
import six
import hou

import pyblish.api
from ayon_core.pipeline import (
    CreatorError,
    Creator,
    CreatedInstance,
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID,
    load,
    publish
)
from ayon_core.lib import BoolDef

from .lib import imprint, read, lsattr, add_self_publish_button


SETTINGS_CATEGORY = "houdini"


class HoudiniCreatorBase(object):
    @staticmethod
    def cache_instance_data(shared_data):
        """Cache instances for Creators to shared data.

        Create `houdini_cached_instances` key when needed in shared data and
        fill it with all collected instances from the scene under its
        respective creator identifiers.

        Create `houdini_cached_legacy_instance` key for any legacy instances
        detected in the scene as instances per family.

        Args:
            Dict[str, Any]: Shared data.

        """
        if shared_data.get("houdini_cached_instances") is None:
            cache = dict()
            cache_legacy = dict()

            nodes = []
            for id_type in [AYON_INSTANCE_ID, AVALON_INSTANCE_ID]:
                nodes.extend(lsattr("id", id_type))
            for node in nodes:

                creator_identifier_parm = node.parm("creator_identifier")
                if creator_identifier_parm:
                    # creator instance
                    creator_id = creator_identifier_parm.eval()
                    cache.setdefault(creator_id, []).append(node)

                else:
                    # legacy instance
                    family_parm = node.parm("family")
                    if not family_parm:
                        # must be a broken instance
                        continue

                    family = family_parm.eval()
                    cache_legacy.setdefault(family, []).append(node)

            shared_data["houdini_cached_instances"] = cache
            shared_data["houdini_cached_legacy_instance"] = cache_legacy

        return shared_data

    @staticmethod
    def create_instance_node(
        folder_path,
        node_name,
        parent,
        node_type="geometry",
        pre_create_data=None
    ):
        """Create node representing instance.

        Arguments:
            folder_path (str): Folder path.
            node_name (str): Name of the new node.
            parent (str): Name of the parent node.
            node_type (str, optional): Type of the node.
            pre_create_data (Optional[Dict]): Pre create data.

        Returns:
            hou.Node: Newly created instance node.

        """
        parent_node = hou.node(parent)
        instance_node = parent_node.createNode(
            node_type, node_name=node_name)
        instance_node.moveToGoodPosition()
        return instance_node


@six.add_metaclass(ABCMeta)
class HoudiniCreator(Creator, HoudiniCreatorBase):
    """Base class for most of the Houdini creator plugins."""
    selected_nodes = []
    settings_name = None
    add_publish_button = False

    settings_category = SETTINGS_CATEGORY

    def create(self, product_name, instance_data, pre_create_data):
        try:
            self.selected_nodes = []

            if pre_create_data.get("use_selection"):
                self.selected_nodes = hou.selectedNodes()

            # Get the node type and remove it from the data, not needed
            node_type = instance_data.pop("node_type", None)
            if node_type is None:
                node_type = "geometry"

            folder_path = instance_data["folderPath"]

            instance_node = self.create_instance_node(
                folder_path,
                product_name,
                "/out",
                node_type,
                pre_create_data
            )

            self.customize_node_look(instance_node)

            instance_data["instance_node"] = instance_node.path()
            instance_data["instance_id"] = instance_node.path()
            instance_data["families"] = self.get_publish_families()
            instance = CreatedInstance(
                self.product_type,
                product_name,
                instance_data,
                self)
            self._add_instance_to_context(instance)
            self.imprint(instance_node, instance.data_to_store())

            if self.add_publish_button:
                add_self_publish_button(instance_node)

            return instance

        except hou.Error as er:
            six.reraise(
                CreatorError,
                CreatorError("Creator error: {}".format(er)),
                sys.exc_info()[2])

    def lock_parameters(self, node, parameters):
        """Lock list of specified parameters on the node.

        Args:
            node (hou.Node): Houdini node to lock parameters on.
            parameters (list of str): List of parameter names.

        """
        for name in parameters:
            try:
                parm = node.parm(name)
                parm.lock(True)
            except AttributeError:
                self.log.debug("missing lock pattern {}".format(name))

    def collect_instances(self):
        # cache instances  if missing
        self.cache_instance_data(self.collection_shared_data)
        for instance in self.collection_shared_data[
                "houdini_cached_instances"].get(self.identifier, []):

            node_data = read(instance)

            # Node paths are always the full node path since that is unique
            # Because it's the node's path it's not written into attributes
            # but explicitly collected
            node_path = instance.path()
            node_data["instance_id"] = node_path
            node_data["instance_node"] = node_path
            node_data["families"] = self.get_publish_families()
            if "AYON_productName" in node_data:
                node_data["productName"] = node_data.pop("AYON_productName")

            created_instance = CreatedInstance.from_existing(
                node_data, self
            )
            self._add_instance_to_context(created_instance)

    def update_instances(self, update_list):
        for created_inst, changes in update_list:
            instance_node = hou.node(created_inst.get("instance_node"))
            new_values = {
                key: changes[key].new_value
                for key in changes.changed_keys
            }
            # Update parm templates and values
            self.imprint(
                instance_node,
                new_values,
                update=True
            )

    def imprint(self, node, values, update=False):
        # Never store instance node and instance id since that data comes
        # from the node's path
        if "productName" in values:
            values["AYON_productName"] = values.pop("productName")
        values.pop("instance_node", None)
        values.pop("instance_id", None)
        values.pop("families", None)
        imprint(node, values, update=update)

    def remove_instances(self, instances):
        """Remove specified instance from the scene.

        This is only removing `id` parameter so instance is no longer
        instance, because it might contain valuable data for artist.

        """
        for instance in instances:
            instance_node = hou.node(instance.data.get("instance_node"))
            if instance_node:
                instance_node.destroy()

            self._remove_instance_from_context(instance)

    def get_pre_create_attr_defs(self):
        return [
            BoolDef("use_selection", label="Use selection")
        ]

    @staticmethod
    def customize_node_look(
            node, color=None,
            shape="chevron_down"):
        """Set custom look for instance nodes.

        Args:
            node (hou.Node): Node to set look.
            color (hou.Color, Optional): Color of the node.
            shape (str, Optional): Shape name of the node.

        Returns:
            None

        """
        if not color:
            color = hou.Color((0.616, 0.871, 0.769))
        node.setUserData('nodeshape', shape)
        node.setColor(color)

    def get_publish_families(self):
        """Return families for the instances of this creator.

        Allow a Creator to define multiple families so that a creator can
        e.g. specify `usd` and `usdrop`.

        There is no need to override this method if you only have the
        primary family defined by the `product_type` property as that will
        always be set.

        Returns:
            List[str]: families for instances of this creator
        """
        return []

    def get_network_categories(self):
        """Return in which network view type this creator should show.

        The node type categories returned here will be used to define where
        the creator will show up in the TAB search for nodes in Houdini's
        Network View.

        This can be overridden in inherited classes to define where that
        particular Creator should be visible in the TAB search.

        Returns:
            list: List of houdini node type categories

        """
        return [hou.ropNodeTypeCategory()]

    def apply_settings(self, project_settings):
        """Method called on initialization of plugin to apply settings."""

        # Apply General Settings
        houdini_general_settings = project_settings["houdini"]["general"]
        self.add_publish_button = houdini_general_settings.get(
            "add_self_publish_button", False)

        # Apply Creator Settings
        settings_name = self.settings_name
        if settings_name is None:
            settings_name = self.__class__.__name__

        settings = project_settings["houdini"]["create"]
        settings = settings.get(settings_name)
        if settings is None:
            self.log.debug(
                "No settings found for {}".format(self.__class__.__name__)
            )
            return

        for key, value in settings.items():
            setattr(self, key, value)


class HoudiniLoader(load.LoaderPlugin):
    """Base class for Houdini load plugins."""

    hosts = ["houdini"]
    settings_category = SETTINGS_CATEGORY


class HoudiniInstancePlugin(pyblish.api.InstancePlugin):
    """Base class for Houdini instance publish plugins."""

    hosts = ["houdini"]
    settings_category = SETTINGS_CATEGORY


class HoudiniContextPlugin(pyblish.api.ContextPlugin):
    """Base class for Houdini context publish plugins."""

    hosts = ["houdini"]
    settings_category = SETTINGS_CATEGORY


class HoudiniExtractorPlugin(publish.Extractor):
    """Base class for Houdini extract plugins.

    Note:
        The `HoudiniExtractorPlugin` is a subclass of `publish.Extractor`,
            which in turn is a subclass of `pyblish.api.InstancePlugin`.
        Should there be a requirement to create an extractor that operates
            as a context plugin, it would be beneficial to incorporate
            the functionalities present in `publish.Extractor`.
    """

    hosts = ["houdini"]
    settings_category = SETTINGS_CATEGORY
