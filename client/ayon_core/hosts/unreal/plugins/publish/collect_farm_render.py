import os
import attr
import unreal

import pyblish.api

from ayon_core.pipeline import publish
from ayon_core.pipeline.publish import RenderInstance

from ayon_core.hosts.unreal.api.pipeline import UNREAL_VERSION
from ayon_core.hosts.unreal.api.rendering import (
    SUPPORTED_EXTENSION_MAP,
    get_render_config,
    set_output_extension_from_settings
)


@attr.s
class UnrealRenderInstance(RenderInstance):
    # extend generic, composition name is needed
    fps = attr.ib(default=None)
    projectEntity = attr.ib(default=None)
    stagingDir = attr.ib(default=None)
    publish_attributes = attr.ib(default={})
    file_names = attr.ib(default=[])
    master_level = attr.ib(default=None)
    config_path = attr.ib(default=None)
    app_version = attr.ib(default=None)
    output_settings = attr.ib(default=None)
    render_queue_path = attr.ib(default=None)


class CollectUnrealRemoteRender(publish.AbstractCollectRender):

    order = pyblish.api.CollectorOrder + 0.405
    label = "Collect Farm Expected files"
    hosts = ["unreal"]
    families = ["render.farm"]

    padding_width = 6
    rendered_extension = 'png'

    def get_instances(self, context):
        instances = []
        instances_to_remove = []

        current_file = context.data["currentFile"]
        version = 1  # TODO where to get this without change list

        project_name = context.data["projectName"]
        project_settings = context.data['project_settings']
        config_path, config = get_render_config(project_name, project_settings)
        if not config:
            raise RuntimeError("Please provide stored render config at path "
                "set in `ayon+settings://unreal/render_config_path`")

        output_ext_from_settings = project_settings["unreal"]["render_format"]
        config = set_output_extension_from_settings(output_ext_from_settings,
                                                    config)

        ext = self._get_ext_from_config(config)
        if not ext:
            raise RuntimeError("Please provide output extension in config!")

        output_settings = config.find_or_add_setting_by_class(
            unreal.MoviePipelineOutputSetting)

        resolution = output_settings.output_resolution
        resolution_width = resolution.x
        resolution_height = resolution.y

        output_fps = output_settings.output_frame_rate
        fps = f"{output_fps.denominator}.{output_fps.numerator}"

        for inst in context:
            if not inst.data.get("active", True):
                continue

            family = inst.data["family"]
            if family not in ["render"]:
                continue

            render_queue_path = "/Game/Ayon/renderQueue"
            if not unreal.EditorAssetLibrary.does_asset_exist(
                    render_queue_path):
                # TODO temporary until C++ blueprint is created as it is not
                # possible to create renderQueue
                master_level = inst.data["master_level"]
                sequence = inst.data["sequence"]
                msg = (f"Please create `Movie Pipeline Queue` "
                       f"at `{render_queue_path}`. "
                       f"Set it Sequence to `{sequence}`, "
                       f"Map to `{master_level}` and "
                       f"Settings to `{config_path}` ")
                raise RuntimeError(msg)

            instance_families = inst.data.get("families", [])
            product_name = inst.data["productName"]
            task_name = inst.data.get("task")

            ar = unreal.AssetRegistryHelpers.get_asset_registry()
            sequence = (ar.get_asset_by_object_path(inst.data["sequence"]).
                        get_asset())
            if not sequence:
                raise RuntimeError(f"Cannot find {inst.data['sequence']}")

            # current frame range - might be different from created
            frame_start = sequence.get_playback_start()
            # in Unreal 1 of 60 >> 0-59
            frame_end = sequence.get_playback_end() - 1

            inst.data["frameStart"] = frame_start
            inst.data["frameEnd"] = frame_end

            master_sequence_name = inst.data["output"]
            frame_placeholder = "#" * output_settings.zero_pad_frame_numbers
            exp_file_name = self._get_expected_file_name(
                output_settings.file_name_format,
                ext,
                frame_placeholder,
                master_sequence_name)

            publish_attributes = {}

            instance = UnrealRenderInstance(
                family="render",
                families=["render.farm"],
                version=version,
                time="",
                source=current_file,
                label="{} - {}".format(product_name, family),
                productName=product_name,
                productType="render",
                folderPath=inst.data["folderPath"],
                task=task_name,
                attachTo=False,
                setMembers='',
                publish=True,
                name=product_name,
                resolutionWidth=resolution_width,
                resolutionHeight=resolution_height,
                pixelAspect=1,
                tileRendering=False,
                tilesX=0,
                tilesY=0,
                review="review" in instance_families,
                frameStart=frame_start,
                frameEnd=frame_end,
                frameStep=1,
                fps=fps,
                publish_attributes=publish_attributes,
                file_names=[exp_file_name],
                app_version=f"{UNREAL_VERSION.major}.{UNREAL_VERSION.minor}",
                output_settings=output_settings,
                config_path=config_path,
                master_level=inst.data["master_level"],
                render_queue_path=render_queue_path,
                deadline=inst.data.get("deadline")
            )
            instance.farm = True

            instances.append(instance)
            instances_to_remove.append(inst)

        for instance in instances_to_remove:
            context.remove(instance)
        return instances

    def _get_expected_file_name(self, file_name_format, ext,
                                frame_placeholder, sequence_name):
        """Calculate file name that should be rendered."""
        file_name_format = file_name_format.replace("{sequence_name}",
                                                    sequence_name)
        file_name_format = file_name_format.replace("{frame_number}",
                                                    frame_placeholder)
        return f"{file_name_format}.{ext}"

    def get_expected_files(self, render_instance):
        """
            Returns list of rendered files that should be created by
            Deadline. These are not published directly, they are source
            for later 'submit_publish_job'.

        Args:
            render_instance (RenderInstance): to pull anatomy and parts used
                in url

        Returns:
            (list) of absolute urls to rendered file
        """
        start = render_instance.frameStart
        end = render_instance.frameEnd

        base_dir = self._get_output_dir(render_instance)
        expected_files = []
        for file_name in render_instance.file_names:
            if "#" in file_name:
                _spl = file_name.split("#")
                _len = (len(_spl) - 1)
                placeholder = "#"*_len
                for frame in range(start, end+1):
                    new_file_name = file_name.replace(placeholder,
                                                      str(frame).zfill(_len))
                    path = os.path.join(base_dir, new_file_name)
                    expected_files.append(path)

        return expected_files

    def _get_output_dir(self, render_instance):
        """
            Returns dir path of rendered files, used in submit_publish_job
            for metadata.json location.
            Should be in separate folder inside of work area.

        Args:
            render_instance (RenderInstance):

        Returns:
            (str): absolute path to rendered files
        """
        # render to folder of project
        output_dir = render_instance.output_settings.output_directory.path
        base_dir = os.path.dirname(render_instance.source)
        output_dir = output_dir.replace("{project_dir}", base_dir)

        return output_dir

    def _get_ext_from_config(self, config):
        """Get set extension in render config.

        Bit weird approach to loop through supported extensions and bail on
        found.
        Assumes that there would be only single extension!

        Arg:
            config (unreal.MoviePipelineMasterConfig): render config
        """
        for ext, cls in SUPPORTED_EXTENSION_MAP.items():
            current_sett = config.find_setting_by_class(cls)
            if current_sett:
                return ext
