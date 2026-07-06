import csv
import logging
from typing import List, Dict, Optional

from ayon_core.client import get_project
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import Anatomy
from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


def parse_csv_to_hierarchy(filepath: str, project_name: str) -> List[Dict]:
    """Parse CSV file into hierarchy data with folder attributes.

    Expected columns (case-insensitive):
    - folder_path: slash-separated path
    - folder_type: type of folder (e.g., Folder, Shot, Asset)
    - folder_description: description text (optional)
    - Any other columns are treated as custom attributes (optional)

    Returns list of dicts with keys: path, type, description, custom_attributes
    """
    project = get_project(project_name)
    if not project:
        raise ValueError(f"Project '{project_name}' not found")

    anatomy = Anatomy(project_name)
    template_preset = get_project_settings(project_name).get(
        "csv_ingest", {}).get("column_mapping", {})

    hierarchy = []
    with open(filepath, 'r') as csvfile:
        reader = csv.DictReader(csvfile)
        if not reader.fieldnames:
            raise ValueError("Empty CSV file or no header")
        # Normalize column names to lowercase
        fieldnames = [f.strip().lower() for f in reader.fieldnames]
        for row in reader:
            # Build normalized row
            normalized_row = {k.strip().lower(): v for k, v in row.items()}
            path = normalized_row.get("folder_path", "").strip()
            if not path:
                log.warning("Skipping row without folder_path")
                continue
            folder_type = normalized_row.get("folder_type", "Folder").strip()
            description = normalized_row.get("folder_description", "").strip()
            # Additional custom attributes (all other columns)
            custom_attrs = {}
            for col in fieldnames:
                if col not in ["folder_path", "folder_type", "folder_description"]:
                    val = normalized_row.get(col, "").strip()
                    if val:
                        custom_attrs[col] = val
            hierarchy.append({
                "path": path,
                "type": folder_type,
                "description": description,
                "custom_attributes": custom_attrs
            })
    return hierarchy


def apply_hierarchy(project_name: str, hierarchy: List[Dict]):
    """Create or update folders from parsed hierarchy."""
    from ayon_core.client import get_project, get_folders, create_folder, update_folder
    project = get_project(project_name)
    if not project:
        raise ValueError(f"Project '{project_name}' not found")

    for entry in hierarchy:
        path = entry["path"]
        folder_type = entry["type"]
        description = entry["description"]

        # Get or create parent folders recursively
        parts = path.split("/")
        parent_path = "/".join(parts[:-1]) if len(parts) > 1 else ""
        folder_name = parts[-1]

        # Ensure parent exists
        if parent_path:
            parent = get_folders(project, paths=[parent_path])
            if not parent:
                # Recursively create parent
                parent_entry = {
                    "path": parent_path,
                    "type": "Folder",
                    "description": "",
                    "custom_attributes": {}
                }
                apply_hierarchy(project_name, [parent_entry])
        else:
            parent = None

        try:
            existing = get_folders(project, paths=[path])
            if existing:
                folder = existing[0]
                # Update if description or type changed
                update_data = {}
                if folder_type and folder.attrib.get("folderType") != folder_type:
                    update_data["folderType"] = folder_type
                if description and folder.attrib.get("description") != description:
                    update_data["description"] = description
                if entry["custom_attributes"]:
                    # Merge custom attributes
                    ca = folder.attrib.get("customAttributes", {})
                    ca.update(entry["custom_attributes"])
                    update_data["customAttributes"] = ca
                if update_data:
                    update_folder(project, folder.id, update_data)
                    log.debug(f"Updated folder: {path}")
            else:
                # Create folder
                data = {
                    "name": folder_name,
                    "folderType": folder_type,
                    "description": description,
                    "customAttributes": entry["custom_attributes"]
                }
                if parent:
                    data["parentId"] = parent.id
                create_folder(project, data)
                log.debug(f"Created folder: {path}")
        except Exception as e:
            log.error(f"Failed to process folder '{path}': {e}")
            raise
