# ... (existing imports and code)

class CSVFolderIngestPlugin(BaseIngestPlugin):
    """Plugin for ingesting folders from CSV."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.folder_description_column = None

    def set_attributes_from_row(self, row, folder_entity):
        """Set folder attributes from a CSV row."""
        super().set_attributes_from_row(row, folder_entity)

        # Handle folder description if column is defined
        if self.folder_description_column and self.folder_description_column in row:
            description = row[self.folder_description_column].strip()
            if description:
                folder_entity["attrib"]["description"] = description

    def parse_column_mapping(self, column_mapping):
        """Parse column mapping including optional folder description."""
        super().parse_column_mapping(column_mapping)
        self.folder_description_column = column_mapping.get("folder_description")

    def row_to_folder(self, row, parent_folder):
        """Convert a CSV row to a folder dictionary."""
        folder = super().row_to_folder(row, parent_folder)
        # Folder already has attributes from set_attributes_from_row
        return folder

# ... (rest of the plugin)