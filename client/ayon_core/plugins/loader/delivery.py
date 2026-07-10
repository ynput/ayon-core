from typing import Optional, Any

from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.pipeline.actions import (
    LoaderSimpleActionPlugin,
    LoaderActionSelection,
    LoaderActionResult,
)
from ayon_core.tools.delivery import DeliveryOptionsDialog


class DeliveryAction(LoaderSimpleActionPlugin):
    identifier = "core.delivery"
    label = "Deliver Versions"
    order = 35
    icon = MaterialSymbolsIcon("uload", color="#d8d8d8")

    def is_compatible(self, selection: LoaderActionSelection) -> bool:
        if self.host_name is not None:
            return False

        if not selection.selected_ids:
            return False

        return (
            selection.versions_selected()
            or selection.representations_selected()
        )

    def execute_simple_action(
        self,
        selection: LoaderActionSelection,
        form_values: dict[str, Any],
    ) -> Optional[LoaderActionResult]:
        version_ids = set()
        if selection.selected_type == "representation":
            versions = selection.entities.get_representations_versions(
                selection.selected_ids
            )
            version_ids = {version["id"] for version in versions}

        if selection.selected_type == "version":
            version_ids = set(selection.selected_ids)

        if not version_ids:
            return LoaderActionResult(
                message="No versions found in your selection",
                success=False,
            )

        try:
            # TODO run the tool in subprocess
            dialog = DeliveryOptionsDialog(
                selection.project_name, version_ids, log=self.log
            )
            dialog.exec_()
        except Exception:
            self.log.error("Failed to deliver versions.", exc_info=True)

        return LoaderActionResult()
