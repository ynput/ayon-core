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


class RepairOverrideResolution(RepairAction):
    """ Repair, force new resolution onto existing shot.
    """
    label = "Force new shot resolution."

    def process(self, context, plugin):
        values = ValidateFolderCreationResolution.get_shot_data(
            context.data["hierarchyContext"]
        )
        entity_hub, entity, shot_data = values

        for attrib in _RESOLUTION_ATTRIBS:
            entity.attribs.set(attrib, shot_data[attrib])

        entity_hub.commit_changes()


class RepairIgnoreResolution(RepairAction):
    """ Repair, disable resolution update in problematic instance(s).
    """
    label = "Do not update resolution."

    def process(self, context, plugin):
        create_context = context.data["create_context"]
        for inst in get_errored_instances_from_context(context, plugin=plugin):
            instance_id = inst.data.get("instance_id")
            created_instance = create_context.get_instance_by_id(instance_id)
            attr_values = created_instance.data["publish_attributes"].get(
                "ValidateFolderCreationResolution", {})
            attr_values["updateExistingFolderResolution"] = False

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
    actions = [RepairIgnoreResolution, RepairOverrideResolution]

    @classmethod
    def get_shot_data(self, hierarchy_context):
        """ Retrieve matching entity and shot_data from hierarchy_context.
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

                if entity and child:
                    entity_children = {
                        child.name: child
                        for child in entity.children
                    }
                    entity_to_inspect.append((entity_children, child))

                # Destination shot already exists return for validation.
                elif (
                    value.get("folder_type") == "Shot"
                    and entity and not child
                ):
                    shot_data = value.get("attributes", {})
                    return entity_hub, entity, shot_data

        return None

    def process(self, instance):
        """ Validate existing shot resolution.
        """
        try:
            hierarchy_context = instance.context.data["hierarchyContext"]

        except KeyError:
            self.log.info("No hierarchy context defined for shot instance.")
            return

        validation_data = self.get_shot_data(hierarchy_context)
        if not validation_data:
            self.log.info(
                "Destination shot does not exist yet, "
                "nothing to validate."
            )
            return

        values = self.get_attr_values_from_data(instance.data)
        _, entity, shot_data = validation_data

        # Validate existing shot resolution is matching new one
        # ask for confirmation instead of blind update, this prevents mistakes.
        if values.get("updateExistingFolderResolution", True):
            for resolution_attrib in _RESOLUTION_ATTRIBS:
                shot_value = shot_data.get(resolution_attrib)
                entity_value = entity.attribs.get(resolution_attrib)
                if shot_value and shot_value != entity_value:
                    raise PublishValidationError(
                        "Resolution mismatch for shot."
                        f"{resolution_attrib}={shot_value} but "
                        f"already existing shot is set to {entity_value}."
                    )

        # If update existing shot is disabled, remove any resolution attribs.
        else:
            for resolution_attrib in _RESOLUTION_ATTRIBS:
                shot_data.pop(resolution_attrib, None)

            self.log.info(
                "Ignore existing shot resolution validation "
                "(update is disabled)."
            )

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context, instance,
    ):
        if instance.product_type not in cls.families:
            return []

        return [
            BoolDef(
                "updateExistingFolderResolution",
                default=True,
                label="Update existing shot resolution.",
            ),
        ]
