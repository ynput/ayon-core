"""Copy last published workfile into local work directory."""

from pathlib import Path
import shutil
from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.pipeline import Anatomy, get_representation_path
from ayon_core.pipeline.workfile import (
    find_workfile_rootless_path,
    save_workfile_info,
)
from ayon_core.settings import get_project_settings


class CopyLastPublishedWorkfile(PreLaunchHook):
    """Copy the found published workfile and update launch context paths."""

    order = 5
    launch_types = {LaunchTypes.local}

    def execute(self):
        if not self.data.get("copy_last_published_workfile_enabled"):
            return

        representation_entity = self.data.get("last_published_workfile_info")
        if not representation_entity:
            return

        project_name = self.data["project_name"]
        host_name = self.application.host_name
        folder_entity = self.data["folder_entity"]
        task_entity = self.data["task_entity"]
        anatomy = self.data.get("anatomy", Anatomy(project_name))
        project_settings = self.data.get(
            "project_settings", get_project_settings(project_name)
        )
        if not (last_workfile_path := self.data.get("last_workfile_path")):
            return

        source_path = Path(
            get_representation_path(
                project_name,
                representation_entity,
                anatomy=anatomy,
            )
        )
        if not source_path.exists():
            return

        dst_path = Path(last_workfile_path).resolve()
        if dst_path.exists():
            published_mtime = source_path.stat().st_mtime
            local_mtime = dst_path.stat().st_mtime
            if published_mtime <= local_mtime:
                if self.log:
                    self.log.debug(
                        "Latest local workfile is newer than last published; "
                        "skipping copy."
                    )
                return

        dst_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, dst_path)

        rootless_path = find_workfile_rootless_path(
            str(dst_path),
            project_name,
            folder_entity,
            task_entity,
            host_name,
            project_settings=project_settings,
            anatomy=anatomy,
        )
        save_workfile_info(
            project_name,
            task_entity["id"],
            rootless_path,
            host_name,
        )
        self.log.info(f"Copied last published workfile to {dst_path}")

        self.data["last_workfile_path"] = dst_path.as_posix()
        self.data["env"]["AYON_LAST_WORKFILE"] = dst_path.as_posix()
