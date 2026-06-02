import time

import ayon_api
import pyblish.api


class IntegrateVersionToList(pyblish.api.ContextPlugin):
    """Integrate published versions to a list

    This plugin integrates published versions to a list in the server.
    """

    label = "Integrate Versions to List"
    order = pyblish.api.IntegratorOrder + 0.49

    def process(self, context):
        # formatted timestamp YYYYMMDD-HHMMSS
        # e.g. 20230101-120000
        timestamp = time.strftime("%Y%m%d-%H%M%S")
        project_name = context.data["projectName"]
        list_name_mapping = {}
        list_tags: list[str] = []
        for instance in context:
            version_entity = instance.data.get("versionEntity")
            if not version_entity:
                continue
            list_name = instance.data.get("addToListName")
            if list_name:
                list_tags = instance.data.get("addToListTags", [])
                list_name = f"{list_name}_{timestamp}"
                list_name_mapping[list_name] = [
                    *list_name_mapping.get(list_name, []),
                    version_entity["id"]
                ]

        for list_label, version_ids in list_name_mapping.items():
            ayon_api.create_entity_list(
                project_name=project_name,
                entity_type="version",
                label=list_label,
                items=[{"entityId": version_id} for version_id in version_ids],
                tags=list_tags,
            )
