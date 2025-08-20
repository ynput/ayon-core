import logging

from ayon_core.pipeline.plugin_discover import (
    discover,
    register_plugin,
    register_plugin_path,
    deregister_plugin,
    deregister_plugin_path
)
from ayon_core.pipeline.load.utils import get_representation_path_from_context


class InventoryAction:
    """A custom action for the scene inventory tool

    If registered the action will be visible in the Right Mouse Button menu
    under the submenu "Actions".

    """

    label = None
    icon = None
    color = None
    order = 0

    log = logging.getLogger("InventoryAction")
    log.propagate = True

    @staticmethod
    def is_compatible(container):
        """Override function in a custom class

        This method is specifically used to ensure the action can operate on
        the container.

        Args:
            container(dict): the data of a loaded asset, see host.ls()

        Returns:
            bool
        """
        return bool(container.get("objectName"))

    def process(self, containers):
        """Override function in a custom class

        This method will receive all containers even those which are
        incompatible. It is advised to create a small filter along the lines
        of this example:

        valid_containers = filter(self.is_compatible(c) for c in containers)

        The return value will need to be a True-ish value to trigger
        the data_changed signal in order to refresh the view.

        You can return a list of container names to trigger GUI to select
        treeview items.

        You can return a dict to carry extra GUI options. For example:
            {
                "objectNames": [container names...],
                "options": {"mode": "toggle",
                            "clear": False}
            }
        Currently workable GUI options are:
            - clear (bool): Clear current selection before selecting by action.
                            Default `True`.
            - mode (str): selection mode, use one of these:
                          "select", "deselect", "toggle". Default is "select".

        Args:
            containers (list): list of dictionaries

        Return:
            bool, list or dict

        """
        return True

    @classmethod
    def filepath_from_context(cls, context):
        return get_representation_path_from_context(context)


def discover_inventory_actions():
    actions = discover(InventoryAction)
    filtered_actions = []
    for action in actions:
        if action is not InventoryAction:
            filtered_actions.append(action)

    return filtered_actions


def register_inventory_action(plugin):
    return register_plugin(InventoryAction, plugin)


def deregister_inventory_action(plugin):
    deregister_plugin(InventoryAction, plugin)


def register_inventory_action_path(path):
    return register_plugin_path(InventoryAction, path)


def deregister_inventory_action_path(path):
    return deregister_plugin_path(InventoryAction, path)
