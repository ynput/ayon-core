import pyblish.api
from ayon_core.pipeline import PublishValidationError


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
