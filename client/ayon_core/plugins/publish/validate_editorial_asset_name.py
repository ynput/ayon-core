from pprint import pformat

import ayon_api
import pyblish.api

from ayon_core.pipeline import KnownPublishError


class ValidateEditorialAssetName(pyblish.api.ContextPlugin):
    """ Validating if editorial's folder names are not already created in db.

    Checking variations of names with different size of caps or with
    or without underscores.
    """

    order = pyblish.api.ValidatorOrder
    label = "Validate Editorial Folder Name"
    hosts = [
        "hiero",
        "resolve",
        "flame",
        "traypublisher"
    ]

    def process(self, context):

        folder_and_parents = self.get_parents(context)
        self.log.debug("__ folder_and_parents: {}".format(folder_and_parents))

        project_name = context.data["projectName"]
        folder_entities = list(ayon_api.get_folders(
            project_name, fields={"path"}
        ))
        self.log.debug("__ folder_entities: {}".format(folder_entities))

        existing_folder_paths = {
            folder_entity["path"]: (
                folder_entity["path"].lstrip("/").rsplit("/")[0]
            )
            for folder_entity in folder_entities
        }

        self.log.debug("__ project_entities: {}".format(
            pformat(existing_folder_paths)))

        folders_missing_name = {}
        folders_wrong_parent = {}
        for folder_path in folder_and_parents.keys():
            if folder_path not in existing_folder_paths.keys():
                # add to some nonexistent list for next layer of check
                folders_missing_name[folder_path] = (
                    folder_and_parents[folder_path]
                )
                continue

            existing_parents = existing_folder_paths[folder_path]
            if folder_and_parents[folder_path] != existing_parents:
                # add to some nonexistent list for next layer of check
                folders_wrong_parent[folder_path] = {
                    "required": folder_and_parents[folder_path],
                    "already_in_db": existing_folder_paths[folder_path]
                }
                continue

            self.log.debug("correct folder: {}".format(folder_path))

        if folders_missing_name:
            wrong_names = {}
            self.log.debug(
                ">> folders_missing_name: {}".format(folders_missing_name))

            # This will create set of folder paths
            folder_paths = {
                folder_path.lower().replace("_", "")
                for folder_path in existing_folder_paths
            }

            for folder_path in folders_missing_name:
                _folder_path = folder_path.lower().replace("_", "")
                if _folder_path in folder_paths:
                    wrong_names[folder_path].update(
                        {
                            "required_name": folder_path,
                            "used_variants_in_db": [
                                p
                                for p in existing_folder_paths
                                if p.lower().replace("_", "") == _folder_path
                            ]
                        }
                    )

            if wrong_names:
                self.log.debug(
                    ">> wrong_names: {}".format(wrong_names))
                raise Exception(
                    "Some already existing folder name variants `{}`".format(
                        wrong_names))

        if folders_wrong_parent:
            self.log.debug(
                ">> folders_wrong_parent: {}".format(folders_wrong_parent))
            raise KnownPublishError(
                "Wrong parents on folders `{}`".format(folders_wrong_parent))

    def get_parents(self, context):
        output = {}
        for instance in context:
            folder_path = instance.data["folderPath"]
            families = instance.data.get("families", []) + [
                instance.data["family"]
            ]
            # filter out non-shot families
            if "shot" not in families:
                continue

            parents = instance.data["parents"]

            output[folder_path] = [
                str(p["entity_name"]) for p in parents
                if p["entity_type"].lower() != "project"
            ]
        return output
