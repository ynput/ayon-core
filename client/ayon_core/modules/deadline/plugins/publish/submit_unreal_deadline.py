import os
import attr
import getpass
import pyblish.api
from datetime import datetime

from ayon_core.lib import (
    env_value_to_bool,
    collect_frames,
    is_in_tests,
)
from openpype_modules.deadline import abstract_submit_deadline
from openpype_modules.deadline.abstract_submit_deadline import DeadlineJobInfo


@attr.s
class DeadlinePluginInfo():
    ProjectFile = attr.ib(default=None)
    EditorExecutableName = attr.ib(default=None)
    EngineVersion = attr.ib(default=None)
    CommandLineMode = attr.ib(default=True)
    OutputFilePath = attr.ib(default=None)
    Output = attr.ib(default=None)
    StartupDirectory = attr.ib(default=None)
    CommandLineArguments = attr.ib(default=None)
    MultiProcess = attr.ib(default=None)
    PerforceStream = attr.ib(default=None)
    PerforceChangelist = attr.ib(default=None)
    PerforceGamePath = attr.ib(default=None)


class UnrealSubmitDeadline(
    abstract_submit_deadline.AbstractSubmitDeadline
):
    """Supports direct rendering of prepared Unreal project on Deadline
    (`render` product must be created with flag for Farm publishing) OR
    Perforce assisted rendering.

    For this Ayon server must contain `ayon-version-control` addon and provide
    configuration for it (P4 credentials etc.)!
    """

    label = "Submit Unreal to Deadline"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["unreal"]
    families = ["render.farm"]  # cannot be "render' as that is integrated
    use_published = True
    targets = ["local"]

    priority = 50
    chunk_size = 1000000
    group = None
    department = None
    multiprocess = True

    def get_job_info(self):
        dln_job_info = DeadlineJobInfo(Plugin="UnrealEngine5")

        context = self._instance.context

        batch_name = self._get_batch_name()
        dln_job_info.Name = self._instance.data["name"]
        dln_job_info.BatchName = batch_name
        dln_job_info.Plugin = "UnrealEngine5"
        dln_job_info.UserName = context.data.get(
            "deadlineUser", getpass.getuser())
        if self._instance.data["frameEnd"] > self._instance.data["frameStart"]:
            # Deadline requires integers in frame range
            frame_range = "{}-{}".format(
                int(round(self._instance.data["frameStart"])),
                int(round(self._instance.data["frameEnd"])))
            dln_job_info.Frames = frame_range

        dln_job_info.Priority = self.priority
        dln_job_info.Pool = self._instance.data.get("primaryPool")
        dln_job_info.SecondaryPool = self._instance.data.get("secondaryPool")
        dln_job_info.Group = self.group
        dln_job_info.Department = self.department
        dln_job_info.ChunkSize = self.chunk_size
        dln_job_info.OutputFilename += \
            os.path.basename(self._instance.data["file_names"][0])
        dln_job_info.OutputDirectory += \
            os.path.dirname(self._instance.data["expectedFiles"][0])
        dln_job_info.JobDelay = "00:00:00"

        keys = [
            "FTRACK_API_KEY",
            "FTRACK_API_USER",
            "FTRACK_SERVER",
            "AYON_PROJECT_NAME",
            "AYON_FOLDER_PATH",
            "AYON_TASK_NAME",
            "AYON_WORKDIR",
            "AYON_APP_NAME",
            "AYON_LOG_NO_COLORS",
            "IS_TEST",
        ]

        environment = {
            key: os.environ[key]
            for key in keys
            if key in os.environ
        }
        for key in keys:
            value = environment.get(key)
            if value:
                dln_job_info.EnvironmentKeyValue[key] = value

        dln_job_info.EnvironmentKeyValue["AYON_UNREAL_VERSION"] = (
            self._instance.data)["app_version"]

        # to recognize render jobs
        dln_job_info.add_render_job_env_var()

        return dln_job_info

    def get_plugin_info(self):
        deadline_plugin_info = DeadlinePluginInfo()

        render_path = self._instance.data["expectedFiles"][0]
        self._instance.data["outputDir"] = os.path.dirname(render_path)
        self._instance.context.data["version"] = 1  #TODO

        render_dir = os.path.dirname(render_path)
        file_name = self._instance.data["file_names"][0]
        render_path = os.path.join(render_dir, file_name)

        deadline_plugin_info.ProjectFile = self.scene_path
        deadline_plugin_info.Output = render_path.replace("\\", "/")

        deadline_plugin_info.ProjectFile = self.scene_path
        deadline_plugin_info.EditorExecutableName = "UnrealEditor-Cmd.exe"  # parse ayon+settings://applications/applications/unreal/variants/3/environmen
        deadline_plugin_info.EngineVersion = self._instance.data["app_version"]
        master_level = self._instance.data["master_level"]
        render_queue_path = self._instance.data["render_queue_path"]
        cmd_args = [f"{master_level} -game ",
                    f"-MoviePipelineConfig={render_queue_path}"]
        cmd_args.extend([
            "-windowed",
            "-Log",
            "-StdOut",
            "-allowStdOutLogVerbosity"
            "-Unattended"
        ])
        self.log.info(f"cmd-args::{cmd_args}")
        deadline_plugin_info.CommandLineArguments = " ".join(cmd_args)

        # if Perforce - triggered by active `publish_commit` instance!!
        collected_version_control = self._get_version_control()
        if collected_version_control:
            self._update_version_control_data(collected_version_control,
                                              deadline_plugin_info)

        return attr.asdict(deadline_plugin_info)

    def from_published_scene(self):
        """ Do not overwrite expected files.

            Use published is set to True, so rendering will be triggered
            from published scene (in 'publish' folder). Default implementation
            of abstract class renames expected (eg. rendered) files accordingly
            which is not needed here.
        """
        return super().from_published_scene(False)

    def _get_batch_name(self):
        """Returns value that differentiate jobs in DL.

        For automatic tests it adds timestamp, for Perforce driven change list
        """
        batch_name = os.path.basename(self._instance.data["source"])
        if is_in_tests():
            batch_name += datetime.now().strftime("%d%m%Y%H%M%S")
        collected_version_control = self._get_version_control()
        if collected_version_control:
            change = (collected_version_control["change_info"]
                                               ["change"])
            batch_name = f"{batch_name}_{change}"
        return batch_name

    def _get_version_control(self):
        """Look if publish_commit is published to get change list info.

        Context version_control contains universal connection info, instance
        version_control contains detail about change list.
        """
        change_list_version = {}
        for inst in self._instance.context:
            # get change info from `publish_commit` instance
            change_list_version = inst.data.get("version_control")
            if change_list_version:
                context_version = (
                    self._instance.context.data["version_control"])
                change_list_version.update(context_version)
                break
        return change_list_version

    def _update_version_control_data(self, collected_version_control,
                                     deadline_plugin_info):
        """Adds Perforce metadata which causes DL pre job to sync to change.

        It triggers only in presence of activated `publish_commit` instance,
        which materialize info about commit. Artists could return to any
        published commit and re-render if they choose.
        `publish_commit` replaces `workfile` as there are no versioned Unreal
        projects (because of size).
        """
        self.log.info(f"collected_version_control::{collected_version_control}")

        unreal_project_file_name = os.path.basename(self.scene_path)
        version_control_data = self._instance.context.data["version_control"]
        workspace_dir = version_control_data["workspace_dir"]
        unreal_project_hierarchy = self.scene_path.replace(workspace_dir,
                                                           "")
        unreal_project_hierarchy = (
            unreal_project_hierarchy.replace(unreal_project_file_name, ""))
        unreal_project_hierarchy = unreal_project_hierarchy.strip("\\")

        deadline_plugin_info.ProjectFile = unreal_project_file_name

        deadline_plugin_info.PerforceStream = version_control_data["stream"]
        deadline_plugin_info.PerforceChangelist = collected_version_control[
            "change_info"]["change"]
        deadline_plugin_info.PerforceGamePath = unreal_project_hierarchy
