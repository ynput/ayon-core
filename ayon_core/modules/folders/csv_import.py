# -*- coding: utf-8 -*-
"""CSV import for folders."""

import csv
import io

import ayon_api


def import_folders_from_csv(project_name, csv_content, user=None):
    """Import folders from CSV content.

    Args:
        project_name (str): Project name.
        csv_content (str): CSV data as string.
        user (str, optional): User name for audit.

    Returns:
        list[dict]: Created folder info.
    """
    reader = csv.DictReader(io.StringIO(csv_content))
    fields = reader.fieldnames

    # Required columns
    required = ["path", "label"]
    for col in required:
        if col not in fields:
            raise ValueError(f"Missing required column: {col}")

    created = []
    for row in reader:
        path = row["path"].strip()
        label = row["label"].strip()

        # Support optional description column
        description = row.get("description", "").strip()

        if not path or not label:
            continue

        folder_data = {
            "path": path,
            "label": label,
        }
        if description:
            folder_data["description"] = description

        folder = ayon_api.create_folder(project_name, folder_data, user=user)
        created.append(folder)

    return created


def validate_csv_structure(csv_content):
    """Validate CSV structure for folder import.

    Args:
        csv_content (str): CSV data as string.

    Returns:
        dict: Validation result with errors.
    """
    errors = []
    reader = csv.DictReader(io.StringIO(csv_content))
    fields = reader.fieldnames

    if not fields:
        errors.append("CSV has no columns.")
    else:
        for col in ["path", "label"]:
            if col not in fields:
                errors.append(f"Missing required column: {col}")
        # Optional columns: description (no error if missing)

    return {"valid": len(errors) == 0, "errors": errors}
