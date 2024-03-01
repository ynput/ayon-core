import pyblish.api
from ayon_core.pipeline.publish import ValidateContentsOrder
from ayon_core.pipeline.publish import (
    PublishXmlValidationError,
    get_publish_template_name,
)


class ValidatePublishDir(pyblish.api.InstancePlugin):
    """Validates if files are being published into a project directory

    In specific cases ('source' template - in place publishing) source folder
    of published items is used as a regular `publish` dir.
    This validates if it is inside any project dir for the project.
    (eg. files are not published from local folder, inaccessible for studio')

    """

    order = ValidateContentsOrder
    label = "Validate publish dir"

    checked_template_names = ["source"]
    # validate instances might have interim family, needs to be mapped to final
    product_type_mapping = {
        "renderLayer": "render",
        "renderLocal": "render"
    }

    def process(self, instance):

        template_name = self._get_template_name_from_instance(instance)

        if template_name not in self.checked_template_names:
            return

        original_dirname = instance.data.get("originalDirname")
        if not original_dirname:
            raise PublishXmlValidationError(
                self,
                "Instance meant for in place publishing."
                " Its 'originalDirname' must be collected."
                " Contact AYON developer to modify collector."
            )

        anatomy = instance.context.data["anatomy"]

        # original_dirname must be convertable to rootless path
        # in other case it is path inside of root folder for the project
        success, _ = anatomy.find_root_template_from_path(original_dirname)
        if not success:
            raise PublishXmlValidationError(
                plugin=self,
                message=(
                    "Path '{}' not in project folder. Please publish from "
                    "inside of project folder.".format(original_dirname)
                ),
                key="not_in_dir",
                formatting_data={"original_dirname": original_dirname}
            )

    def _get_template_name_from_instance(self, instance):
        """Find template which will be used during integration."""
        project_name = instance.context.data["projectName"]
        host_name = instance.context.data["hostName"]
        product_type = instance.data["productType"]
        mapped_product_type = (
            self.product_type_mapping.get(product_type) or product_type
        )
        anatomy_data = instance.data["anatomyData"]
        task_info = anatomy_data.get("task") or {}

        return get_publish_template_name(
            project_name,
            host_name,
            mapped_product_type,
            task_name=task_info.get("name"),
            task_type=task_info.get("type"),
            project_settings=instance.context.data["project_settings"],
            logger=self.log
        )
