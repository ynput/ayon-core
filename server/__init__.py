from typing import Any, Dict

from api.resolve import StringTemplate
from ayon_server.addons import BaseServerAddon
from ayon_server.actions import (
    ActionExecutor,
    ExecuteResponseModel,
    SimpleActionManifest,
)
from ayon_server.forms.simple_form import SimpleForm, FormSelectOption
from ayon_server.helpers.roots import get_roots_for_projects
from ayon_server.lib.postgres import Postgres

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
                    identifier="core.copyfilepath",
                    label="Copy File Path",
                    icon={
                        "type": "material-symbols",
                        "name": "content_copy",
                    },
                    order=100,
                    entity_type="version",
                    entity_subtypes=None,
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

        if executor.identifier == "core.copyfilepath":
            return await self.copy_file_path_action(executor)

        logger.debug(f"Unknown action: {executor.identifier}")
        # Works since AYON server 1.8.3
        if hasattr(executor, "get_simple_response"):
            return await executor.get_simple_response(
                "Unknown action", success=False
            )

    async def copy_file_path_initial_form(
        self,
        executor: ActionExecutor
    ) -> ExecuteResponseModel:
        """Get initial form for Copy File Path action."""
        form = SimpleForm()

        platform_options: list[FormSelectOption] = []
        platforms = {"windows": "Windows", "linux": "Linux", "darwin": "OSX"}
        for value, label in platforms.items():
            platform_options.append(
                FormSelectOption(value=value, label=label)
            )

        form.select(
            name="platform",
            label="Select OS",
            options=platform_options,
            value=platform_options[0]["value"],
        )

        version_id = (
            executor.context.entity_ids[0]
            if executor.context.entity_ids
            else None
        )
        form.hidden(
            "version_id", version_id
        )
        project_name = executor.context.project_name

        query = (
            "SELECT name, files -> 0 ->> 'path' AS first_rootless_path "
            f"FROM project_{project_name}.representations "
            f"WHERE version_id = '{version_id}' "
            "ORDER BY name"
        )

        representation_options = []
        async for row in Postgres.iterate(query):
            representation_options.append(
                FormSelectOption(
                    value=row["first_rootless_path"], label=row["name"]
                )
            )

        form.select(
            name="first_rootless_path",
            label="Select Representation",
            options=representation_options,
            value=representation_options[0]["value"],
        )

        return await executor.get_form_response("Select representation", form)

    async def copy_file_path_action(
        self,
        executor: ActionExecutor,
    ) -> ExecuteResponseModel:
        form_data: Dict[str, Any] = executor.context.form_data or {}

        if form_data:
            project_name = executor.context.project_name
            roots = await get_roots_for_projects(
                executor.user.name,
                site_id=None,
                projects=[project_name],
                platform=form_data["platform"],
            )

            context = {"root": roots[project_name]}
            first_rootless_path = form_data["first_rootless_path"]
            resolved_path = StringTemplate.format_template(
                first_rootless_path, context
            )
            return await executor.get_simple_response(
                message=f"Copied '{resolved_path}' to clipboard",
                extra_clipboard=resolved_path,
                success=True,
            )

        # No interaction yet, show the initial form
        return await self.copy_file_path_initial_form(executor)
