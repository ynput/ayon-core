# Copyright Epic Games, Inc. All Rights Reserved

"""
This script handles processing jobs and shots in the current loaded queue
"""
import unreal

from .utils import (
    movie_pipeline_queue,
    execute_render,
    setup_remote_render_jobs,
    update_render_output
)


def setup_render_parser(subparser):
    """
    This method adds a custom execution function and args to a render subparser

    :param subparser: Subparser for processing custom sequences
    """

    # Function to process arguments
    subparser.set_defaults(func=_process_args)


def render_jobs(
    is_remote=False,
    is_cmdline=False,
    executor_instance=None,
    remote_batch_name=None,
    remote_job_preset=None,
    output_dir_override=None,
    output_filename_override=None
):
    """
    This renders the current state of the queue

    :param bool is_remote: Is this a remote render
    :param bool is_cmdline: Is this a commandline render
    :param executor_instance: Movie Pipeline Executor instance
    :param str remote_batch_name: Batch name for remote renders
    :param str remote_job_preset: Remote render job preset
    :param str output_dir_override: Movie Pipeline output directory override
    :param str output_filename_override: Movie Pipeline filename format override
    :return: MRQ executor
    """

    if not movie_pipeline_queue.get_jobs():
        # Make sure we have jobs in the queue to work with
        raise RuntimeError("There are no jobs in the queue!!")

    # Update the job
    for job in movie_pipeline_queue.get_jobs():

        # If we have output job overrides and filename overrides, update it on
        # the job
        if output_dir_override or output_filename_override:
            update_render_output(
                job,
                output_dir=output_dir_override,
                output_filename=output_filename_override
            )

        # Get the job output settings
        output_setting = job.get_configuration().find_setting_by_class(
            unreal.MoviePipelineOutputSetting
        )

        # Allow flushing flies to disk per shot.
        # Required for the OnIndividualShotFinishedCallback to get called.
        output_setting.flush_disk_writes_per_shot = True

    if is_remote:
        setup_remote_render_jobs(
            remote_batch_name,
            remote_job_preset,
            movie_pipeline_queue.get_jobs(),
        )

    try:
        # Execute the render.
        # This will execute the render based on whether its remote or local
        executor = execute_render(
            is_remote,
            executor_instance=executor_instance,
            is_cmdline=is_cmdline,
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

    return render_jobs(
        is_remote=args.remote,
        is_cmdline=args.cmdline,
        remote_batch_name=args.batch_name,
        remote_job_preset=args.deadline_job_preset,
        output_dir_override=args.output_override,
        output_filename_override=args.filename_override
    )
