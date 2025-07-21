# -*- coding: utf-8 -*-
"""Collect render template.

TODO: use @dataclass when times come.

"""
from abc import abstractmethod

import attr
import pyblish.api

from .publish_plugins import AbstractMetaContextPlugin


@attr.s
class RenderInstance(object):
    """Data collected by collectors.

    This data class later on passed to collected instances.
    Those attributes are required later on.

    """

    # metadata
    version = attr.ib()  # instance version
    time = attr.ib()  # time of instance creation (get_formatted_current_time)
    source = attr.ib()  # path to source scene file
    label = attr.ib()  # label to show in GUI
    family = attr.ib()  # product type for pyblish filtering
    productType = attr.ib()  # product type
    productName = attr.ib()  # product name
    folderPath = attr.ib()  # folder path
    task = attr.ib()  # task name
    attachTo = attr.ib()  # product name to attach render to
    setMembers = attr.ib()  # list of nodes/members producing render output
    publish = attr.ib()  # bool, True to publish instance
    name = attr.ib()  # instance name

    # format settings
    resolutionWidth = attr.ib()  # resolution width (1920)
    resolutionHeight = attr.ib()  # resolution height (1080)
    pixelAspect = attr.ib()  # pixel aspect (1.0)

    # time settings
    frameStart = attr.ib()  # start frame
    frameEnd = attr.ib()  # start end
    frameStep = attr.ib()  # frame step

    handleStart = attr.ib(default=None)  # start frame
    handleEnd = attr.ib(default=None)  # start frame

    # for software (like Harmony) where frame range cannot be set by DB
    # handles need to be propagated if exist
    ignoreFrameHandleCheck = attr.ib(default=False)

    # --------------------
    # With default values
    # metadata
    renderer = attr.ib(default="")  # renderer - can be used in Deadline
    review = attr.ib(default=None)  # False - explicitly skip review
    priority = attr.ib(default=50)  # job priority on farm

    # family = attr.ib(default="renderlayer")
    families = attr.ib(default=["renderlayer"])  # list of families
    # True if should be rendered on farm, eg not integrate
    farm = attr.ib(default=False)

    # format settings
    multipartExr = attr.ib(default=False)  # flag for multipart exrs
    convertToScanline = attr.ib(default=False)  # flag for exr conversion

    tileRendering = attr.ib(default=False)  # bool: treat render as tiles
    tilesX = attr.ib(default=0)  # number of tiles in X
    tilesY = attr.ib(default=0)  # number of tiles in Y

    # submit_publish_job
    deadlineSubmissionJob = attr.ib(default=None)
    anatomyData = attr.ib(default=None)
    outputDir = attr.ib(default=None)
    context = attr.ib(default=None)
    deadline = attr.ib(default=None)

    # The source instance the data of this render instance should merge into
    source_instance = attr.ib(default=None, type=pyblish.api.Instance)

    @frameStart.validator
    def check_frame_start(self, _, value):
        """Validate if frame start is not larger then end."""
        if value > self.frameEnd:
            raise ValueError("frameStart must be smaller "
                             "or equal then frameEnd")

    @frameEnd.validator
    def check_frame_end(self, _, value):
        """Validate if frame end is not less then start."""
        if value < self.frameStart:
            raise ValueError("frameEnd must be smaller "
                             "or equal then frameStart")

    @tilesX.validator
    def check_tiles_x(self, _, value):
        """Validate if tile x isn't less then 1."""
        if not self.tileRendering:
            return
        if value < 1:
            raise ValueError("tile X size cannot be less then 1")

        if value == 1 and self.tilesY == 1:
            raise ValueError("both tiles X a Y sizes are set to 1")

    @tilesY.validator
    def check_tiles_y(self, _, value):
        """Validate if tile y isn't less then 1."""
        if not self.tileRendering:
            return
        if value < 1:
            raise ValueError("tile Y size cannot be less then 1")

        if value == 1 and self.tilesX == 1:
            raise ValueError("both tiles X a Y sizes are set to 1")


