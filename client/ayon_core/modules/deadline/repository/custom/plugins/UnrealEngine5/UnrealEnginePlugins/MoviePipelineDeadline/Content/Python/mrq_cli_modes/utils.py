# Copyright Epic Games, Inc. All Rights Reserved

import unreal

from getpass import getuser

# Get a render queue
pipeline_subsystem = unreal.get_editor_subsystem(
    unreal.MoviePipelineQueueSubsystem
)

# Get the project settings
project_settings = unreal.get_default_object(
    unreal.MovieRenderPipelineProjectSettings
)

# Get the pipeline queue
movie_pipeline_queue = pipeline_subsystem.get_queue()

pipeline_executor = None


def get_executor_instance(is_remote):
    """
    Method to return an instance of a render executor

    :param bool is_remote: Flag to use the local or remote executor class
    :return: Executor instance
    """
    is_soft_class_object = True
    # Convert the SoftClassPath into a SoftClassReference.
    # local executor class from the project settings
    try:
        class_ref = unreal.SystemLibrary.conv_soft_class_path_to_soft_class_ref(
            project_settings.default_local_executor
        )
    # For Backwards compatibility. Older version returned a class object from
    # the project settings
    except TypeError:
        class_ref = project_settings.default_local_executor
        is_soft_class_object = False

    if is_remote:
        try:
            # Get the remote executor class
            class_ref = (
                unreal.SystemLibrary.conv_soft_class_path_to_soft_class_ref(
                    project_settings.default_remote_executor
                )
            )
        except TypeError:
            class_ref = project_settings.default_remote_executor
            is_soft_class_object = False

    if not class_ref:
        raise RuntimeError(
            "Failed to get a class reference to the default executor from the "
            "project settings. Check the logs for more details."
        )

    if is_soft_class_object:
        # Get the executor class as this is required to get an instance of
        # the executor
        executor_class = unreal.SystemLibrary.load_class_asset_blocking(
            class_ref
        )
    else:
        executor_class = class_ref

    global pipeline_executor
    pipeline_executor = unreal.new_object(executor_class)

    return pipeline_executor


def execute_render(is_remote=False, executor_instance=None, is_cmdline=False):
    """
    Starts a render

    :param bool is_remote: Flag to use the local or remote executor class
    :param executor_instance: Executor instance used for rendering
    :param bool is_cmdline: Flag to determine if the render was executed from a commandline.
    """

    if not executor_instance:
        executor_instance = get_executor_instance(is_remote)

    if is_cmdline:
        setup_editor_exit_callback(executor_instance)

    # Start the Render
    unreal.log("MRQ job started...")
    unreal.log(f"Is remote render: {is_remote}")

    pipeline_subsystem.render_queue_with_executor_instance(executor_instance)

    return executor_instance


def setup_editor_exit_callback(executor_instance):
    """
    Setup callbacks for when you need to close the editor after a render

    :param executor_instance: Movie Pipeline executor instance
    """

    unreal.log("Executed job from commandline, setting up shutdown callback..")

    # add a callable to the executor to be executed when the pipeline is done rendering
    executor_instance.on_executor_finished_delegate.add_callable(
        shutdown_editor
    )
    # add a callable to the executor to be executed when the pipeline fails to render
    executor_instance.on_executor_errored_delegate.add_callable(
        executor_failed_callback
    )


def shutdown_editor(movie_pipeline=None, results=None):
    """
    This method shutdown the editor
    """
    unreal.log("Rendering is complete! Exiting...")
    unreal.SystemLibrary.quit_editor()


def executor_failed_callback(executor, pipeline, is_fatal, error):
    """
    Callback executed when a job fails in the editor
    """
    unreal.log_error(
        f"An error occurred while executing a render.\n\tError: {error}"
    )

    unreal.SystemLibrary.quit_editor()


def get_asset_data(name_or_path, asset_class):
    """
    Get the asset data for the asset name or path based on its class.

    :param str name_or_path: asset name or package name
    :param str asset_class: Asset class filter to use when looking for assets in registry
    :raises RuntimeError
    :return: Asset package if it exists
    """
    # Get all the specified class assets in the project.
    # This is the only mechanism we can think of at the moment to allow
    # shorter path names in the commandline interface. This will allow users
    # to only provide the asset name or the package path in the commandline
    # interface based on the assumption that all assets are unique
    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()

    # If the asset registry is still loading, wait for it to finish
    if asset_registry.is_loading_assets():
        unreal.log_warning("Asset Registry is loading, waiting to complete...")
        asset_registry.wait_for_completion()

        unreal.log("Asset Registry load complete!")

    assets = asset_registry.get_assets(
        unreal.ARFilter(class_names=[asset_class])
    )

    # This lookup could potentially be very slow
    for asset in assets:
        # If a package name is provided lookup the package path. If a
        # packages startwith a "/" this signifies a content package. Content
        # packages can either be Game or plugin. Game content paths start
        # with "/Game" and plugin contents startswith /<PluginName>
        if name_or_path.startswith("/"):
            # Reconstruct the package path into a package name. eg.
            # /my/package_name.package_name -> /my/package_name
            name_or_path = name_or_path.split(".")[0]
            if asset.package_name == name_or_path:
                return asset
        else:
            if asset.asset_name == name_or_path:
                return asset
    else:
        raise RuntimeError(f"`{name_or_path}` could not be found!")


