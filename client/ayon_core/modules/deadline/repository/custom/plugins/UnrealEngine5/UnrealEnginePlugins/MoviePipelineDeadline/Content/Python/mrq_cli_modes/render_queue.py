# Copyright Epic Games, Inc. All Rights Reserved

"""
This script handles processing jobs for a specific queue asset
"""
import unreal

from .render_queue_jobs import render_jobs
from .utils import (
    get_asset_data,
    movie_pipeline_queue,
    update_queue
)


def setup_queue_parser(subparser):
    """
    This method adds a custom execution function and args to a queue subparser

    :param subparser: Subparser for processing custom sequences
    """
    # Set the name of the job
    subparser.add_argument(
        "queue",
        type=str,
        help="The name or path to a movie pipeline queue."
    )

    # Add option to only load the contents of the queue. By default,
    # this will only load the queue and render its contents
    subparser.add_argument(
        "--load",
        action="store_true",
        help="Load the contents of the queue asset. By default the queue asset will loaded and render its contents.",
    )

    # We will use the level sequence and the map as our context for
    # other subsequence arguments.
    subparser.add_argument(
        "--jobs",
        type=str,
        nargs="+",
        help="A list of jobs to execute in the queue. "
        "If no jobs are provided, all jobs in the queue will be rendered.",
    )

    # Function to process arguments
    subparser.set_defaults(func=_process_args)


def render_queue_asset(
    queue_name,
    only_load=False,
    shots=None,
    jobs=None,
    all_shots=False,
    is_cmdline=False,
    is_remote=False,
    user=None,
    remote_batch_name=None,
    remote_job_preset=None,
    executor_instance=None,
    output_dir_override=None,
    output_filename_override=None
):
    """
    Render using a Movie Render Queue asset

    :param str queue_name: The name of the Queue asset
    :param bool only_load: Only load the queue asset. This is usually used when you need to process intermediary steps before rendering
    :param list shots: Shots to render from the queue.
    :param list jobs: The list job to render in the Queue asset.
    :param bool all_shots: Flag to render all shots in a job in the queue.
    :param bool is_cmdline: Flag to determine if the job is a commandline job
    :param bool is_remote: Flag to determine if the jobs should be rendered remote
    :param str user: Render user
    :param str remote_batch_name: Batch name for remote renders
    :param str remote_job_preset: Remote render job preset
    :param executor_instance: Movie Pipeline executor instance
    :param str output_dir_override: Movie Pipeline output directory override
    :param str output_filename_override: Movie Pipeline filename format override
    :return: MRQ Executor
    """

    # The queue subsystem behaves like a singleton so
    # clear all the jobs in the current queue.
    movie_pipeline_queue.delete_all_jobs()

    # Get the queue data asset package path by name or by path
    # Create a new queue from the queue asset
    movie_pipeline_queue.copy_from(
        get_asset_data(queue_name, "MoviePipelineQueue").get_asset()
    )

    # If we only want to load the queue asset, then exit after loading.
    # If we want to shut down the editor as well, then do so
    if only_load:

        if is_cmdline:
            unreal.SystemLibrary.quit_editor()

        return None

    if not movie_pipeline_queue.get_jobs():
        # Make sure we have jobs in the queue to work with
        raise RuntimeError("There are no jobs in the queue!!")

    # Allow executing the render queue in its current loaded state
    if all_shots or (any([shots, jobs])):
        update_queue(
            jobs=jobs,
            shots=shots,
            all_shots=all_shots,
            user=user
        )

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

    except Exception:
        raise

    return executor


def _process_args(args):
    """
    Function to process the arguments for the sequence subcommand
    :param args: Parsed Arguments from parser
    """

    return render_queue_asset(
        args.queue,
        only_load=args.load,
        shots=args.shots,
        jobs=args.jobs,
        all_shots=args.all_shots,
        is_remote=args.remote,
        is_cmdline=args.cmdline,
        user=args.user,
        remote_batch_name=args.batch_name,
        remote_job_preset=args.deadline_job_preset,
        output_dir_override=args.output_override,
        output_filename_override=args.filename_override
    )
