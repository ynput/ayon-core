import csv
import logging
from typing import Dict, List, Optional

from ayon_core.addon import AddonLibrary
from ayon_core.folders import create_folder

log = logging.getLogger(__name__)

def ingest_folders_from_csv(filepath: str, project_name: str, parent_id: Optional[str] = None) -> List[str]:
    """
    Ingest folders from a CSV file.

    Expected CSV columns (case-insensitive headers):
        - name (required)
        - label (optional)
        - folder_type (optional, default 'Folder')
        - description (optional)
        - parent_id (optional, overrides parent_id parameter)

    Any extra columns are ignored.

    Args:
        filepath: Path to CSV file.
        project_name: Name of the AYON project.
        parent_id: Default parent folder ID (overridden by CSV 'parent_id' column).

    Returns:
        List of created folder IDs.
    """
    created_ids = []
    required_columns = {'name'}
    valid_columns = {'name', 'label', 'folder_type', 'description', 'parent_id'}

    with open(filepath, 'r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        # Normalize header names to lowercase
        headers = [h.strip().lower() for h in reader.fieldnames]
        if not required_columns.issubset(headers):
            missing = required_columns - set(headers)
            raise ValueError(f"Missing required columns: {missing}")

        for row in reader:
            # Build folder data
            folder_data = {}
            for key, val in row.items():
                k = key.strip().lower()
                if k in valid_columns and val:
                    folder_data[k] = val.strip()

            name = folder_data.get('name')
            if not name:
                log.warning("Skipping row with empty name: %s", row)
                continue

            # Determine parent_id: CSV column overrides function parameter
            effective_parent_id = folder_data.get('parent_id', parent_id)

            # Optional fields
            label = folder_data.get('label')
            folder_type = folder_data.get('folder_type', 'Folder')
            description = folder_data.get('description')

            try:
                folder_id = create_folder(
                    project_name=project_name,
                    folder_name=name,
                    parent_id=effective_parent_id,
                    label=label,
                    folder_type=folder_type,
                    description=description
                )
                created_ids.append(folder_id)
                log.info("Created folder '%s' (id=%s)", name, folder_id)
            except Exception as exc:
                log.error("Failed to create folder '%s': %s", name, exc)

    return created_ids


def create_folder(
    project_name: str,
    folder_name: str,
    parent_id: Optional[str] = None,
    label: Optional[str] = None,
    folder_type: str = 'Folder',
    description: Optional[str] = None
) -> str:
    """
    Create a folder in AYON.

    This is a placeholder implementation. Replace with actual API call.
    """
    # Example implementation - replace with actual AYON API call
    from ayon_core.api import create_entity
    payload = {
        "name": folder_name,
        "type": folder_type,
        "parentId": parent_id,
        "label": label,
        "description": description,
    }
    # Remove None values
    payload = {k: v for k, v in payload.items() if v is not None}
    return create_entity(project_name, "folder", payload)