def setup_remote_render_jobs(batch_name, job_preset, render_jobs):
    """
    This function sets up a render job with the options for a remote render.
    This is configured currently for deadline jobs.

    :param str batch_name: Remote render batch name
    :param str job_preset: Job Preset to use for job details
    :param list render_jobs: The list of render jobs to apply the ars to
    """

    unreal.log("Setting up Remote render executor.. ")

    # Update the settings on the render job.
    # Currently, this is designed to work with deadline

    # Make sure we have the relevant attribute on the jobs. This remote cli
    # setup can be used with out-of-process rendering and not just deadline.
    unset_job_properties = []
    for job in render_jobs:
        if hasattr(job, "batch_name") and not batch_name:
            unset_job_properties.append(job.name)

        if hasattr(job, "job_preset") and not job_preset:
            unset_job_properties.append(job.name)

    # If we find a deadline property on the job, and it's not set, raise an
    # error
    if unset_job_properties:
        raise RuntimeError(
            "These jobs did not have a batch name, preset name or preset "
            "library set. This is a requirement for deadline remote rendering. "
            "{jobs}".format(
                jobs="\n".join(unset_job_properties))
        )

    for render_job in render_jobs:
        render_job.batch_name = batch_name
        render_job.job_preset = get_asset_data(
            job_preset,
            "DeadlineJobPreset"
        ).get_asset()


def set_job_state(job, enable=False):
    """
    This method sets the state on a current job to enabled or disabled

    :param job: MoviePipeline job to enable/disable
    :param bool enable: Flag to determine if a job should be or not
    """

    if enable:
        # Check for an enable attribute on the job and if not move along.
        # Note: `Enabled` was added to MRQ that allows disabling all shots in
        #  a job. This also enables backwards compatibility.
        try:
            if not job.enabled:
                job.enabled = True
        except AttributeError:
            # Legacy implementations assumes the presence of a job means its
            # enabled
            return

    try:
        if job.enabled:
            job.enabled = False
    except AttributeError:
        # If the attribute is not available, go through and disable all the
        # associated shots. This behaves like a disabled job
        for shot in job.shot_info:
            unreal.log_warning(
                f"Disabling shot `{shot.inner_name}` from current render job `{job.job_name}`"
            )
            shot.enabled = False


def update_render_output(job, output_dir=None, output_filename=None):
    """
    Updates that output directory and filename on a render job

    :param job: MRQ job
    :param str output_dir: Output directory for renders
    :param str output_filename: Output filename
    """

    # Get the job output settings
    output_setting = job.get_configuration().find_setting_by_class(
        unreal.MoviePipelineOutputSetting
    )

    if output_dir:
        new_output_dir = unreal.DirectoryPath()
        new_output_dir.set_editor_property(
            "path",
            output_dir
        )
        unreal.log_warning(
            f"Overriding output directory! New output directory is `{output_dir}`."
        )
        output_setting.output_directory = new_output_dir

    if output_filename:
        unreal.log_warning(
            "Overriding filename format! New format is `{output_filename}`."
        )

        output_setting.file_name_format = output_filename


def update_queue(
    jobs=None,
    shots=None,
    all_shots=False,
    user=None,
):
    """
    This function configures and renders a job based on the arguments

    :param list jobs: MRQ jobs to render
    :param list shots: Shots to render from jobs
    :param bool all_shots: Flag for rendering all shots
    :param str user: Render user
    """

    # Iterate over all the jobs and make sure the jobs we want to
    # render are enabled.
    # All jobs that are not going to be rendered will be disabled if the
    # job enabled attribute is not set or their shots disabled.
    # The expectation is, If a job name is specified, we want to render the
    # current state of that job.
    # If a shot list is specified, we want to only render that shot alongside
    # any other whole jobs (job states) that are explicitly specified,
    # else other jobs or shots that are not
    # needed are disabled
    for job in movie_pipeline_queue.get_jobs():
        enable_job = False

        # Get a list of jobs to enable.
        # This will enable jobs in their current queue state awaiting other
        # modifications if shots are provided, if only the job name is
        # specified, the job will be rendered in its current state
        if jobs and (job.job_name in jobs):
            enable_job = True

        # If we are told to render all shots. Enable all shots for all jobs
        if all_shots:
            for shot in job.shot_info:
                shot.enabled = True

            # set the user for the current job
            job.author = user or getuser()

            # Set the job to enabled and move on to the next job
            set_job_state(job, enable=True)

            continue

        # If we have a list of shots, go through the shots associated
        # with this job, enable the shots that need to be rendered and
        # disable the others
        if shots and (not enable_job):
            for shot in job.shot_info:
                if shot.inner_name in shots or (shot.outer_name in shots):
                    shot.enabled = True
                    enable_job = True
                else:
                    unreal.log_warning(
                        f"Disabling shot `{shot.inner_name}` from current render job `{job.job_name}`"
                    )
                    shot.enabled = False

        if enable_job:
            # Set the author on the job
            job.author = user or getuser()

        # Set the state of the job by enabling or disabling it.
        set_job_state(job, enable=enable_job)
