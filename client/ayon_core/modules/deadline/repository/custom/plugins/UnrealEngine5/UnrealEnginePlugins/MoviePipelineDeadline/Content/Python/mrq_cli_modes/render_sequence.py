# Copyright Epic Games, Inc. All Rights Reserved

"""
This script handles processing jobs for a specific sequence
"""

import unreal
from getpass import getuser

from .render_queue_jobs import render_jobs
from .utils import (
    movie_pipeline_queue,
    project_settings,
    get_asset_data
)


def setup_sequence_parser(subparser):
    """
    This method adds a custom execution function and args to a sequence subparser

    :param subparser: Subparser for processing custom sequences
    """
    # We will use the level sequence and the map as our context for
    # other subsequence arguments.
    subparser.add_argument(
        "sequence", type=str, help="The level sequence that will be rendered."
    )
    subparser.add_argument(
        "map",
        type=str,
        help="The map the level sequence will be loaded with for rendering.",
    )

    # Get some information for the render queue
    subparser.add_argument(
        "mrq_preset",
        type=str,
        help="The MRQ preset used to render the current job.",
    )

    # Function to process arguments
    subparser.set_defaults(func=_process_args)


def render_current_sequence(
    sequence_name,
    sequence_map,
    mrq_preset,
    user=None,
    shots=None,
    is_remote=False,
    is_cmdline=False,
    remote_batch_name=None,
    remote_job_preset=None,
    executor_instance=None,
    output_dir_override=None,
    output_filename_override=None
):
    """
    Renders a sequence with a map and mrq preset

    :param str sequence_name: Sequence to render
    :param str sequence_map: Map to load sequence
    :param str mrq_preset: MRQ preset for rendering sequence
    :param str user: Render user
    :param list shots: Shots to render
    :param bool is_remote: Flag to determine if the job should be executed remotely
    :param bool is_cmdline: Flag to determine if the render was executed via commandline
    :param str remote_batch_name: Remote render batch name
    :param str remote_job_preset:  deadline job Preset Library
    :param executor_instance: Movie Pipeline executor Instance
    :param str output_dir_override: Movie Pipeline output directory override
    :param str output_filename_override: Movie Pipeline filename format override
    :return: MRQ executor
    """

    # The queue subsystem behaves like a singleton so
    # clear all the jobs in the current queue.
    movie_pipeline_queue.delete_all_jobs()

    render_job = movie_pipeline_queue.allocate_new_job(
        unreal.SystemLibrary.conv_soft_class_path_to_soft_class_ref(
            project_settings.default_executor_job
        )
    )

    # Set the author on the job
    render_job.author = user or getuser()

    sequence_data_asset = get_asset_data(sequence_name, "LevelSequence")

    # Create a job in the queue
    unreal.log(f"Creating render job for `{sequence_data_asset.asset_name}`")
    render_job.job_name = sequence_data_asset.asset_name

    unreal.log(
        f"Setting the job sequence to `{sequence_data_asset.asset_name}`"
    )
    render_job.sequence = sequence_data_asset.to_soft_object_path()

    map_data_asset = get_asset_data(sequence_map, "World")
    unreal.log(f"Setting the job map to `{map_data_asset.asset_name}`")
    render_job.map = map_data_asset.to_soft_object_path()

    mrq_preset_data_asset = get_asset_data(
        mrq_preset, "MoviePipelineMasterConfig"
    )
    unreal.log(
        f"Setting the movie pipeline preset to `{mrq_preset_data_asset.asset_name}`"
    )
    render_job.set_configuration(mrq_preset_data_asset.get_asset())

    # MRQ added the ability to enable and disable jobs. Check to see is a job
    # is disabled and enable it. The assumption is we want to render this
    # particular job.
    # Note this try/except block is for backwards compatibility
    try:
        if not render_job.enabled:
            render_job.enabled = True
    except AttributeError:
        pass

    # If we have a shot list, iterate over the shots in the sequence
    # and disable anything that's not in the shot list. If no shot list is
    # provided render all the shots in the sequence
    if shots:
        for shot in render_job.shot_info:
            if shot.inner_name in shots or (shot.outer_name in shots):
                shot.enabled = True
            else:
                unreal.log_warning(
                    f"Disabling shot `{shot.inner_name}` from current render job `{render_job.job_name}`"
                )
                shot.enabled = False

    try:
        # Execute the render. This will execute the render based on whether
        # its remote or local
        executor = render_jobs(
            is_remote,
            remote_batch_name=remote_batch_name,
            remote_job_preset=remote_job_preset,
            is_cmdline=is_cmdline,
            executor_instance=executor_instance,
            output_dir_override=output_dir_override,
            output_filename_override=output_filename_override
        )

    except Exception as err:
        unreal.log_error(
            f"An error occurred executing the render.\n\tError: {err}"
        )
        raise

    return executor


def _process_args(args):
    """
    Function to process the arguments for the sequence subcommand
    :param args: Parsed Arguments from parser
    """

    return render_current_sequence(
        args.sequence,
        args.map,
        args.mrq_preset,
        user=args.user,
        shots=args.shots,
        is_remote=args.remote,
        is_cmdline=args.cmdline,
        remote_batch_name=args.batch_name,
        remote_job_preset=args.deadline_job_preset,
        output_dir_override=args.output_override,
        output_filename_override=args.filename_override
    )
