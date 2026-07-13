from typing import Any

from ayon_server.addons import BaseServerAddon
from ayon_server.actions import (
    ActionExecutor,
    ExecuteResponseModel,
    SimpleActionManifest,
)
from ayon_server.events import dispatch_event
try:
    from ayon_server.logging import logger
except ImportError:
    from nxtools import logging as logger

from .settings import (
    CoreSettings,
    DEFAULT_VALUES,
    convert_settings_overrides,
)


class CoreAddon(BaseServerAddon):
    settings_model = CoreSettings

    async def get_default_settings(self):
        settings_model_cls = self.get_settings_model()
        return settings_model_cls(**DEFAULT_VALUES)

    async def convert_settings_overrides(
        self,
        source_version: str,
        overrides: dict[str, Any],
    ) -> dict[str, Any]:
        convert_settings_overrides(source_version, overrides)
        # Use super conversion
        return await super().convert_settings_overrides(
            source_version, overrides
        )

    async def get_simple_actions(
        self,
        project_name: str | None = None,
        variant: str = "production",
    ) -> list[SimpleActionManifest]:
        """Return a list of simple actions provided by the addon"""
        output = []

        if project_name:
            # Add 'Create Project Folder Structure' action to folders.
            output.append(
                SimpleActionManifest(
                    identifier="core.createprojectstructure",
                    label="Create Project Folder Structure",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="project",
                    entity_subtypes=None,
                    allow_multiselection=False,
                )
            )
            output.append(
                SimpleActionManifest(
                    identifier="core.delivery.version",
                    label="Deliver versions (launcher action)",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="version",
                    entity_subtypes=None,
                    allow_multiselection=True,
                )
            )
            output.append(
                SimpleActionManifest(
                    identifier="core.delivery.list",
                    label="Deliver versions (launcher action)",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="list",
                    entity_subtypes=[
                        "version:review-session",
                        "version:generic",
                    ],
                    allow_multiselection=False,
                )
            )

        return output

    async def execute_action(
        self,
        executor: ActionExecutor,
    ) -> ExecuteResponseModel:
        """Execute webactions."""

        project_name = executor.context.project_name

        if executor.identifier == "core.createprojectstructure":
            if not project_name:
                logger.error(
                    f"Can't execute {executor.identifier} because"
                    " of missing project name."
                )
                # Works since AYON server 1.8.3
                if hasattr(executor, "get_simple_response"):
                    return await executor.get_simple_response(
                        "Missing project name", success=False
                    )
                return

            args = [
                "create-project-structure", "--project", project_name,
            ]
            # Works since AYON server 1.8.3
            if hasattr(executor, "get_launcher_response"):
                return await executor.get_launcher_response(args)

            return await executor.get_launcher_action_response(args)

        if executor.identifier == "core.delivery.version":
            selected_versions = await executor.context.get_entities()
            if not selected_versions:
                return await executor.get_server_action_response(
                    message="No versions available in selection.",
                    success=False
                )
            version_ids = [version.id for version in selected_versions]
            event_id = await dispatch_event(
                topic="delivery.requested",
                project=project_name,
                payload={"version_ids": version_ids},
                finished=True,
            )
            args = [
                "deliver", "--project", project_name,
                "--event_id", event_id,
            ]

            return await executor.get_launcher_response(args)

        if executor.identifier == "core.delivery.list":
            selected_list = executor.context.entity_ids[0]
            if not selected_list:
                return await executor.get_server_action_response(
                    message="No list available in selection.",
                    success=False
                )
            event_id = await dispatch_event(
                topic="delivery.requested",
                project=project_name,
                payload={"list_id": selected_list},
                finished=True,
            )
            args = [
                "deliver", "--project", project_name,
                "--event_id", event_id,
            ]

            return await executor.get_launcher_response(args)

        logger.debug(f"Unknown action: {executor.identifier}")
        # Works since AYON server 1.8.3
        if hasattr(executor, "get_simple_response"):
            return await executor.get_simple_response(
                "Unknown action", success=False
            )
