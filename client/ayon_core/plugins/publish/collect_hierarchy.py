import pyblish.api
import ayon_api

from ayon_core.lib import BoolDef
from ayon_core.pipeline import publish

SHOT_ATTRS = (
    "handleStart",
    "handleEnd",
    "frameStart",
    "frameEnd",
    "clipIn",
    "clipOut",
    "fps",
    "resolutionWidth",
    "resolutionHeight",
    "pixelAspect",
)


class CollectHierarchy(
    pyblish.api.ContextPlugin,
    publish.AYONPyblishPluginMixin,
):
    """Collecting hierarchy from `parents`.

    present in `clip` family instances coming from the request json data file

    It will add `hierarchical_context` into each instance for integrate
    plugins to be able to create needed parents for the context if they
    don't exist yet
    """

    label = "Collect Hierarchy"
    order = pyblish.api.CollectorOrder - 0.076
    settings_category = "core"

    edit_shot_attributes_on_update = True

    @classmethod
    def get_attr_defs_for_context(cls, create_context):
        return [
            BoolDef(
                "edit_shot_attributes_on_update",
                label="Edit shot attributes on update",
                default=cls.edit_shot_attributes_on_update
            )
        ]

    @classmethod
    def apply_settings(cls, project_settings):
        cls.edit_shot_attributes_on_update = (
            project_settings
                ["core"]
                ["CollectHierarchy"]
                ["edit_shot_attributes_on_update"]
        )

    def _get_shot_instances(self, context):
        """Get shot instances from context.

        Args:
            context (pyblish.api.Context): Context is a list of instances.

        Returns:
            list[pyblish.api.Instance]: A list of shot instances.
        """
        shot_instances = []
        for instance in context:
            # shot data dict
            product_base_type = instance.data.get("productBaseType")
            if not product_base_type:
                product_base_type = instance.data["productType"]
            families = instance.data["families"]

            # exclude other families then "shot" with intersection
            if "shot" not in (families + [product_base_type]):
                self.log.debug("Skipping not a shot: {}".format(families))
                continue

            # Skip if is not a hero track
            if not instance.data.get("heroTrack"):
                self.log.debug("Skipping not a shot from hero track")
                continue

            shot_instances.append(instance)

        return shot_instances

    def get_existing_folder_entities(self, project_name, shot_instances):
        """Get existing folder entities for given shot instances.

        Args:
            project_name (str): The name of the project.
            shot_instances (list[pyblish.api.Instance]): A list of shot
                instances.

        Returns:
            dict[str, dict]: A dictionary mapping folder paths to existing
                folder entities.
        """
        # first we need to get all folder paths from shot instances
        folder_paths = {
            instance.data["folderPath"]
            for instance in shot_instances
        }
        # then we get all existing folder entities with one request
        existing_entities = {
            folder_entity["path"]: folder_entity
            for folder_entity in ayon_api.get_folders(
                project_name, folder_paths=folder_paths, fields={"path"})
        }
        for folder_path in folder_paths:
            # add None value to non-existing folder entities
            existing_entities.setdefault(folder_path, None)

        return existing_entities

    def process(self, context):
        # get only shot instances from context
        shot_instances = self._get_shot_instances(context)

        if not shot_instances:
            return

        # get user input
        values = self.get_attr_values_from_data(context.data)
        edit_shot_attributes_on_update = values.get(
            "edit_shot_attributes_on_update", None)

        project_name = context.data["projectName"]
        final_context = {
            project_name: {
                "entity_type": "project",
                "children": {}
            },
        }
        temp_context = {}
        existing_entities = self.get_existing_folder_entities(
            project_name, shot_instances)

        for instance in shot_instances:
            folder_path = instance.data["folderPath"]
            self.log.debug(
                f"Processing instance: `{folder_path} {instance}` ...")

            shot_data = {
                "entity_type": "folder",
                # WARNING unless overwritten, default folder type is hardcoded
                #   to shot
                "folder_type": instance.data.get("folder_type") or "Shot",
                "tasks": instance.data.get("tasks") or {},
                "comments": instance.data.get("comments", []),
            }

            shot_data["attributes"] = {}
            # we need to check if the shot entity already exists
            # and if not the attributes needs to be added in case the option
            # is disabled by settings
            if (
                existing_entities.get(folder_path)
                and edit_shot_attributes_on_update
            ):
                for shot_attr in SHOT_ATTRS:
                    attr_value = instance.data.get(shot_attr)
                    if attr_value is None:
                        # Shot attribute might not be defined (e.g. CSV ingest)
                        self.log.debug(
                            "%s shot attribute is not defined for instance.",
                            shot_attr
                        )
                        continue

                    shot_data["attributes"][shot_attr] = attr_value
                else:
                    self.log.debug(
                        "Shot attributes will not be updated."
                    )

            # Split by '/' for AYON where asset is a path
            name = folder_path.split("/")[-1]
            actual = {name: shot_data}

            for parent in reversed(instance.data["parents"]):
                next_dict = {
                    parent["entity_name"]: {
                        "entity_type": "folder",
                        "folder_type": parent["folder_type"],
                        "children": actual,
                    }
                }
                actual = next_dict

            temp_context = self._update_dict(temp_context, actual)

        # skip if nothing for hierarchy available
        if not temp_context:
            return

        final_context[project_name]["children"] = temp_context

        # adding hierarchy context to context
        context.data["hierarchyContext"] = final_context
        self.log.debug("context.data[hierarchyContext] is: {}".format(
            context.data["hierarchyContext"]))

    def _update_dict(self, parent_dict, child_dict):
        """Nesting each child into its parent.

        Args:
            parent_dict (dict): parent dict that should be nested with children
            child_dict (dict): children dict which should be ingested
        """

        for key in parent_dict:
            if key in child_dict and isinstance(parent_dict[key], dict):
                child_dict[key] = self._update_dict(
                    parent_dict[key], child_dict[key]
                )
            else:
                if parent_dict.get(key) and child_dict.get(key):
                    continue
                else:
                    child_dict[key] = parent_dict[key]

        return child_dict
