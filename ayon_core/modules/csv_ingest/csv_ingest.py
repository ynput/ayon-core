# -*- coding: utf-8 -*-
"""CSV ingest module for AYON."""

import csv
import io
from typing import Dict, List, Optional

from ayon_core.addon import Addon
from ayon_core.pipeline import CreatedInstance


class CSVFolderIngest:
    """Handles CSV ingestion to create folder structures with descriptions."""

    DEFAULT_COLUMNS = {
        "name": "Name",
        "parent_name": "ParentName",
        "folder_type": "FolderType",
        "label": "Label",
        "description": "Description",  # NEW: support description column
    }

    def __init__(self, addon: Addon):
        self.addon = addon

    def parse_csv(self, content: str) -> List[Dict]:
        """Parse CSV content into list of folder dictionaries."""
        reader = csv.DictReader(io.StringIO(content))
        rows = []
        for row in reader:
            # Normalize keys (strip whitespace)
            normalized = {k.strip(): v.strip() for k, v in row.items()}
            folder = {}
            # Map known columns
            folder["name"] = normalized.get(self.DEFAULT_COLUMNS["name"], "").strip()
            folder["parent_name"] = normalized.get(self.DEFAULT_COLUMNS["parent_name"], "").strip()
            folder["folder_type"] = normalized.get(self.DEFAULT_COLUMNS["folder_type"], "Folder").strip()
            folder["label"] = normalized.get(self.DEFAULT_COLUMNS["label"], "").strip()
            folder["description"] = normalized.get(self.DEFAULT_COLUMNS["description"], "").strip()  # NEW
            if folder["name"]:
                rows.append(folder)
        return rows

    def create_folders(self, project_name: str, folders: List[Dict]):
        """Create folders in AYON from parsed list."""
        from ayon_core.pipeline import register_folder
        for folder_data in folders:
            parent_name = folder_data["parent_name"]
            parent = None
            if parent_name:
                # Resolve parent folder (simplified, actual implementation may vary)
                parent = self.addon.get_folder_by_name(project_name, parent_name)
            folder_entity = self.addon.create_folder(
                project_name,
                folder_data["name"],
                folder_type=folder_data["folder_type"],
                label=folder_data["label"],
                parent=parent,
                data={"description": folder_data["description"]} if folder_data["description"] else {}
            )

    def ingest_from_file(self, project_name: str, filepath: str):
        """Convenience method to ingest from a file path."""
        with open(filepath, 'r', encoding='utf-8-sig') as f:
            content = f.read()
        folders = self.parse_csv(content)
        self.create_folders(project_name, folders)
