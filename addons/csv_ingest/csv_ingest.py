import csv
import logging
from typing import Dict, List, Optional

from ayon_api.entity_hub import EntityHub

log = logging.getLogger(__name__)


def ingest_csv(file_path: str, project_name: str, hub: Optional[EntityHub] = None):
    """Ingest folders from a CSV file.

    Expected columns:
        - path: folder path (required)
        - folder_type: folder type (optional, default 'Folder')
        - description: folder description (optional)
        - Any other columns are treated as custom attributes.

    Args:
        file_path: Path to CSV file.
        project_name: Name of the AYON project.
        hub: EntityHub instance. If None, a new one is created.
    """
    if hub is None:
        hub = EntityHub(project_name)

    with open(file_path, 'r', encoding='utf-8') as csvfile:
        reader = csv.DictReader(csvfile)
        for row_num, row in enumerate(reader, start=2):  # row 1 is header
            folder_path = row.get('path', '').strip()
            if not folder_path:
                log.warning(f"Row {row_num}: Missing 'path' column. Skipping.")
                continue

            folder_type = row.get('folder_type', 'Folder').strip()
            description = row.get('description', '').strip()

            # Build attributes dict, excluding reserved keys
            reserved_keys = {'path', 'folder_type', 'description'}
            attributes = {k: v for k, v in row.items() if k not in reserved_keys and v}

            # Add description if provided
            if description:
                attributes['description'] = description

            # Use folder path to get or create entity
            entity = hub.get_entity_by_path(folder_path)
            if entity is None:
                entity = hub.create_entity(
                    folder_path,
                    folder_type=folder_type,
                    attributes=attributes
                )
                log.info(f"Created folder: {folder_path}")
            else:
                entity.folder_type = folder_type
                entity.attributes.update(attributes)
                hub.update_entity(entity)
                log.info(f"Updated folder: {folder_path}")

    hub.commit_changes()
    log.info("CSV ingest completed successfully.")
