"""Create workflow moved from avalon-core repository.

Renamed classes and functions
- 'Creator' -> 'LegacyCreator'
- 'create'  -> 'legacy_create'
"""

import os
import logging
import collections

from ayon_core.pipeline.constants import AVALON_INSTANCE_ID

from .product_name import get_product_name


class LegacyCreator(object):
    """Determine how assets are created"""
    label = None
    product_type = None
    defaults = None
    maintain_selection = True
    enabled = True

    dynamic_product_name_keys = []

    log = logging.getLogger("LegacyCreator")
    log.propagate = True

    def __init__(self, name, folder_path, options=None, data=None):
        self.name = name  # For backwards compatibility
        self.options = options

        # Default data
        self.data = collections.OrderedDict()
        # TODO use 'AYON_INSTANCE_ID' when all hosts support it
        self.data["id"] = AVALON_INSTANCE_ID
        self.data["productType"] = self.product_type
        self.data["folderPath"] = folder_path
        self.data["productName"] = name
        self.data["active"] = True

        self.data.update(data or {})

    @classmethod
    def apply_settings(cls, project_settings):
        """Apply AYON settings to a plugin class."""

        host_name = os.environ.get("AYON_HOST_NAME")
        plugin_type = "create"
        plugin_type_settings = (
            project_settings
            .get(host_name, {})
            .get(plugin_type, {})
        )
        global_type_settings = (
            project_settings
            .get("core", {})
            .get(plugin_type, {})
        )
        if not global_type_settings and not plugin_type_settings:
            return

        plugin_name = cls.__name__

        plugin_settings = None
        # Look for plugin settings in host specific settings
        if plugin_name in plugin_type_settings:
            plugin_settings = plugin_type_settings[plugin_name]

        # Look for plugin settings in global settings
        elif plugin_name in global_type_settings:
            plugin_settings = global_type_settings[plugin_name]

        if not plugin_settings:
            return

        cls.log.debug(">>> We have preset for {}".format(plugin_name))
        for option, value in plugin_settings.items():
            if option == "enabled" and value is False:
                cls.log.debug("  - is disabled by preset")
            else:
                cls.log.debug("  - setting `{}`: `{}`".format(option, value))
            setattr(cls, option, value)

    def process(self):
        pass

    @classmethod
    def get_dynamic_data(
        cls, project_name, folder_entity, task_entity, variant, host_name
    ):
        """Return dynamic data for current Creator plugin.

        By default return keys from `dynamic_product_name_keys` attribute
        as mapping to keep formatted template unchanged.

        ```
        dynamic_product_name_keys = ["my_key"]
        ---
        output = {
            "my_key": "{my_key}"
        }
        ```

        Dynamic keys may override default Creator keys (productType, task,
        folderPath, ...) but do it wisely if you need.

        All of keys will be converted into 3 variants unchanged, capitalized
        and all upper letters. Because of that are all keys lowered.

        This method can be modified to prefill some values just keep in mind it
        is class method.

        Returns:
            dict: Fill data for product name template.
        """
        dynamic_data = {}
        for key in cls.dynamic_product_name_keys:
            key = key.lower()
            dynamic_data[key] = "{" + key + "}"
        return dynamic_data

    @classmethod
    def get_product_name(
        cls, project_name, folder_entity, task_entity, variant, host_name=None
    ):
        """Return product name created with entered arguments.

        Logic extracted from Creator tool. This method should give ability
        to get product name without the tool.

        TODO: Maybe change `variant` variable.

        By default is output concatenated product type with variant.

        Args:
            project_name (str): Context's project name.
            folder_entity (dict[str, Any]): Folder entity.
            task_entity (dict[str, Any]): Task entity.
            variant (str): What is entered by user in creator tool.
            host_name (str): Name of host.

        Returns:
            str: Formatted product name with entered arguments. Should match
                config's logic.
        """

        dynamic_data = cls.get_dynamic_data(
            project_name, folder_entity, task_entity, variant, host_name
        )
        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]
        return get_product_name(
            project_name,
            task_name,
            task_type,
            host_name,
            cls.product_type,
            variant,
            dynamic_data=dynamic_data
        )


def legacy_create(
    Creator, product_name, folder_path, options=None, data=None
):
    """Create a new instance

    Associate nodes with a product name and type. These nodes are later
    validated, according to their `product type`, and integrated into the
    shared environment, relative their `productName`.

    Data relative each product type, along with default data, are imprinted
    into the resulting objectSet. This data is later used by extractors
    and finally asset browsers to help identify the origin of the asset.

    Arguments:
        Creator (Creator): Class of creator.
        product_name (str): Name of product.
        folder_path (str): Folder path.
        options (dict, optional): Additional options from GUI.
        data (dict, optional): Additional data from GUI.

    Raises:
        NameError on `productName` already exists
        KeyError on invalid dynamic property
        RuntimeError on host error

    Returns:
        Name of instance

    """
    from ayon_core.pipeline import registered_host

    host = registered_host()
    plugin = Creator(product_name, folder_path, options, data)

    if plugin.maintain_selection is True:
        with host.maintained_selection():
            print("Running %s with maintained selection" % plugin)
            instance = plugin.process()
        return instance

    print("Running %s" % plugin)
    instance = plugin.process()
    return instance
