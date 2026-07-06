# -*- coding: utf-8 -*-
"""CSV reader for editorial ingest."""

import csv
import logging

from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


class CSVReader:
    """Read CSV files for editorial ingest, supporting folder description."""

    def __init__(self, filepath, delimiter=","):
        self.filepath = filepath
        self.delimiter = delimiter
        self.data = []
        self.errors = []

    def read(self):
        """Parse CSV file and return list of folder dicts."""
        with open(self.filepath, "r") as csvfile:
            reader = csv.DictReader(csvfile, delimiter=self.delimiter)
            for row in reader:
                folder = self._process_row(row)
                if folder:
                    self.data.append(folder)
        return self.data

    def _process_row(self, row):
        """Convert a CSV row into a folder dictionary.

        Expected columns (case-insensitive):
            - name (required)
            - parent (optional)
            - label (optional)
            - description (optional)

        Returns:
            dict: Folder info with keys 'name', 'parent', 'label', 'description'.
        """
        folder = {}
        name = row.get("name")
        if not name:
            self.errors.append(f"Missing 'name' in row: {row}")
            log.warning("Missing 'name', skipping row.")
            return None

        folder["name"] = name.strip()

        parent = row.get("parent")
        if parent:
            folder["parent"] = parent.strip()

        label = row.get("label")
        if label:
            folder["label"] = label.strip()

        description = row.get("description")
        if description:
            folder["description"] = description.strip()

        return folder

    def get_errors(self):
        """Return list of parsing errors."""
        return self.errors


# Example usage:
if __name__ == "__main__":
    import sys
    reader = CSVReader(sys.argv[1])
    folders = reader.read()
    for f in folders:
        print(f)
    if reader.errors:
        print("Errors:", reader.errors)