class AbstractCollectRender(
    pyblish.api.ContextPlugin, metaclass=AbstractMetaContextPlugin
):
    """Gather all publishable render layers from renderSetup."""

    order = pyblish.api.CollectorOrder + 0.01
    label = "Collect Render"
    sync_workfile_version = False

    def __init__(self, *args, **kwargs):
        """Constructor."""
        super(AbstractCollectRender, self).__init__(*args, **kwargs)
        self._file_path = None
        self._context = None

    def process(self, context):
        """Entry point to collector."""
        self._context = context
        for instance in context:
            # make sure workfile instance publishing is enabled
            try:
                if "workfile" in instance.data["families"]:
                    instance.data["publish"] = True
                # TODO merge renderFarm and render.farm
                if ("renderFarm" in instance.data["families"] or
                        "render.farm" in instance.data["families"]):
                    instance.data["remove"] = True
            except KeyError:
                # be tolerant if 'families' is missing.
                pass

        self._file_path = context.data["currentFile"].replace("\\", "/")

        render_instances = self.get_instances(context)
        for render_instance in render_instances:
            exp_files = self.get_expected_files(render_instance)
            assert exp_files, "no file names were generated, this is bug"

            # if we want to attach render to product, check if we have AOV's
            # in expectedFiles. If so, raise error as we cannot attach AOV
            # (considered to be product on its own) to another product
            if render_instance.attachTo:
                assert isinstance(exp_files, list), (
                    "attaching multiple AOVs or renderable cameras to "
                    "product is not supported"
                )

            frame_start_render = int(render_instance.frameStart)
            frame_end_render = int(render_instance.frameEnd)
            # TODO: Refactor hacky frame range workaround below
            if (render_instance.ignoreFrameHandleCheck or
                    int(context.data['frameStartHandle']) == frame_start_render
                    and int(context.data['frameEndHandle']) == frame_end_render):  # noqa: W503, E501
                # only for Harmony where frame range cannot be set by DB
                handle_start = context.data['handleStart']
                handle_end = context.data['handleEnd']
                frame_start = context.data['frameStart']
                frame_end = context.data['frameEnd']
                frame_start_handle = context.data['frameStartHandle']
                frame_end_handle = context.data['frameEndHandle']
            elif (hasattr(render_instance, "frameStartHandle")
                  and hasattr(render_instance, "frameEndHandle")):
                handle_start = int(render_instance.handleStart)
                handle_end = int(render_instance.handleEnd)
                frame_start = int(render_instance.frameStart)
                frame_end = int(render_instance.frameEnd)
                frame_start_handle = int(render_instance.frameStartHandle)
                frame_end_handle = int(render_instance.frameEndHandle)
            else:
                handle_start = 0
                handle_end = 0
                frame_start = frame_start_render
                frame_end = frame_end_render
                frame_start_handle = frame_start_render
                frame_end_handle = frame_end_render

            data = {
                "handleStart": handle_start,
                "handleEnd": handle_end,
                "frameStart": frame_start,
                "frameEnd": frame_end,
                "frameStartHandle": frame_start_handle,
                "frameEndHandle": frame_end_handle,
                "byFrameStep": int(render_instance.frameStep),

                "author": context.data["user"],
                # Add source to allow tracing back to the scene from
                # which was submitted originally
                "expectedFiles": exp_files,
            }
            if self.sync_workfile_version:
                data["version"] = context.data["version"]

            # add additional data
            data = self.add_additional_data(data)

            instance = render_instance.source_instance
            if instance is None:
                instance = context.create_instance(render_instance.name)

            render_instance_dict = attr.asdict(render_instance)
            instance.data.update(render_instance_dict)
            instance.data.update(data)

        self.post_collecting_action()

    @abstractmethod
    def get_instances(self, context):
        """Get all renderable instances and their data.

        Args:
            context (pyblish.api.Context): Context object.

        Returns:
            list of :class:`RenderInstance`: All collected renderable instances
                (like render layers, write nodes, etc.)

        """
        pass

    @abstractmethod
    def get_expected_files(self, render_instance):
        """Get list of expected files.

        Returns:
            list: expected files. This can be either simple list of files with
                their paths, or list of dictionaries, where key is name of AOV
                for example and value is list of files for that AOV.

        Example::

            ['/path/to/file.001.exr', '/path/to/file.002.exr']

            or as dictionary:

            [
                {
                    "beauty": ['/path/to/beauty.001.exr', ...],
                    "mask": ['/path/to/mask.001.exr']
                }
            ]

        """
        pass

    def add_additional_data(self, data):
        """Add additional data to collected instance.

        This can be overridden by host implementation to add custom
        additional data.

        """
        return data

    def post_collecting_action(self):
        """Execute some code after collection is done.

        This is useful for example for restoring current render layer.

        """
        pass
