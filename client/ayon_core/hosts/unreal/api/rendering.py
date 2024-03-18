import os

import unreal

from ayon_core.settings import get_project_settings
from ayon_core.pipeline import Anatomy
from ayon_core.hosts.unreal.api import pipeline
from ayon_core.tools.utils import show_message_dialog


queue = None
executor = None

SUPPORTED_EXTENSION_MAP = {
    "png": unreal.MoviePipelineImageSequenceOutput_PNG,
    "exr": unreal.MoviePipelineImageSequenceOutput_EXR,
    "jpg": unreal.MoviePipelineImageSequenceOutput_JPG,
    "bmp": unreal.MoviePipelineImageSequenceOutput_BMP,
}


def _queue_finish_callback(exec, success):
    unreal.log("Render completed. Success: " + str(success))

    # Delete our reference so we don't keep it alive.
    global executor
    global queue
    del executor
    del queue


def _job_finish_callback(job, success):
    # You can make any edits you want to the editor world here, and the world
    # will be duplicated when the next render happens. Make sure you undo your
    # edits in OnQueueFinishedCallback if you don't want to leak state changes
    # into the editor world.
    unreal.log("Individual job completed.")


def get_render_config(project_name, project_settings=None):
    """Returns Unreal asset from render config.

    Expects configured location of render config set in Settings. This path
    must contain stored render config in Unreal project
    Args:
        project_name (str):
        project_settings (dict): Settings from get_project_settings
    Returns
        (str, uasset): path and UAsset
    Raises:
        RuntimeError if no path to config is set
    """
    if not project_settings:
        project_settings = get_project_settings(project_name)

    ar = unreal.AssetRegistryHelpers.get_asset_registry()
    config_path = project_settings["unreal"]["render_config_path"]

    if not config_path:
        raise RuntimeError("Please provide location for stored render "
            "config in `ayon+settings://unreal/render_config_path`")

    unreal.log(f"Configured config path {config_path}")
    if not unreal.EditorAssetLibrary.does_asset_exist(config_path):
        raise RuntimeError(f"No config found at {config_path}")

    unreal.log("Found saved render configuration")
    config = ar.get_asset_by_object_path(config_path).get_asset()

    return config_path, config


def set_output_extension_from_settings(render_format, config):
    """Forces output extension from Settings if available.

    Clear all other extensions if there is value in Settings.
    Args:
        render_format (str): "png"|"jpg"|"exr"|"bmp"
        config (unreal.MoviePipelineMasterConfig)
    Returns
        (unreal.MoviePipelineMasterConfig)
    """
    if not render_format:
        return config

    cls_from_map = SUPPORTED_EXTENSION_MAP.get(render_format.lower())
    if not cls_from_map:
        return config

    for ext, cls in SUPPORTED_EXTENSION_MAP.items():
        current_sett = config.find_setting_by_class(cls)
        if current_sett and ext == render_format:
            return config
        config.remove_setting(current_sett)

    config.find_or_add_setting_by_class(cls_from_map)
    return config


def start_rendering():
    """
    Start the rendering process.
    """
    unreal.log("Starting rendering...")

    # Get selected sequences
    assets = unreal.EditorUtilityLibrary.get_selected_assets()

    if not assets:
        show_message_dialog(
            title="No assets selected",
            message="No assets selected. Select a render instance.",
            level="warning")
        raise RuntimeError(
            "No assets selected. You need to select a render instance.")

    # instances = pipeline.ls_inst()
    instances = [
        a for a in assets
        if a.get_class().get_name() == "AyonPublishInstance"]

    inst_data = []

    for i in instances:
        data = pipeline.parse_container(i.get_path_name())
        if data["productType"] == "render":
            inst_data.append(data)

    try:
        project_name = os.environ.get("AYON_PROJECT_NAME")
        anatomy = Anatomy(project_name)
        root = anatomy.roots['renders']
    except Exception as e:
        raise Exception(
            "Could not find render root in anatomy settings.") from e

    render_dir = f"{root}/{project_name}"

    # subsystem = unreal.get_editor_subsystem(
    #     unreal.MoviePipelineQueueSubsystem)
    # queue = subsystem.get_queue()
    global queue
    queue = unreal.MoviePipelineQueue()

    ar = unreal.AssetRegistryHelpers.get_asset_registry()

    project_settings = get_project_settings(project_name)
    _, config = get_render_config(project_name, project_settings)

    for i in inst_data:
        sequence = ar.get_asset_by_object_path(i["sequence"]).get_asset()

        sequences = [{
            "sequence": sequence,
            "output": f"{i['output']}",
            "frame_range": (
                int(float(i["frameStart"])),
                int(float(i["frameEnd"])) + 1)
        }]
        render_list = []

        # Get all the sequences to render. If there are subsequences,
        # add them and their frame ranges to the render list. We also
        # use the names for the output paths.
        for seq in sequences:
            subscenes = pipeline.get_subsequences(seq.get('sequence'))

            if subscenes:
                for sub_seq in subscenes:
                    sequences.append({
                        "sequence": sub_seq.get_sequence(),
                        "output": (f"{seq.get('output')}/"
                                   f"{sub_seq.get_sequence().get_name()}"),
                        "frame_range": (
                            sub_seq.get_start_frame(), sub_seq.get_end_frame())
                    })
            else:
                # Avoid rendering camera sequences
                if "_camera" not in seq.get('sequence').get_name():
                    render_list.append(seq)

        # Create the rendering jobs and add them to the queue.
        for render_setting in render_list:
            job = queue.allocate_new_job(unreal.MoviePipelineExecutorJob)
            job.sequence = unreal.SoftObjectPath(i["master_sequence"])
            job.map = unreal.SoftObjectPath(i["master_level"])
            job.author = "Ayon"

            # If we have a saved configuration, copy it to the job.
            if config:
                job.get_configuration().copy_from(config)

            job_config = job.get_configuration()
            # User data could be used to pass data to the job, that can be
            # read in the job's OnJobFinished callback. We could,
            # for instance, pass the AyonPublishInstance's path to the job.
            # job.user_data = ""

            output_dir = render_setting.get('output')
            shot_name = render_setting.get('sequence').get_name()

            settings = job_config.find_or_add_setting_by_class(
                unreal.MoviePipelineOutputSetting)
            settings.output_resolution = unreal.IntPoint(1920, 1080)
            settings.custom_start_frame = render_setting.get("frame_range")[0]
            settings.custom_end_frame = render_setting.get("frame_range")[1]
            settings.use_custom_playback_range = True
            settings.file_name_format = f"{shot_name}" + ".{frame_number}"
            settings.output_directory.path = f"{render_dir}/{output_dir}"

            job_config.find_or_add_setting_by_class(
                unreal.MoviePipelineDeferredPassBase)

            render_format = project_settings.get("unreal").get("render_format",
                                                               "png")

            set_output_extension_from_settings(render_format,
                                               job_config)

    # If there are jobs in the queue, start the rendering process.
    if queue.get_jobs():
        global executor
        executor = unreal.MoviePipelinePIEExecutor()

        preroll_frames = project_settings.get("unreal").get("preroll_frames",
                                                            0)

        settings = unreal.MoviePipelinePIEExecutorSettings()
        settings.set_editor_property(
            "initial_delay_frame_count", preroll_frames)

        executor.on_executor_finished_delegate.add_callable_unique(
            _queue_finish_callback)
        executor.on_individual_job_finished_delegate.add_callable_unique(
            _job_finish_callback)  # Only available on PIE Executor
        executor.execute(queue)
