from datetime import datetime
import logging
import os
import shutil

import ayon_api

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_api import (
    get_representations,
    get_products,
    get_last_versions
)

from ayon_core.pipeline.template_data import get_template_data
from ayon_core.pipeline.workfile import get_workfile_template_key

from ayon_core.pipeline.workfile import should_use_last_workfile_on_launch, \
    should_use_last_published_workfile_on_launch

from ayon_core.pipeline.load import get_representation_path_with_anatomy


class AddLastWorkfileToLaunchArgs(PreLaunchHook):
    """Add last workfile path to launch arguments.

    This is not possible to do for all applications the same way.
    Checks 'start_last_workfile', if set to False, it will not open last
    workfile. This property is set explicitly in Launcher.
    """

    # Execute after workfile template copy
    order = 10
    app_groups = {
        "3dsmax", "adsk_3dsmax",
        "maya",
        "nuke",
        "nukex",
        "hiero",
        "houdini",
        "nukestudio",
        "fusion",
        "blender",
        "photoshop",
        "tvpaint",
        "substancepainter",
        "substancedesigner",
        "aftereffects",
        "wrap",
        "openrv",
        "cinema4d",
        "silhouette",
        "gaffer",
        "loki",
        "marvelousdesigner",
    }
    launch_types = {LaunchTypes.local}

    def execute(self):
        # self.log.addHandler(
        #     logging.FileHandler(r"C:\TEMP\%s.log" % self.__class__.__name__,
        #                         encoding="utf-8"))
        workfile_path = self.data.get("workfile_path")
        if not workfile_path:
            if not self.data.get("start_last_workfile"):
                self.log.info("It is set to not start last workfile on start.")
                return

            workfile_path = self.data.get("last_workfile_path")
            if not workfile_path:
                self.log.warning("Last workfile was not collected.")
                return

        if not os.path.exists(workfile_path):
            self.log.info("Current context does not have any workfile yet.")
            return
        self.log.info(f"Last workfile path start: {workfile_path}")
        project_name = self.data["project_name"]
        project_settings = self.data["project_settings"]
        anatomy = self.data["anatomy"]
        task_id = self.data["task_entity"]["id"]
        folder_entity = self.data["folder_entity"]
        folder_id = folder_entity["id"]
        task_name = self.data["task_name"]
        task_type = self.data["task_type"]
        project_entity = self.data["project_entity"]
        task_entity = self.data["task_entity"]
        host_name = self.application.host_name
        host_addon = self.addons_manager.get_host_addon(host_name)
        workfile_extensions = host_addon.get_workfile_extensions()


        # check the settings is this wanted at all
        use_last_workfile = should_use_last_workfile_on_launch(
            project_name,
            host_name,
            task_name,
            task_type,
            project_settings=project_settings
        )
        # check if last published workfile is wanted
        use_last_published_workfile = should_use_last_published_workfile_on_launch(
            project_name,
            host_name,
            task_name,
            task_type,
            project_settings=project_settings
        )
        if not use_last_workfile:
            self.log.info("It is set to not start last workfile on start.")
            return

        if use_last_workfile and not use_last_published_workfile:
            # Add path to workfile to arguments
            self.launch_context.launch_args.append(workfile_path)
            return

        workfile_representation = (
            self._get_last_published_workfile_representation(
                project_name, folder_id, task_id, workfile_extensions
            )
        )

        # compare timestamps of the latest publish to the latest local workfile
        # bail out if the local file is newer
        created_at_timestamp = datetime.fromisoformat(
            workfile_representation["createdAt"]).timestamp()

        if created_at_timestamp < os.path.getmtime(workfile_path):
            self.log.info(
                "Local workfile is newer than published workfile, skipping")
            self.launch_context.launch_args.append(workfile_path)
            return

        # Get workfile data
        workfile_data = get_template_data(
            project_entity, folder_entity, task_entity, host_name,
            project_settings
        )
        self.log.info(f"Workfile data: {workfile_data}")
        last_published_workfile_path = get_representation_path_with_anatomy(
            workfile_representation, anatomy
        )
        workfile_entities = list(ayon_api.get_workfiles_info(
            project_name,
            task_ids=[task_id]
        ))

        latest_workfile_entity = workfile_entities[-1]
        latest_workfile_entity_version = latest_workfile_entity["data"]["version"]
        self.log.info(f"Latest workfile version: {latest_workfile_entity_version}")
        self.log.info(f"Last published workfile path: {last_published_workfile_path}")

        extension = last_published_workfile_path.split(".")[-1]
        workfile_data["version"] = (
                latest_workfile_entity_version + 1)
        workfile_data["ext"] = extension

        template_key = get_workfile_template_key(
            task_name, host_name, project_name, project_settings
        )
        template = anatomy.get_template_item("work", template_key, "path")
        local_workfile_path = template.format_strict(workfile_data)
        self.log.info(f"Local workfile path: {local_workfile_path}")

        # Copy last published workfile to local workfile directory
        shutil.copy(
            last_published_workfile_path,
            local_workfile_path,
        )

        self.data["last_workfile_path"] = local_workfile_path
        # Keep source filepath for further path conformation
        self.data["source_filepath"] = last_published_workfile_path
        self.launch_context.launch_args.append(local_workfile_path)

    def _get_last_published_workfile_representation(self,
                                                    project_name, folder_id,
                                                    task_id, workfile_extensions
                                                    ):
        """Looks for last published representation for host and context"""

        product_entities = get_products(
            project_name,
            folder_ids={folder_id},
            product_types={"workfile"}
        )
        product_ids = {
            product_entity["id"]
            for product_entity in product_entities
        }
        if not product_ids:
            return None

        versions_by_product_id = get_last_versions(
            project_name,
            product_ids
        )
        version_ids = {
            version_entity["id"]
            for version_entity in versions_by_product_id.values()
            if version_entity["taskId"] == task_id
        }
        if not version_ids:
            return None

        for representation_entity in get_representations(
                project_name,
                version_ids=version_ids,
        ):
            ext = representation_entity["context"].get("ext")
            if not ext:
                continue
            ext = f".{ext}"
            if ext in workfile_extensions:
                return representation_entity
        return None
