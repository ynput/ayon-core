import os
import copy
import webbrowser
from dataclasses import dataclass, asdict
from urllib.parse import urlencode
from typing import Any, Optional

import ayon_api

from ayon_core import resources
from ayon_core.lib import (
    Logger,
    NestedCacheItem,
    CacheItem,
    get_settings_variant,
    run_detached_ayon_launcher_process,
)
from ayon_core.addon import AddonsManager
from ayon_core.pipeline.actions import (
    discover_launcher_actions,
    LauncherActionSelection,
    register_launcher_action_path,
)


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
        config_fields (list[dict]): Config fields for webaction.
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
        config_fields=None,
        full_label=None
    ):
        if config_fields is None:
            config_fields = []
        self.action_type = action_type
        self.identifier = identifier
        self.label = label
        self.variant_label = variant_label
        self.icon = icon
        self.order = order
        self.addon_name = addon_name
        self.addon_version = addon_version
        self.config_fields = config_fields
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
            "config_fields": copy.deepcopy(self.config_fields),
        }

    @classmethod
    def from_data(cls, data):
        return cls(**data)


@dataclass
class WebactionForm:
    fields: list[dict[str, Any]]
    title: str
    submit_label: str
    submit_icon: str
    cancel_label: str
    cancel_icon: str


@dataclass
class WebactionResponse:
    response_type: str
    success: bool
    message: Optional[str] = None
    clipboard_text: Optional[str] = None
    form: Optional[WebactionForm] = None
    error_message: Optional[str] = None

    def to_data(self):
        return asdict(self)

    @classmethod
    def from_data(cls, data):
        data = data.copy()
        form = data["form"]
        if form:
            data["form"] = WebactionForm(**form)

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
        identifier,
        project_name,
        folder_id,
        task_id,
    ):
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

    def trigger_webaction(
        self,
        identifier,
        project_name,
        folder_id,
        task_id,
        action_label,
        addon_name,
        addon_version,
        form_data,
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
        if form_data is not None:
            context["formData"] = form_data

        try:
            self._controller.emit_event(
                "webaction.trigger.started",
                {
                    "identifier": identifier,
                    "full_label": action_label,
                }
            )

            conn = ayon_api.get_server_api_connection()
            # Add 'referer' header to the request
            # - ayon-api 1.1.1 adds the value to the header automatically
            headers = conn.get_headers()
            if "referer" in headers:
                headers = None
            else:
                headers["referer"] = conn.get_base_url()
            response = ayon_api.raw_post(url, headers=headers, json=context)
            response.raise_for_status()
            handle_response = self._handle_webaction_response(response.data)

        except Exception:
            self.log.warning("Action trigger failed.", exc_info=True)
            handle_response = WebactionResponse(
                "unknown",
                False,
                error_message="Failed to trigger webaction.",
            )

        data = handle_response.to_data()
        data.update({
            "identifier": identifier,
            "action_label": action_label,
            "project_name": project_name,
            "folder_id": folder_id,
            "task_id": task_id,
            "addon_name": addon_name,
            "addon_version": addon_version,
        })
        self._controller.emit_event(
            "webaction.trigger.finished",
            data,
        )

    def get_action_config_values(
        self,
        identifier,
        project_name,
        folder_id,
        task_id,
        addon_name,
        addon_version,
    ):
        selection = self._prepare_selection(project_name, folder_id, task_id)
        if not selection.is_project_selected:
            return {}

        context = self._get_webaction_context(selection)

        query = {
            "addonName": addon_name,
            "addonVersion": addon_version,
            "identifier": identifier,
            "variant": self._variant,
        }
        url = f"actions/config?{urlencode(query)}"
        try:
            response = ayon_api.post(url, **context)
            response.raise_for_status()
        except Exception:
            self.log.warning(
                "Failed to collect webaction config values.",
                exc_info=True
            )
            return {}
        return response.data

    def set_action_config_values(
        self,
        identifier,
        project_name,
        folder_id,
        task_id,
        addon_name,
        addon_version,
        values,
    ):
        selection = self._prepare_selection(project_name, folder_id, task_id)
        if not selection.is_project_selected:
            return {}

        context = self._get_webaction_context(selection)
        context["value"] = values

        query = {
            "addonName": addon_name,
            "addonVersion": addon_version,
            "identifier": identifier,
            "variant": self._variant,
        }
        url = f"actions/config?{urlencode(query)}"
        try:
            response = ayon_api.post(url, **context)
            response.raise_for_status()
        except Exception:
            self.log.warning(
                "Failed to store webaction config values.",
                exc_info=True
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

    def _get_webaction_context(self, selection: LauncherActionSelection):
        if not selection.is_project_selected:
            return None

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
        return {
            "projectName": project_name,
            "entityType": entity_type,
            "entitySubtypes": entity_subtypes,
            "entityIds": entity_ids,
        }

    def _get_webactions(self, selection: LauncherActionSelection):
        if not selection.is_project_selected:
            return []

        context = self._get_webaction_context(selection)
        project_name = selection.project_name
        entity_id = None
        if context["entityIds"]:
            entity_id = context["entityIds"][0]

        cache: CacheItem = self._webaction_items[project_name][entity_id]
        if cache.is_valid:
            return cache.get_data()

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
            icon = action.get("icon")
            if icon and icon["type"] == "url" and icon["url"].startswith("/"):
                icon["type"] = "ayon_url"

            config_fields = action.get("configFields") or []
            variant_label = action["label"]
            group_label = action.get("groupLabel")
            if not group_label:
                group_label = variant_label
                variant_label = None

            action_items.append(ActionItem(
                "webaction",
                action["identifier"],
                group_label,
                variant_label,
                # action["category"],
                icon,
                action["order"],
                action["addonName"],
                action["addonVersion"],
                config_fields,
            ))

        cache.update_data(action_items)
        return cache.get_data()

    def _handle_webaction_response(self, data) -> WebactionResponse:
        response_type = data["type"]
        # Backwards compatibility -> 'server' type is not available since
        #   AYON backend 1.8.3
        if response_type == "server":
            return WebactionResponse(
                response_type,
                False,
                error_message="Please use AYON web UI to run the action.",
            )

        payload = data.get("payload") or {}

        # TODO handle 'extra_download'
        download_uri = payload.get("extra_download")
        if download_uri is not None:
            # TODO check if uri is relative or absolute
            webbrowser.open_new_tab(download_uri)

        response = WebactionResponse(
            response_type,
            data["success"],
            data.get("message"),
            payload.get("extra_clipboard"),
        )
        if response_type == "simple":
            pass

        elif response_type == "redirect":
            # NOTE unused 'newTab' key because we always have to
            #   open new tab from desktop app.
            if not webbrowser.open_new_tab(payload["uri"]):
                payload.error_message = "Failed to open web browser."

        elif response_type == "form":
            response.form = payload["form"]

        elif response_type == "launcher":
            # Run AYON launcher process with uri in arguments
            # NOTE This does pass environment variables of current process
            #   to the subprocess.
            # NOTE We could 'take action' directly and use the arguments here
            if payload is not None:
                uri = payload["uri"]
            else:
                uri = data["uri"]
            run_detached_ayon_launcher_process(uri)

        elif response_type in ("query", "navigate"):
            response.error_message = (
                "Please use AYON web UI to run the action."
            )

        else:
            self.log.warning(f"Unknown webaction response type '{response_type}'")
            response.error_message = "Unknown webaction response type."

        return response

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
