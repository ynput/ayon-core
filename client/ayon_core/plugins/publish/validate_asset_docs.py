import pyblish.api

from ayon_api.entity_hub import EntityHub

from ayon_core.lib import BoolDef
from ayon_core.pipeline.publish import (
    PublishValidationError,
    RepairAction,
    get_errored_instances_from_context,
    AYONPyblishPluginMixin
)


_RESOLUTION_ATTRIBS = ("resolutionHeight", "resolutionWidth", "pixelAspect")


class ValidateFolderEntities(pyblish.api.InstancePlugin):
    """Validate existence of folder entity on instances.

    Without folder entity it is not possible to publish the instance.

    If context has set folder entity the validation is skipped.

    Plugin was added because there are cases when context folder is not
    defined e.g. in tray publisher.
    """

    label = "Validate Folder entities"
    order = pyblish.api.ValidatorOrder

    def process(self, instance):
        context_folder_entity = instance.context.data.get("folderEntity")
        if context_folder_entity:
            return

        if instance.data.get("folderEntity"):
            self.log.debug("Instance has set fodler entity in its data.")

        elif (
            instance.data.get("newHierarchyIntegration")
            # Backwards compatible (Deprecated since 24/06/06)
            or instance.data.get("newAssetPublishing")
        ):
            # skip if it is editorial
            self.log.debug("Editorial instance has no need to check...")

        else:
            raise PublishValidationError((
                "Instance \"{}\" doesn't have folder entity "
                "set which is needed for publishing."
            ).format(instance.data["name"]))


class RepairIgnoreResolution(RepairAction):
    """ Repair, disable resolution update in problematic instance(s).
    """
    label = "Skip folder resolution validation."

    def process(self, context, plugin):
        create_context = context.data["create_context"]
        for inst in get_errored_instances_from_context(context, plugin=plugin):
            instance_id = inst.data.get("instance_id")
            created_instance = create_context.get_instance_by_id(instance_id)
            attr_values = created_instance.data["publish_attributes"].get(
                "ValidateFolderCreationResolution", {})
            attr_values["validateExistingFolderResolution"] = False

        create_context.save_changes()


class ValidateFolderCreationResolution(
        pyblish.api.InstancePlugin,
        AYONPyblishPluginMixin
    ):
    """ Validate resolution values before updating an existing folder.
    """

    label = "Validate new folder resolution"
    order = pyblish.api.ValidatorOrder
    families = ["shot"]
    actions = [RepairIgnoreResolution]

    def _validate_hierarchy_resolution(self, hierarchy_context):
        """ Deep validation of hierarchy_context resolution.
        """
        project_name = tuple(hierarchy_context.keys())[0]
        entity_hub = EntityHub(project_name)
        entity_data = {project_name: entity_hub.project_entity}
        entity_to_inspect = [(entity_data, hierarchy_context)]

        while entity_to_inspect:
            entity_data, data = entity_to_inspect.pop(0)

            for name, value in data.items():
                entity = entity_data.get(name)
                child = value.get("children", None)

                # entity exists in AYON.
                if entity:
                    folder_data = value.get("attributes", {})
                    self._validate_folder_resolution(
                        folder_data,
                        entity,
                    )

                    if child:
                        entity_children = {
                            chld.name: chld
                            for chld in entity.children
                        }
                        entity_to_inspect.append((entity_children, child))

    def _validate_folder_resolution(self, folder_data, entity):
        """ Validate folder resolution against existing data.
        """
        similar = True
        for resolution_attrib in _RESOLUTION_ATTRIBS:
            folder_value = folder_data.get(resolution_attrib)
            entity_value = entity.attribs.get(resolution_attrib)
            if folder_value and folder_value != entity_value:
                self.log.warning(
                    f"Resolution mismatch for folder {entity.name}. "
                    f"{resolution_attrib}={folder_value} but "
                    f" existing entity is set to {entity_value}."
                )
                similar = False

        if not similar:
            resolution_data = {
                key: value
                for key, value in folder_data.items()
                if key in _RESOLUTION_ATTRIBS
            }
            raise PublishValidationError(
                "Resolution mismatch for "
                f"folder {entity.name} (type: {entity.folder_type}) "
                f"{resolution_data} does not "
                "correspond to existing entity."
            )

    def process(self, instance):
        """ Validate existing folder resolution.
        """
        values = self.get_attr_values_from_data(instance.data)
        if not values.get("validateExistingFolderResolution", False):
            self.log.debug("Skip existing folder(s) resolution validation ")
            return

        hierarchy_context = instance.context.data.get("hierarchyContext")
        if not hierarchy_context:
            self.log.debug("No hierarchy context defined for instance.")
            return

        self._validate_hierarchy_resolution(hierarchy_context)

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context, instance,
    ):
        if not cls.instance_matches_plugin_families(instance):
            return []

        return [
            BoolDef(
                "validateExistingFolderResolution",
                default=False,
                label="Validate existing folders resolution",
            ),
        ]
