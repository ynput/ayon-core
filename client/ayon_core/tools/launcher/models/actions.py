import os
import platform
import subprocess
from urllib.parse import urlencode

import ayon_api

from ayon_core import resources
from ayon_core.lib import (
    Logger,
    NestedCacheItem,
    CacheItem,
    get_settings_variant,
)
from ayon_core.addon import AddonsManager
from ayon_core.pipeline.actions import (
    discover_launcher_actions,
    LauncherActionSelection,
    register_launcher_action_path,
)


# class Action:
#     def __init__(self, label, icon=None, identifier=None):
#         self._label = label
#         self._icon = icon
#         self._callbacks = []
#         self._identifier = identifier or uuid.uuid4().hex
#         self._checked = True
#         self._checkable = False
#
#     def set_checked(self, checked):
#         self._checked = checked
#
#     def set_checkable(self, checkable):
#         self._checkable = checkable
#
#     def set_label(self, label):
#         self._label = label
#
#     def add_callback(self, callback):
#         self._callbacks = callback
#
#
# class Menu:
#     def __init__(self, label, icon=None):
#         self.label = label
#         self.icon = icon
#         self._actions = []
#
#     def add_action(self, action):
#         self._actions.append(action)


class ActionItem:
    """Item representing single action to trigger.

    Todos:
        Get rid of application specific logic.

    Args:
        action_type (Literal["webaction", "local"]): Type of action.
        identifier (str): Unique identifier of action item.
        label (str): Action label.
        variant_label (Union[str, None]): Variant label, full label is
            concatenated with space. Actions are grouped under single
            action if it has same 'label' and have set 'variant_label'.
        icon (dict[str, str]): Icon definition.
        order (int): Action ordering.
        addon_name (str): Addon name.
        addon_version (str): Addon version.
        full_label (Optional[str]): Full label, if not set it is generated
            from 'label' and 'variant_label'.
    """

    def __init__(
        self,
        action_type,
        identifier,
        label,
        variant_label,
        icon,
        order,
        addon_name=None,
        addon_version=None,
        full_label=None
    ):
        self.action_type = action_type
        self.identifier = identifier
        self.label = label
        self.variant_label = variant_label
        self.icon = icon
        self.order = order
        self.addon_name = addon_name
        self.addon_version = addon_version
        self._full_label = full_label

    def copy(self):
        return self.from_data(self.to_data())

    @property
    def full_label(self):
        if self._full_label is None:
            if self.variant_label:
                self._full_label = " ".join([self.label, self.variant_label])
            else:
                self._full_label = self.label
        return self._full_label

    def to_data(self):
        return {
            "identifier": self.identifier,
            "label": self.label,
            "variant_label": self.variant_label,
            "icon": self.icon,
            "order": self.order,
            "full_label": self._full_label,
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)


def get_action_icon(action):
    """Get action icon info.

    Args:
        action (LacunherAction): Action instance.

    Returns:
        dict[str, str]: Icon info.
    """

    icon = action.icon
    if not icon:
        return {
            "type": "awesome-font",
            "name": "fa.cube",
            "color": "white"
        }

    if isinstance(icon, dict):
        return icon

    icon_path = resources.get_resource(icon)
    if not os.path.exists(icon_path):
        try:
            icon_path = icon.format(resources.RESOURCES_DIR)
        except Exception:
            pass

    if os.path.exists(icon_path):
        return {
            "type": "path",
            "path": icon_path,
        }

    return {
        "type": "awesome-font",
        "name": icon,
        "color": action.color or "white"
    }


