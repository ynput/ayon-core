import logging
import warnings

import ayon_api

from ayon_core.pipeline.plugin_discover import (
    discover,
    register_plugin,
    register_plugin_path,
    deregister_plugin,
    deregister_plugin_path
)

from .load.utils import get_representation_path_from_context


class LauncherActionSelection:
    """Object helper to pass selection to actions.

    Object support backwards compatibility for 'session' from OpenPype where
    environment variable keys were used to define selection.

    Args:
        project_name (str): Selected project name.
        folder_id (str): Selected folder id.
        task_id (str): Selected task id.
        folder_path (Optional[str]): Selected folder path.
        task_name (Optional[str]): Selected task name.
        project_entity (Optional[dict[str, Any]]): Project entity.
        folder_entity (Optional[dict[str, Any]]): Folder entity.
        task_entity (Optional[dict[str, Any]]): Task entity.

    """
    def __init__(
        self,
        project_name,
        folder_id,
        task_id,
        folder_path=None,
        task_name=None,
        project_entity=None,
        folder_entity=None,
        task_entity=None
    ):
        self._project_name = project_name
        self._folder_id = folder_id
        self._task_id = task_id

        self._folder_path = folder_path
        self._task_name = task_name

        self._project_entity = project_entity
        self._folder_entity = folder_entity
        self._task_entity = task_entity

    def __getitem__(self, key):
        warnings.warn(
            (
                "Using deprecated access to selection data. Please use"
                " attributes and methods"
                " defined by 'LauncherActionSelection'."
            ),
            category=DeprecationWarning
        )
        if key in {"AYON_PROJECT_NAME", "AVALON_PROJECT"}:
            return self.project_name
        if key in {"AYON_FOLDER_PATH", "AVALON_ASSET"}:
            return self.folder_path
        if key in {"AYON_TASK_NAME", "AVALON_TASK"}:
            return self.task_name
        raise KeyError(f"Key: {key} not found")

    def __iter__(self):
        for key in self.keys():
            yield key

    def __contains__(self, key):
        warnings.warn(
            (
                "Using deprecated access to selection data. Please use"
                " attributes and methods"
                " defined by 'LauncherActionSelection'."
            ),
            category=DeprecationWarning
        )
        # Fake missing keys check for backwards compatibility
        if key in {
            "AYON_PROJECT_NAME",
            "AVALON_PROJECT",
        }:
            return self._project_name is not None
        if key in {
            "AYON_FOLDER_PATH",
            "AVALON_ASSET",
        }:
            return self._folder_id is not None
        if key in {
            "AYON_TASK_NAME",
            "AVALON_TASK",
        }:
            return self._task_id is not None
        return False

    def get(self, key, default=None):
        warnings.warn(
            (
                "Using deprecated access to selection data. Please use"
                " attributes and methods"
                " defined by 'LauncherActionSelection'."
            ),
            category=DeprecationWarning
        )
        try:
            return self[key]
        except KeyError:
            return default

    def items(self):
        for key, value in (
            ("AYON_PROJECT_NAME", self.project_name),
            ("AYON_FOLDER_PATH", self.folder_path),
            ("AYON_TASK_NAME", self.task_name),
        ):
            if value is not None:
                yield (key, value)

    def keys(self):
        for key, _ in self.items():
            yield key

    def values(self):
        for _, value in self.items():
            yield value

    def get_project_name(self):
        """Selected project name.

        Returns:
            Union[str, None]: Selected project name.

        """
        return self._project_name

    def get_folder_id(self):
        """Selected folder id.

        Returns:
            Union[str, None]: Selected folder id.

        """
        return self._folder_id

    def get_folder_path(self):
        """Selected folder path.

        Returns:
            Union[str, None]: Selected folder path.

        """
        if self._folder_id is None:
            return None
        if self._folder_path is None:
            self._folder_path = self.folder_entity["path"]
        return self._folder_path

    def get_task_id(self):
        """Selected task id.

        Returns:
            Union[str, None]: Selected task id.

        """
        return self._task_id

    def get_task_name(self):
        """Selected task name.

        Returns:
            Union[str, None]: Selected task name.

        """
        if self._task_id is None:
            return None
        if self._task_name is None:
            self._task_name = self.task_entity["name"]
        return self._task_name

    def get_project_entity(self):
        """Project entity for the selection.

        Returns:
            Union[dict[str, Any], None]: Project entity.

        """
        if self._project_name is None:
            return None
        if self._project_entity is None:
            self._project_entity = ayon_api.get_project(self._project_name)
        return self._project_entity

    def get_folder_entity(self):
        """Folder entity for the selection.

        Returns:
            Union[dict[str, Any], None]: Folder entity.

        """
        if self._project_name is None or self._folder_id is None:
            return None
        if self._folder_entity is None:
            self._folder_entity = ayon_api.get_folder_by_id(
                self._project_name, self._folder_id
            )
        return self._folder_entity

    def get_task_entity(self):
        """Task entity for the selection.

        Returns:
            Union[dict[str, Any], None]: Task entity.

        """
        if (
            self._project_name is None
            or self._task_id is None
        ):
            return None
        if self._task_entity is None:
            self._task_entity = ayon_api.get_task_by_id(
                self._project_name, self._task_id
            )
        return self._task_entity

    @property
    def is_project_selected(self):
        """Return whether a project is selected.

        Returns:
            bool: Whether a project is selected.

        """
        return self._project_name is not None

    @property
    def is_folder_selected(self):
        """Return whether a folder is selected.

        Returns:
            bool: Whether a folder is selected.

        """
        return self._folder_id is not None

    @property
    def is_task_selected(self):
        """Return whether a task is selected.

        Returns:
            bool: Whether a task is selected.

        """
        return self._task_id is not None

    project_name = property(get_project_name)
    folder_id = property(get_folder_id)
    task_id = property(get_task_id)
    folder_path = property(get_folder_path)
    task_name = property(get_task_name)

    project_entity = property(get_project_entity)
    folder_entity = property(get_folder_entity)
    task_entity = property(get_task_entity)


class LauncherAction(object):
    """A custom action available"""
    name = None
    label = None
    icon = None
    color = None
    order = 0

    log = logging.getLogger("LauncherAction")
    log.propagate = True

    def is_compatible(self, selection):
        """Return whether the class is compatible with the Session.

        Args:
            selection (LauncherActionSelection): Data with selection.

        """
        return True

    def process(self, selection, **kwargs):
        """Process the action.

        Args:
            selection (LauncherActionSelection): Data with selection.
            **kwargs: Additional arguments.

        """
        pass


class InventoryAction(object):
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


# Launcher action
def discover_launcher_actions():
    return discover(LauncherAction)


def register_launcher_action(plugin):
    return register_plugin(LauncherAction, plugin)


def register_launcher_action_path(path):
    return register_plugin_path(LauncherAction, path)


# Inventory action
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
