import csv
import io
from ayon_core.addons.core.integrations.base import BaseIngest


class CSVFolderIngest(BaseIngest):
    """Ingest folders from CSV file, supporting description column."""

    def __init__(self, addon):
        super().__init__(addon)
        self._field_mapping = {
            "name": "name",
            "label": "label",
            "parent": "parent",
            "folder_type": "folder_type",
            "description": "description",
        }

    def _parse_csv(self, csv_content):
        reader = csv.DictReader(io.StringIO(csv_content))
        folders = []
        for row in reader:
            folder = {}
            for csv_col, field in self._field_mapping.items():
                value = row.get(csv_col, "")
                if field == "description":
                    folder[field] = value
                elif value:
                    folder[field] = value
            if "name" not in folder:
                raise ValueError("Missing 'name' column in CSV")
            folders.append(folder)
        return folders

    def ingest(self, project_name, csv_content, parent_folder_id=None):
        folders = self._parse_csv(csv_content)
        created_folders = []
        for folder_data in folders:
            # Ensure parent folder reference
            if parent_folder_id:
                folder_data["parent_id"] = parent_folder_id
            # Create folder via AYON API
            folder = self.addon.create_folder(project_name, folder_data)
            created_folders.append(folder)
        return created_folders
