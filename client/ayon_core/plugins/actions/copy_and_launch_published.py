import shutil
from pathlib import Path
from typing import Any

import ayon_api

from ayon_core.addon import AddonsManager, IHostAddon
from ayon_core.lib import StringTemplate
from ayon_core.pipeline import Anatomy, LauncherAction
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.template_data import get_template_data
from ayon_core.pipeline.version_start import get_versioning_start
from ayon_core.pipeline.workfile.path_resolving import (
    get_last_workfile_with_version,
    get_workdir,
    get_workfile_template_key,
)
from ayon_core.pipeline.workfile.utils import (
    find_workfile_rootless_path,
    save_workfile_info,
)


class _CopyAndLaunchPublishedLogic:
    name = "copy_and_launch_published"
    label = "Copy and Open"
    order = 5
    app_full_name = None
    host_name = None
    supported_exts = frozenset()

    def is_compatible(self, selection) -> bool:
        """Return whether this app variant can process current selection."""
        if not (
            selection.is_published_workfile
            and selection.is_project_selected
            and selection.is_folder_selected
            and selection.is_task_selected
            and selection.is_workfile_selected
        ):
            return False

        representation_entity = selection.representation_entity
        if not representation_entity:
            return False
        source_path = get_representation_path_with_anatomy(
            representation_entity, Anatomy(selection.project_name)
        )
        if not source_path:
            return False
        src_ext = Path(source_path).suffix.lower().lstrip(".")
        return src_ext in self.supported_exts

    def process(self, selection, **kwargs) -> None:
        """Copy selected published workfile to workdir and launch app."""
        project_name = selection.project_name
        project_entity = selection.project_entity
        folder_entity = selection.folder_entity
        task_entity = selection.task_entity
        representation_entity = selection.representation_entity
        if representation_entity is None:
            raise RuntimeError("Published representation is not available.")

        anatomy = Anatomy(project_name, project_entity=project_entity)
        source_path = get_representation_path_with_anatomy(
            representation_entity, anatomy
        )
        source_path_obj = Path(source_path) if source_path else None
        if source_path_obj is None or not source_path_obj.exists():
            raise RuntimeError(
                "Published workfile path is not available on this machine."
            )

        src_ext = source_path_obj.suffix.lower().lstrip(".")
        if not src_ext:
            raise RuntimeError(
                "Could not determine source workfile extension."
            )

        if src_ext not in self.supported_exts:
            raise RuntimeError(
                f"Selected workfile '.{src_ext}' is not supported by"
                f" '{self.app_full_name}'."
            )

        project_settings = selection.get_project_settings()
        template_key = get_workfile_template_key(
            project_name,
            task_entity["taskType"],
            self.host_name,
            project_settings=project_settings,
        )
        workdir = get_workdir(
            project_entity,
            folder_entity,
            task_entity,
            self.host_name,
            anatomy=anatomy,
            template_key=template_key,
            project_settings=project_settings,
        )
        workdir_path = Path(workdir)
        workdir_path.mkdir(parents=True, exist_ok=True)

        template_data = get_template_data(
            project_entity,
            folder_entity,
            task_entity,
            self.host_name,
        )
        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        ).template

        _last_path, last_version = get_last_workfile_with_version(
            str(workdir_path),
            file_template,
            template_data,
            {f".{src_ext}"},
        )
        published_version = self._get_published_version(
            project_name, representation_entity
        )
        if last_version is None:
            version = get_versioning_start(
                project_name,
                self.host_name,
                task_name=task_entity["name"],
                task_type=task_entity["taskType"],
                product_base_type="workfile",
                project_settings=project_settings,
            )
            version = max(version, published_version + 1)
        else:
            version = max(last_version + 1, published_version + 1)

        template_data["version"] = version
        template_data["ext"] = src_ext
        filename = StringTemplate.format_strict_template(
            file_template, template_data
        )
        destination_path = workdir_path / filename
        shutil.copy2(source_path_obj, destination_path)

        rootless_path = find_workfile_rootless_path(
            str(destination_path),
            project_name,
            folder_entity,
            task_entity,
            self.host_name,
            project_settings=project_settings,
            anatomy=anatomy,
        )
        save_workfile_info(
            project_name,
            task_entity["id"],
            rootless_path,
            self.host_name,
            version=version,
            comment=None,
            description=None,
        )

        apps_addon = self._get_applications_addon()
        apps_addon.launch_application(
            app_name=self.app_full_name,
            project_name=project_name,
            folder_path=folder_entity["path"],
            task_name=task_entity["name"],
            workfile_path=str(destination_path),
        )

    def _get_applications_addon(self) -> Any:
        """Return applications addon used to launch selected app variant."""
        addons_manager = AddonsManager()
        return addons_manager["applications"]

    def _get_published_version(
        self,
        project_name: str,
        representation_entity: dict[str, Any],
    ) -> int:
        """Return parent version number for selected representation."""
        version_id = representation_entity.get("versionId")
        if not version_id:
            return 0
        version_entity = ayon_api.get_version_by_id(
            project_name, version_id, fields={"version"}
        )
        if not version_entity:
            return 0
        return version_entity.get("version") or 0


def _host_extensions() -> dict[str, set[str]]:
    """Map host names to supported workfile extensions."""
    addons_manager = AddonsManager()
    output: dict[str, set[str]] = {}
    for addon in addons_manager.get_enabled_addons():
        if not isinstance(addon, IHostAddon):
            continue
        host_name = addon.host_name
        if not host_name:
            continue
        exts = {
            ext.lower().lstrip(".")
            for ext in addon.get_workfile_extensions()
            if ext
        }
        if exts:
            output[host_name] = exts
    return output


def _create_variant_actions() -> dict[str, type[LauncherAction]]:
    """Dynamically create one launcher action class per app variant."""
    actions: dict[str, type[LauncherAction]] = {}
    try:
        addons_manager = AddonsManager()
        applications_addon = addons_manager["applications"]
        apps_manager = applications_addon.get_applications_manager()
        host_exts = _host_extensions()
    except Exception:
        return actions
    for app_group in apps_manager.app_groups.values():
        host_name = app_group.host_name
        if not host_name or host_name not in host_exts:
            continue

        icon = None
        if app_group.icon:
            icon_url = applications_addon.get_app_icon_url(
                app_group.icon, server=True
            )
            if icon_url:
                # `get_qt_icon` with type "ayon_url" expects a path relative to
                # the server base URL (it prepends base_url); full URLs break.
                base_url = ayon_api.get_base_url()
                if icon_url.startswith(base_url):
                    icon_url = icon_url[len(base_url) + 1 :]
                    icon = {"type": "ayon_url", "url": icon_url}
                else:
                    icon = {"type": "url", "url": icon_url}

        for app in app_group:
            if not app.enabled:
                continue
            class_name = "CopyAndLaunchPublished_" + app.full_name.replace(
                "-", "_"
            ).replace(".", "_")
            identifier = f"copy_and_launch_published/{app.full_name}"
            attrs = {
                "identifier": identifier,
                "name": "copy_and_launch_published",
                "label": "Copy and Open",
                "label_variant": app.full_label,
                "icon": icon or "fa.copy",
                "order": 5,
                "app_full_name": app.full_name,
                "host_name": host_name,
                "supported_exts": frozenset(host_exts[host_name]),
            }
            actions[class_name] = type(
                class_name,
                (_CopyAndLaunchPublishedLogic, LauncherAction),
                attrs,
            )
    return actions


globals().update(_create_variant_actions())
