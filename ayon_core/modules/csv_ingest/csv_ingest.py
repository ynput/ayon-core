import csv
import io
import json
import logging
import os
import re
from typing import Dict, List, Optional, Any

from ayon_core.lib import Logger
from ayon_core.addon import Addon
from ayon_core.pipeline import registered_host
from ayon_core.tools.utils import get_ayon_connection

log = Logger.get_logger(__name__)


class CSVFoldersIngest:
    """Ingest folders from CSV file."""

    def __init__(self, project_name: str, user_id: str, addon: Addon):
        self._project_name = project_name
        self._user_id = user_id
        self._addon = addon
        self._ayon = get_ayon_connection()
        self._folder_types = self._get_folder_types()

    def _get_folder_types(self) -> Dict[str, Any]:
        """Get all folder types from server."""
        return self._ayon.get(f"projects/{self._project_name}/folderTypes")

    def _parse_csv(self, csv_content: str) -> List[Dict[str, str]]:
        """Parse CSV content and return list of row dicts."""
        reader = csv.DictReader(io.StringIO(csv_content))
        return [row for row in reader]

    def _validate_rows(self, rows: List[Dict[str, str]]) -> bool:
        """Basic validation - at least 'name' column exists."""
        if not rows:
            log.error("CSV file is empty")
            return False
        required = {"name"}
        for row in rows:
            if not row.get("name"):
                log.error("Missing 'name' column in row.")
                return False
        return True

    def _create_or_update_folder(self, folder_data: Dict[str, str]) -> Dict[str, Any]:
        """Create or update a folder with given data.

        Supports columns: name, label, folderType, parent, description, attrib.
        """
        name = folder_data["name"].strip()
        label = folder_data.get("label", "").strip() or name
        folder_type = folder_data.get("folderType", "").strip()
        parent_name = folder_data.get("parent", "").strip()
        description = folder_data.get("description", "").strip()
        attrib_str = folder_data.get("attrib", "").strip()

        # Resolve folder type
        if not folder_type:
            folder_type = "Folder"
        folder_type_found = None
        for ft in self._folder_types:
            if ft["name"] == folder_type:
                folder_type_found = ft["id"]
                break
        if not folder_type_found:
            log.warning(f"Folder type '{folder_type}' not found, using default.")
            folder_type_found = "Folder"

        # Resolve parent
        parent_id = None
        if parent_name:
            existing_parent = self._ayon.get(
                f"projects/{self._project_name}/folders",
                params={"name": parent_name}
            )
            if existing_parent:
                parent_id = existing_parent[0]["id"]
            else:
                log.error(f"Parent folder '{parent_name}' not found.")
                return None

        # Check if folder already exists
        existing = self._ayon.get(
            f"projects/{self._project_name}/folders",
            params={"name": name}
        )

        attrib = {}
        if attrib_str:
            try:
                attrib = json.loads(attrib_str)
            except json.JSONDecodeError:
                log.warning(f"Invalid attrib JSON for folder '{name}': {attrib_str}")

        payload = {
            "name": name,
            "label": label,
            "folderType": folder_type_found,
            "parentId": parent_id,
            "description": description,
            "attrib": attrib
        }

        if existing:
            folder_id = existing[0]["id"]
            # Update only provided fields
            update_payload = {k: v for k, v in payload.items() if v is not None and v != ""}
            if update_payload:
                self._ayon.put(
                    f"projects/{self._project_name}/folders/{folder_id}",
                    json=update_payload
                )
            log.info(f"Updated folder: {name}")
            return existing[0]
        else:
            new_folder = self._ayon.post(
                f"projects/{self._project_name}/folders",
                json=payload
            )
            log.info(f"Created folder: {name}")
            return new_folder

    def ingest(self, csv_content: str) -> Dict[str, Any]:
        """Main entry point for CSV ingest."""
        rows = self._parse_csv(csv_content)
        if not self._validate_rows(rows):
            return {"success": False, "message": "Validation failed."}

        results = []
        for row in rows:
            folder = self._create_or_update_folder(row)
            results.append({"name": row["name"], "result": "created" if folder else "failed"})

        return {"success": True, "results": results}
