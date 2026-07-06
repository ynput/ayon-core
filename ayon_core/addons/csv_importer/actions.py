import csv
import os
from ayon_core.addons.csv_importer import constants
from ayon_core.pipeline import registered_host
from ayon_core.pipeline.create import get_product_name
from ayon_core.lib import StringTemplate


def import_csv(filepath, project_name, folder_path_template=None):
    """Import folders from CSV file."""
    from ayon_core.pipeline import get_current_project
    from ayon_core.client import get_project
    from ayon_core.entities import FolderEntity

    project = get_project(project_name)
    if not project:
        raise ValueError(f"Project '{project_name}' not found.")

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"CSV file not found: {filepath}")

    with open(filepath, mode='r', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        required_columns = ['name', 'folder_type', 'path']
        # Check required columns
        if not all(col in reader.fieldnames for col in required_columns):
            raise ValueError(f"CSV must contain columns: {required_columns}")

        created_count = 0
        for row in reader:
            folder_name = row.get('name', '').strip()
            folder_type = row.get('folder_type', '').strip()
            folder_path = row.get('path', '').strip()
            description = row.get('description', row.get('folder_description', '')).strip()

            if not folder_name or not folder_type:
                continue

            # Create folder entity
            folder = FolderEntity(
                project,
                name=folder_name,
                folder_type=folder_type,
                path=folder_path
            )

            # Set description if provided
            if description:
                folder.set_attrib('description', description)

            folder.save()
            created_count += 1

        return created_count


def run():
    """Entry point for CSV import action."""
    # Example usage: usually triggered via GUI or CLI
    pass
