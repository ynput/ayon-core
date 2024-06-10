# -*- coding: utf-8 -*-
"""Submitting render job to RoyalRender."""
import os
import json
import re
import tempfile
import uuid
from datetime import datetime

import pyblish.api

from ayon_core.lib import (
    BoolDef,
    NumberDef,
    is_running_from_build,
    is_in_tests,
)
from ayon_core.lib.execute import run_ayon_launcher_process
from ayon_royalrender.api import Api as rrApi
from ayon_royalrender.rr_job import (
    CustomAttribute,
    RRJob,
    RREnvList,
    get_rr_platform,
)
from ayon_core.pipeline import AYONPyblishPluginMixin
from ayon_core.pipeline.publish import KnownPublishError
from ayon_core.pipeline.publish.lib import get_published_workfile_instance


class BaseCreateRoyalRenderJob(pyblish.api.InstancePlugin,
                               AYONPyblishPluginMixin):
    """Creates separate rendering job for Royal Render"""
    label = "Create Nuke Render job in RR"
    order = pyblish.api.IntegratorOrder + 0.1
    hosts = ["nuke"]
    families = ["render", "prerender"]
    targets = ["local"]
    optional = True

    priority = 50
    chunk_size = 1
    concurrent_tasks = 1
    use_gpu = True
    use_published = True

    @classmethod
    def get_attribute_defs(cls):
        return [
            NumberDef(
                "priority",
                label="Priority",
                default=cls.priority,
                decimals=0
            ),
            NumberDef(
                "chunk",
                label="Frames Per Task",
                default=cls.chunk_size,
                decimals=0,
                minimum=1,
                maximum=1000
            ),
            NumberDef(
                "concurrency",
                label="Concurrency",
                default=cls.concurrent_tasks,
                decimals=0,
                minimum=1,
                maximum=10
            ),
            BoolDef(
                "use_gpu",
                default=cls.use_gpu,
                label="Use GPU"
            ),
            BoolDef(
                "suspend_publish",
                default=False,
                label="Suspend publish"
            ),
            BoolDef(
                "use_published",
                default=cls.use_published,
                label="Use published workfile"
            )
        ]

    def __init__(self, *args, **kwargs):
        self._rr_root = None
        self.scene_path = None
        self.job = None
        self.submission_parameters = None
        self.rr_api = None

    def process(self, instance):
        if not instance.data.get("farm"):
            self.log.info("Skipping local instance.")
            return

        instance.data["attributeValues"] = self.get_attr_values_from_data(
            instance.data)

        # add suspend_publish attributeValue to instance data
        instance.data["suspend_publish"] = instance.data["attributeValues"][
            "suspend_publish"]

        context = instance.context

        self._rr_root = instance.data.get("rr_root")
        if not self._rr_root:
            raise KnownPublishError(
                ("Missing RoyalRender root. "
                 "You need to configure RoyalRender module."))

        self.rr_api = rrApi(self._rr_root)

        self.scene_path = context.data["currentFile"]
        if self.use_published:
            published_workfile = get_published_workfile_instance(context)

            # fallback if nothing was set
            if published_workfile is None:
                self.log.warning("Falling back to workfile")
                file_path = context.data["currentFile"]
            else:
                workfile_repre = published_workfile.data["representations"][0]
                file_path = workfile_repre["published_path"]

            self.scene_path = file_path
            self.log.info(
                "Using published scene for render {}".format(self.scene_path)
            )

        if not instance.data.get("expectedFiles"):
            instance.data["expectedFiles"] = []

        if not instance.data.get("rrJobs"):
            instance.data["rrJobs"] = []

    def get_job(self, instance, script_path, render_path, node_name):
        """Get RR job based on current instance.

        Args:
            script_path (str): Path to Nuke script.
            render_path (str): Output path.
            node_name (str): Name of the render node.

        Returns:
            RRJob: RoyalRender Job instance.

        """
        start_frame = int(instance.data["frameStartHandle"])
        end_frame = int(instance.data["frameEndHandle"])

        batch_name = os.path.basename(script_path)
        jobname = "%s - %s" % (batch_name, instance.name)
        if is_in_tests():
            batch_name += datetime.now().strftime("%d%m%Y%H%M%S")

        render_dir = os.path.normpath(os.path.dirname(render_path))
        output_filename_0 = self.pad_file_name(render_path, str(start_frame))
        file_name, file_ext = os.path.splitext(
            os.path.basename(output_filename_0))

        custom_attributes = []
        if is_running_from_build():
            custom_attributes = [
                CustomAttribute(
                    name="OpenPypeVersion",
                    value=os.environ.get("OPENPYPE_VERSION"))
            ]

        # this will append expected files to instance as needed.
        expected_files = self.expected_files(
            instance, render_path, start_frame, end_frame)
        instance.data["expectedFiles"].extend(expected_files)

        job = RRJob(
            Software="",
            Renderer="",
            SeqStart=int(start_frame),
            SeqEnd=int(end_frame),
            SeqStep=int(instance.data.get("byFrameStep", 1)),
            SeqFileOffset=0,
            Version=0,
            SceneName=script_path,
            IsActive=True,
            ImageDir=render_dir.replace("\\", "/"),
            ImageFilename=file_name,
            ImageExtension=file_ext,
            ImagePreNumberLetter="",
            ImageSingleOutputFile=False,
            SceneOS=get_rr_platform(),
            Layer=node_name,
            SceneDatabaseDir=script_path,
            CustomSHotName=jobname,
            CompanyProjectName=instance.context.data["projectName"],
            ImageWidth=instance.data["resolutionWidth"],
            ImageHeight=instance.data["resolutionHeight"],
            CustomAttributes=custom_attributes
        )

        return job

    def update_job_with_host_specific(self, instance, job):
        """Host specific mapping for RRJob"""
        raise NotImplementedError

    def expected_files(self, instance, path, start_frame, end_frame):
        """Get expected files.

        This function generate expected files from provided
        path and start/end frames.

        It was taken from Deadline module, but this should be
        probably handled better in collector to support more
        flexible scenarios.

        Args:
            instance (Instance)
            path (str): Output path.
            start_frame (int): Start frame.
            end_frame (int): End frame.

        Returns:
            list: List of expected files.

        """
        dir_name = os.path.dirname(path)
        file = os.path.basename(path)

        expected_files = []

        if "#" in file:
            pparts = file.split("#")
            padding = "%0{}d".format(len(pparts) - 1)
            file = pparts[0] + padding + pparts[-1]

        if "%" not in file:
            expected_files.append(path)
            return expected_files

        if instance.data.get("slate"):
            start_frame -= 1

        expected_files.extend(
            os.path.join(dir_name, (file % i)).replace("\\", "/")
            for i in range(start_frame, (end_frame + 1))
        )
        return expected_files

    def pad_file_name(self, path, first_frame):
        """Return output file path with #### for padding.

        RR requires the path to be formatted with # in place of numbers.
        For example `/path/to/render.####.png`

        Args:
            path (str): path to rendered image
            first_frame (str): from representation to cleany replace with #
                padding

        Returns:
            str

        """
        self.log.debug("pad_file_name path: `{}`".format(path))
        if "%" in path:
            search_results = re.search(r"(%0)(\d)(d.)", path).groups()
            self.log.debug("_ search_results: `{}`".format(search_results))
            return int(search_results[1])
        if "#" in path:
            self.log.debug("already padded: `{}`".format(path))
            return path

        if first_frame:
            padding = len(first_frame)
            path = path.replace(first_frame, "#" * padding)

        return path

    def inject_environment(self, instance, job):
        # type: (pyblish.api.Instance, RRJob) -> RRJob
        """Inject environment variables for RR submission.

        This function mimics the behaviour of the Deadline
        integration. It is just temporary solution until proper
        runtime environment injection is implemented in RR.

        Args:
            instance (pyblish.api.Instance): Publishing instance
            job (RRJob): RRJob instance to be injected.

        Returns:
            RRJob: Injected RRJob instance.

        Throws:
            RuntimeError: If any of the required env vars is missing.

        """

        temp_file_name = "{}_{}.json".format(
            datetime.utcnow().strftime('%Y%m%d%H%M%S%f'),
            str(uuid.uuid1())
        )

        export_url = os.path.join(tempfile.gettempdir(), temp_file_name)
        print(">>> Temporary path: {}".format(export_url))

        anatomy_data = instance.context.data["anatomyData"]
        addons_manager = instance.context.data["ayonAddonsManager"]
        applications_addon = addons_manager.get_enabled_addon("applications")

        folder_key = "folder"
        if applications_addon is None:
            # Use 'asset' when applications addon command is not used
            folder_key = "asset"

        add_kwargs = {
            "project": anatomy_data["project"]["name"],
            folder_key: instance.context.data["folderPath"],
            "task": anatomy_data["task"]["name"],
            "app": instance.context.data.get("appName"),
            "envgroup": "farm"
        }

        if not all(add_kwargs.values()):
            raise RuntimeError((
                "Missing required env vars: AYON_PROJECT_NAME, AYON_FOLDER_PATH,"
                " AYON_TASK_NAME, AYON_APP_NAME"
            ))

        args = ["--headless"]
        # Use applications addon to extract environments
        # NOTE this is for backwards compatibility, the global command
        #   will be removed in future and only applications addon command
        #   should be used.
        if applications_addon is not None:
            args.extend(["addon", "applications"])

        args.extend([
            "extractenvironments",
            export_url
        ])

        if os.getenv('IS_TEST'):
            args.append("--automatic-tests")

        for key, value in add_kwargs.items():
            args.extend([f"--{key}", value])
        self.log.debug("Executing: {}".format(" ".join(args)))
        run_ayon_launcher_process(*args, logger=self.log)

        self.log.debug("Loading file ...")
        with open(export_url) as fp:
            contents = json.load(fp)

        job.rrEnvList = RREnvList(contents).serialize()
        return job