class ActionsModel:
    """Actions model.

    Args:
        controller (AbstractLauncherBackend): Controller instance.
    """

    def __init__(self, controller):
        self._controller = controller

        self._log = None

        self._discovered_actions = None
        self._actions = None
        self._action_items = {}
        self._webaction_items = NestedCacheItem(
            levels=2, default_factory=list
        )

        self._addons_manager = None

        self._variant = get_settings_variant()

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    def refresh(self):
        self._discovered_actions = None
        self._actions = None
        self._action_items = {}

        self._controller.emit_event("actions.refresh.started")
        self._get_action_objects()
        self._controller.emit_event("actions.refresh.finished")

    def get_action_items(self, project_name, folder_id, task_id):
        """Get actions for project.

        Args:
            project_name (Union[str, None]): Project name.
            folder_id (Union[str, None]): Folder id.
            task_id (Union[str, None]): Task id.

        Returns:
            list[ActionItem]: List of actions.

        """
        selection = self._prepare_selection(project_name, folder_id, task_id)
        output = []
        action_items = self._get_action_items(project_name)
        for identifier, action in self._get_action_objects().items():
            if action.is_compatible(selection):
                output.append(action_items[identifier])
        output.extend(self._get_webactions(selection))

        return output

    def trigger_action(
        self,
        acton_type,
        identifier,
        project_name,
        folder_id,
        task_id,
        addon_name,
        addon_version,
    ):
        if acton_type == "webaction":
            self._trigger_webaction(
                identifier,
                project_name,
                folder_id,
                task_id,
                addon_name,
                addon_version,
            )
            return

        selection = self._prepare_selection(project_name, folder_id, task_id)
        failed = False
        error_message = None
        action_label = identifier
        action_items = self._get_action_items(project_name)
        try:
            action = self._actions[identifier]
            action_item = action_items[identifier]
            action_label = action_item.full_label
            self._controller.emit_event(
                "action.trigger.started",
                {
                    "identifier": identifier,
                    "full_label": action_label,
                }
            )

            action.process(selection)
        except Exception as exc:
            self.log.warning("Action trigger failed.", exc_info=True)
            failed = True
            error_message = str(exc)

        self._controller.emit_event(
            "action.trigger.finished",
            {
                "identifier": identifier,
                "failed": failed,
                "error_message": error_message,
                "full_label": action_label,
            }
        )

    def _get_addons_manager(self):
        if self._addons_manager is None:
            self._addons_manager = AddonsManager()
        return self._addons_manager

    def _prepare_selection(self, project_name, folder_id, task_id):
        project_entity = None
        if project_name:
            project_entity = self._controller.get_project_entity(project_name)
        project_settings = self._controller.get_project_settings(project_name)
        return LauncherActionSelection(
            project_name,
            folder_id,
            task_id,
            project_entity=project_entity,
            project_settings=project_settings,
        )

    def _get_webactions(self, selection: LauncherActionSelection):
        if not selection.is_project_selected:
            return []

        entity_type = None
        entity_id = None
        entity_subtypes = []
        if selection.is_task_selected:
            entity_type = "task"
            entity_id = selection.task_entity["id"]
            entity_subtypes = [selection.task_entity["taskType"]]

        elif selection.is_folder_selected:
            entity_type = "folder"
            entity_id = selection.folder_entity["id"]
            entity_subtypes = [selection.folder_entity["folderType"]]

        entity_ids = []
        if entity_id:
            entity_ids.append(entity_id)

        project_name = selection.project_name
        cache: CacheItem = self._webaction_items[project_name][entity_id]
        if cache.is_valid:
            return cache.get_data()

        context = {
            "projectName": project_name,
            "entityType": entity_type,
            "entitySubtypes": entity_subtypes,
            "entityIds": entity_ids,
        }
        try:
            response = ayon_api.post("actions/list", **context)
            response.raise_for_status()
        except Exception:
            self.log.warning("Failed to collect webactions.", exc_info=True)
            return []

        action_items = []
        for action in response.data["actions"]:
            # NOTE Settings variant may be important for triggering?
            # - action["variant"]
            icon = action["icon"]
            if icon["type"] == "url" and icon["url"].startswith("/"):
                icon["type"] = "ayon_url"
            action_items.append(ActionItem(
                "webaction",
                action["identifier"],
                # action["category"],
                action["label"],
                None,
                action["icon"],
                action["order"],
                action["addonName"],
                action["addonVersion"],
            ))

        cache.update_data(action_items)

        return cache.get_data()

    def _trigger_webaction(
        self,
        identifier,
        project_name,
        folder_id,
        task_id,
        addon_name,
        addon_version,
    ):
        entity_type = None
        entity_ids = []
        if task_id:
            entity_type = "task"
            entity_ids.append(task_id)
        elif folder_id:
            entity_type = "folder"
            entity_ids.append(folder_id)

        query = {
            "addonName": addon_name,
            "addonVersion": addon_version,
            "identifier": identifier,
            "variant": self._variant,
        }
        url = f"actions/execute?{urlencode(query)}"
        context = {
            "projectName": project_name,
            "entityType": entity_type,
            "entityIds": entity_ids,
        }

        # TODO pass label in as argument?
        action_label= "Webaction"

        failed = False
        error_message = None
        try:
            self._controller.emit_event(
                "action.trigger.started",
                {
                    "identifier": identifier,
                    "full_label": action_label,
                }
            )
            response = ayon_api.post(url, **context)
            response.raise_for_status()
            data = response.data
            if data["success"] == True:
                self._handle_webaction_response(data)
            else:
                error_message = data["message"]
                failed = True

        except Exception as exc:
            self.log.warning("Action trigger failed.", exc_info=True)
            failed = True
            error_message = str(exc)

        self._controller.emit_event(
            "action.trigger.finished",
            {
                "identifier": identifier,
                "failed": failed,
                "error_message": error_message,
                "full_label": action_label,
            }
        )

    def _handle_webaction_response(self, data):
        response_type = data["type"]
        # Nothing to do
        if response_type == "server":
            return

        if response_type == "launcher":
            uri = data["uri"]
            # There might be a better way to do this?
            # Not sure if all linux distributions have 'xdg-open' available
            platform_name = platform.system().lower()
            if platform_name == "windows":
                os.startfile(uri)
            elif platform_name == "darwin":
                subprocess.run(["open", uri])
            else:
                subprocess.run(["xdg-open", uri])
            return

        raise Exception(
            "Unknown webaction response type '{response_type}'"
        )

    def _get_discovered_action_classes(self):
        if self._discovered_actions is None:
            # NOTE We don't need to register the paths, but that would
            #   require to change discovery logic and deprecate all functions
            #   related to registering and discovering launcher actions.
            addons_manager = self._get_addons_manager()
            actions_paths = addons_manager.collect_launcher_action_paths()
            for path in actions_paths:
                if path and os.path.exists(path):
                    register_launcher_action_path(path)
            self._discovered_actions = (
                discover_launcher_actions()
            )
        return self._discovered_actions

    def _get_action_objects(self):
        if self._actions is None:
            actions = {}
            for cls in self._get_discovered_action_classes():
                obj = cls()
                identifier = getattr(obj, "identifier", None)
                if identifier is None:
                    identifier = cls.__name__
                actions[identifier] = obj
            self._actions = actions
        return self._actions

    def _get_action_items(self, project_name):
        action_items = self._action_items.get(project_name)
        if action_items is not None:
            return action_items

        project_entity = None
        if project_name:
            project_entity = self._controller.get_project_entity(project_name)
        project_settings = self._controller.get_project_settings(project_name)

        action_items = {}
        for identifier, action in self._get_action_objects().items():
            # Backwards compatibility from 0.3.3 (24/06/10)
            # TODO: Remove in future releases
            if hasattr(action, "project_settings"):
                action.project_entities[project_name] = project_entity
                action.project_settings[project_name] = project_settings

            label = action.label or identifier
            variant_label = getattr(action, "label_variant", None)
            icon = get_action_icon(action)

            item = ActionItem(
                "local",
                identifier,
                label,
                variant_label,
                icon,
                action.order,
            )
            action_items[identifier] = item
        self._action_items[project_name] = action_items
        return action_items
