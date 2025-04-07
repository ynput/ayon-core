from typing import Any

from ayon_server.addons import BaseServerAddon
from ayon_server.actions import (
    ActionExecutor,
    ExecuteResponseModel,
    SimpleActionManifest,
)

from .settings import (
    CoreSettings,
    DEFAULT_VALUES,
    convert_settings_overrides,
)


IDENTIFIER_PREFIX = "core"


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
                    identifier=f"{IDENTIFIER_PREFIX}.createprojectstructure",
                    label="Create Project Folder Structure",
                    icon={
                        "type": "material-symbols",
                        "name": "create_new_folder",
                    },
                    order=100,
                    entity_type="folder",
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

        if executor.identifier == \
              f"{IDENTIFIER_PREFIX}.create_project_structure":

            if not project_name:
                raise ValueError(
                    f"Can't execute {executor.identifier} because"
                    " of missing project name."
                )
                return

            return await executor.get_launcher_action_response(
                args=[
                    "create-project-structure",
                    "--project", project_name,
                ]
            )

        raise ValueError(f"Unknown action: {executor.identifier}")
