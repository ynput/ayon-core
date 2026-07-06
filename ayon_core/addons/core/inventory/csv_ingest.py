import csv
from typing import Dict, List, Optional
from ayon_api import get_project, create_folder, update_folder
from ayon_core.addons.core.inventory import InventoryAddon


def ingest_csv(project_name: str, csv_path: str, delimiter: str = ","):
    """Ingest folders from a CSV file.

    Expected CSV columns: folder_name, parent_path, folder_type (optional), description (optional)
    """
    project = get_project(project_name)
    addon = InventoryAddon(project)

    with open(csv_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            folder_name = row.get("folder_name", "").strip()
            if not folder_name:
                continue
            parent_path = row.get("parent_path", "").strip()
            folder_type = row.get("folder_type", "Folder").strip() or "Folder"
            description = row.get("description", "").strip()

            # Determine parent folder path
            if parent_path:
                parent_id = addon.get_folder_by_path(parent_path).get("id")
            else:
                parent_id = None

            # Check if folder already exists
            existing = addon.get_folder_by_path(f"{parent_path}/{folder_name}" if parent_path else folder_name)
            if existing:
                folder_id = existing["id"]
                if description:
                    update_folder(project_name, folder_id, description=description)
            else:
                # Create folder with description if provided
                create_kwargs = {"folder_type": folder_type}
                if description:
                    create_kwargs["description"] = description
                create_folder(
                    project_name,
                    folder_name,
                    parent_id=parent_id,
                    **create_kwargs
                )
