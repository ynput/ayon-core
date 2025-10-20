from ayon_applications import PreLaunchHook

from ayon_core.pipeline.colorspace import get_imageio_config_preset
from ayon_core.pipeline.template_data import get_template_data


class OCIOEnvHook(PreLaunchHook):
    """Set OCIO environment variable for hosts that use OpenColorIO."""

    order = 0
    hosts = {
        "substancepainter",
        "substancedesigner",
        "fusion",
        "blender",
        "aftereffects",
        "max",
        "houdini",
        "maya",
        "nuke",
        "hiero",
        "resolve",
        "openrv",
        "cinema4d",
        "silhouette",
        "gaffer",
        "loki",
    }
    launch_types = set()

    def execute(self):
        """Hook entry method."""

        task_entity = self.data.get("task_entity")

        if not task_entity:
            self.log.info(
                "Skipping OCIO Environment preparation."
                "Task Entity is not available."
            )
            return

        folder_entity = self.data["folder_entity"]

        template_data = get_template_data(
            self.data["project_entity"],
            folder_entity=folder_entity,
            task_entity=self.data["task_entity"],
            host_name=self.host_name,
            settings=self.data["project_settings"],
        )

        config_data = get_imageio_config_preset(
            self.data["project_name"],
            self.data["folder_path"],
            self.data["task_name"],
            self.host_name,
            anatomy=self.data["anatomy"],
            project_settings=self.data["project_settings"],
            template_data=template_data,
            env=self.launch_context.env,
            folder_id=folder_entity["id"],
        )

        if not config_data:
            self.log.debug("OCIO not set or enabled")
            return

        ocio_path = config_data["path"]

        if self.host_name in ["nuke", "hiero"]:
            ocio_path = ocio_path.replace("\\", "/")

        self.log.info(
            f"Setting OCIO environment to config path: {ocio_path}")

        self.launch_context.env["OCIO"] = ocio_path
