import csv
import pyblish.api
from ayon_core.pipeline import publish


class ExtractCSV(publish.Extractor):
    """Extract CSV data into AYON entities."""

    label = "Extract CSV"
    order = pyblish.api.ExtractorOrder
    families = ["csv.ingest"]

    def process(self, instance):
        csv_path = instance.data.get("csvPath")
        if not csv_path:
            raise ValueError("CSV path not found in instance.")

        mapping = instance.data.get("columnMapping", {})
        with open(csv_path, newline='') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                self._process_row(row, mapping, instance)

    def _process_row(self, row, mapping, instance):
        # Extract folder fields from mapping
        folder_name_col = mapping.get("folderName", "folderName")
        folder_description_col = mapping.get("folderDescription", "folderDescription")
        parent_col = mapping.get("parent", "parent")

        folder_name = row.get(folder_name_col, "").strip()
        if not folder_name:
            return

        folder_description = row.get(folder_description_col, "").strip()
        parent_name = row.get(parent_col, "").strip()

        # Create folder
        project = instance.context.data["projectEntity"]
        folder_data = {
            "name": folder_name,
            "parent": parent_name,
        }
        if folder_description:
            folder_data["description"] = folder_description

        # Call AYON API to create folder
        # This is a placeholder for actual API call
        self.log.info(f"Creating folder: {folder_data}")
        # folder_entity = project.create_folder(**folder_data)
