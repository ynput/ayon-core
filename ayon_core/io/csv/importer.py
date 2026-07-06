import csv
import logging
from typing import Dict, List, Optional

from ayon_core.addon import AddonManager
from ayon_core.pipeline.create import Creator
from ayon_core.pipeline.workfile import get_workfile
from ayon_core.pipeline import get_current_project
from ayon_core.host import IHost
from ayon_core.client import get_entities, create_entity

log = logging.getLogger(__name__)


def import_folders_from_csv(
    filepath: str,
    project_name: Optional[str] = None,
    folder_type: str = "Folder",
) -> List[Dict]:
    """Import folders from CSV file.

    Expected columns: name, label, path, description (optional)
    """
    if project_name is None:
        project_name = get_current_project()

    with open(filepath, newline='', encoding='utf-8-sig') as csvfile:
        reader = csv.DictReader(csvfile)
        required_fields = {"name"}
        if reader.fieldnames is None:
            raise ValueError("CSV file has no columns")
        missing = required_fields - set(reader.fieldnames)
        if missing:
            raise ValueError(f"CSV missing required columns: {missing}")

        folders = []
        for row in reader:
            name = row.get("name", "").strip()
            if not name:
                log.warning("Skipping row with empty name")
                continue
            label = row.get("label", "").strip() or name
            path = row.get("path", "").strip()
            description = row.get("description", "").strip()

            folder_data = {
                "name": name,
                "label": label,
                "path": path,
                "folderType": folder_type,
                "description": description,
            }
            folders.append(folder_data)

        # Create folders via API
        created = []
        for folder_data in folders:
            try:
                entity = create_entity(
                    project_name=project_name,
                    entity_type="folder",
                    data=folder_data,
                )
                created.append(entity)
                log.info(f"Created folder: {folder_data['name']}")
            except Exception as e:
                log.error(f"Failed to create folder {folder_data['name']}: {e}")
        return created
