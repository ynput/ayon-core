import csv
import re
import pyblish.api
from ayon_core.pipeline import registered_host


class CollectCsvInstances(pyblish.api.ContextPlugin):
    """Collect instances from a CSV file.

    The CSV file should have at least a 'path' column pointing to the
    representation file. Additional columns can be 'name', 'label',
    'folderType', 'description', and any other custom attributes.
    """

    order = pyblish.api.CollectorOrder
    label = "Collect CSV Instances"

    def process(self, context):
        host = registered_host()
        current_file = host.get_current_file()
        if not current_file or not current_file.lower().endswith('.csv'):
            return

        with open(current_file, 'r') as csvfile:
            reader = csv.DictReader(csvfile)
            for row in reader:
                path = row.get('path')
                if not path:
                    continue

                name = row.get('name', '')
                label = row.get('label', name or path)
                folder_type = row.get('folderType', 'Folder')
                description = row.get('description', '')

                # Create instance
                instance = context.create_instance(name or path)
                instance.data['family'] = 'csv.folder'
                instance.data['folderPath'] = path
                instance.data['folderName'] = name or path
                instance.data['folderLabel'] = label
                instance.data['folderType'] = folder_type
                instance.data['folderDescription'] = description
                instance.data['publish'] = True
                instance.data['representations'] = []

                # Collect any custom attributes
                for key, value in row.items():
                    if key not in ('path', 'name', 'label', 'folderType', 'description'):
                        instance.data[key] = value

        self.log.info("Collected {} instances from CSV".format(
            len(list(context)) if context else 0
        ))
