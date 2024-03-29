from ayon_core.lib.applications import PreLaunchHook

from ayon_core.pipeline.colorspace import get_imageio_config
from ayon_core.pipeline.template_data import get_template_data_with_names


class OCIOEnvHook(PreLaunchHook):
    """Set OCIO environment variable for hosts that use OpenColorIO."""

    order = 0
    hosts = {
        "substancepainter",
        "fusion",
        "blender",
        "aftereffects",
        "3dsmax",
        "houdini",
        "maya",
        "nuke",
        "hiero",
        "resolve",
        "openrv"
    }
    launch_types = set()

    def execute(self):
        """Hook entry method."""

        # bit lost here tbh.
        # don't know which key to use in replacement for "project_settings"
        # using "project_entity" fails with this error:
        # File "<REDACT>\ayon-core\client\ayon_core\pipeline\template_data.py", line 21, in get_general_template_data
        # core_settings = settings[ "core" ]
        # if not self.data.get("project_settings"):
        #     self.log.error("Missing project settings data")
        #     return

        template_data = get_template_data_with_names(
            project_name=self.data["project_name"],
            folder_path=self.data["folder_path"],
            task_name=self.data["task_name"],
            host_name=self.host_name,
            settings=self.data["project_settings"]
        )

        config_data = get_imageio_config(
            project_name=self.data["project_name"],
            host_name=self.host_name,
            project_settings=self.data["project_settings"],
            anatomy_data=template_data,
            anatomy=self.data["anatomy"],
            env=self.launch_context.env,
        )

        if config_data:
            ocio_path = config_data["path"]

            if self.host_name in ["nuke", "hiero"]:
                ocio_path = ocio_path.replace("\\", "/")

            self.log.info(
                f"Setting OCIO environment to config path: {ocio_path}")

            self.launch_context.env["OCIO"] = ocio_path
        else:
            self.log.debug("OCIO not set or enabled")
