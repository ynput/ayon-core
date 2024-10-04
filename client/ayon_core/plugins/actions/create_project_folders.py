from ayon_core.pipeline import LauncherAction, project_folders


class CreateProjectFoldersAction(LauncherAction):
    """Create project folders as defined in settings."""
    name = "create_project_folders"
    label = "Create Project Folders"
    icon = "sitemap"
    color = "#e0e1e1"
    order = 1000

    def is_compatible(self, selection) -> bool:
        return (
            selection.is_project_selected
            and not selection.is_folder_selected
        )

    def process(self, selection, **kwargs):
        project_folders.create_project_folders(selection.project_name)
