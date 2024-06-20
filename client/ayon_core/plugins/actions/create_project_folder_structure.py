from ayon_core.pipeline import LauncherAction
from ayon_core.pipeline import project_folders


class CreateProjectStructureAction(LauncherAction):
    """Create project structure as defined in settings."""
    name = "create_project_structure"
    label = "Create Project Structure"
    icon = "sitemap"
    color = "#e0e1e1"
    order = 1000

    def is_compatible(self, selection) -> bool:
        return (
            selection.is_project_selected and
            not selection.is_folder_selected
        )

    def process(self, selection, **kwargs):
        project_folders.create_project_folders(selection.project_name)
