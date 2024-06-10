# Copyright Epic Games, Inc. All Rights Reserved

import os
import argparse
import json

import unreal

from deadline_rpc import BaseRPC

from mrq_cli_modes import (
    render_queue_manifest,
    render_current_sequence,
    render_queue_asset,
    utils,
)


class MRQRender(BaseRPC):
    """
    Class to execute deadline MRQ renders using RPC
    """

    def __init__(self, *args, **kwargs):
        """
        Constructor
        """
        super(MRQRender, self).__init__(*args, **kwargs)

        self._render_cmd = ["mrq_cli.py"]

        # Keep track of the task data
        self._shot_data = None
        self._queue = None
        self._manifest = None
        self._sequence_data = None

    def _get_queue(self):
        """
        Render a MRQ queue asset

        :return: MRQ queue asset name
        """
        if not self._queue:
            self._queue = self.proxy.get_job_extra_info_key_value("queue_name")

        return self._queue

    def _get_sequence_data(self):
        """
        Get sequence data

        :return: Sequence data
        """
        if not self._sequence_data:
            self._sequence_data = self.proxy.get_job_extra_info_key_value(
                "sequence_render"
            )

        return self._sequence_data

    def _get_serialized_pipeline(self):
        """
        Get Serialized pipeline from Deadline

        :return:
        """
        if not self._manifest:
            serialized_pipeline = self.proxy.get_job_extra_info_key_value(
                "serialized_pipeline"
            )
            if not serialized_pipeline:
                return

            unreal.log(
                f"Executing Serialized Pipeline: `{serialized_pipeline}`"
            )

            # create temp manifest folder
            movieRenderPipeline_dir = os.path.join(
                unreal.SystemLibrary.get_project_saved_directory(),
                "MovieRenderPipeline",
                "TempManifests",
            )

            if not os.path.exists(movieRenderPipeline_dir ):
                os.makedirs(movieRenderPipeline_dir )

            # create manifest file
            manifest_file = unreal.Paths.create_temp_filename(
                movieRenderPipeline_dir ,
                prefix='TempManifest',
                extension='.utxt')

            unreal.log(f"Saving Manifest file `{manifest_file}`")

            # Dump the manifest data into the manifest file
            with open(manifest_file, "w") as manifest:
                manifest.write(serialized_pipeline)

            self._manifest = manifest_file

        return self._manifest

    def execute(self):
        """
        Starts the render execution
        """

        # shots are listed as a dictionary of task id -> shotnames
        # i.e {"O": "my_new_shot"} or {"20", "shot_1,shot_2,shot_4"}

        # Get the task data and cache it
        if not self._shot_data:
            self._shot_data = json.loads(
                self.proxy.get_job_extra_info_key_value("shot_info")
            )

        # Get any output overrides
        output_dir = self.proxy.get_job_extra_info_key_value(
            "output_directory_override"
        )

        # Resolve any path mappings in the directory name. The server expects
        # a list of paths, but we only ever expect one. So wrap it in a list
        # if we have an output directory
        if output_dir:
            output_dir = self.proxy.check_path_mappings([output_dir])
            output_dir = output_dir[0]

        # Get the filename format
        filename_format = self.proxy.get_job_extra_info_key_value(
            "filename_format_override"
        )

        # Resolve any path mappings in the filename. The server expects
        # a list of paths, but we only ever expect one. So wrap it in a list
        if filename_format:
            filename_format = self.proxy.check_path_mappings([filename_format])
            filename_format = filename_format[0]

        # get the shots for the current task
        current_task_data = self._shot_data.get(str(self.current_task_id), None)

        if not current_task_data:
            self.proxy.fail_render("There are no task data to execute!")
            return

        shots = current_task_data.split(",")

        if self._get_queue():
            return self.render_queue(
                self._get_queue(),
                shots,
                output_dir_override=output_dir if output_dir else None,
                filename_format_override=filename_format if filename_format else None
            )

        if self._get_serialized_pipeline():
            return self.render_serialized_pipeline(
                self._get_serialized_pipeline(),
                shots,
                output_dir_override=output_dir if output_dir else None,
                filename_format_override=filename_format if filename_format else None
            )

        if self._get_sequence_data():
            render_data = json.loads(self._get_sequence_data())
            sequence = render_data.get("sequence_name")
            level = render_data.get("level_name")
            mrq_preset = render_data.get("mrq_preset_name")
            return self.render_sequence(
                sequence,
                level,
                mrq_preset,
                shots,
                output_dir_override=output_dir if output_dir else None,
                filename_format_override=filename_format if filename_format else None
            )

    def render_queue(
        self,
        queue_path,
        shots,
        output_dir_override=None,
        filename_format_override=None
    ):
        """
        Executes a render from a queue

        :param str queue_path: Name/path of the queue asset
        :param list shots: Shots to render
        :param str output_dir_override: Movie Pipeline output directory
        :param str filename_format_override: Movie Pipeline filename format override
        """
        unreal.log(f"Executing Queue asset `{queue_path}`")
        unreal.log(f"Rendering shots: {shots}")

        # Get an executor instance
        executor = self._get_executor_instance()

        # Set executor callbacks

        # Set shot finished callbacks
        executor.on_individual_shot_work_finished_delegate.add_callable(
            self._on_individual_shot_finished_callback
        )

        # Set executor finished callbacks
        executor.on_executor_finished_delegate.add_callable(
            self._on_job_finished
        )
        executor.on_executor_errored_delegate.add_callable(self._on_job_failed)

        # Render queue with executor
        render_queue_asset(
            queue_path,
            shots=shots,
            user=self.proxy.get_job_user(),
            executor_instance=executor,
            output_dir_override=output_dir_override,
            output_filename_override=filename_format_override
        )

    def render_serialized_pipeline(
        self,
        manifest_file,
        shots,
        output_dir_override=None,
        filename_format_override=None
    ):
        """
        Executes a render using a manifest file

        :param str manifest_file: serialized pipeline used to render a manifest file
        :param list shots: Shots to render
        :param str output_dir_override: Movie Pipeline output directory
        :param str filename_format_override: Movie Pipeline filename format override
        """
        unreal.log(f"Rendering shots: {shots}")

        # Get an executor instance
        executor = self._get_executor_instance()

        # Set executor callbacks

        # Set shot finished callbacks
        executor.on_individual_shot_work_finished_delegate.add_callable(
            self._on_individual_shot_finished_callback
        )

        # Set executor finished callbacks
        executor.on_executor_finished_delegate.add_callable(
            self._on_job_finished
        )
        executor.on_executor_errored_delegate.add_callable(self._on_job_failed)

        render_queue_manifest(
            manifest_file,
            shots=shots,
            user=self.proxy.get_job_user(),
            executor_instance=executor,
            output_dir_override=output_dir_override,
            output_filename_override=filename_format_override
        )

    def render_sequence(
        self,
        sequence,
        level,
        mrq_preset,
        shots,
        output_dir_override=None,
        filename_format_override=None
    ):
        """
        Executes a render using a sequence level and map

        :param str sequence: Level Sequence name
        :param str level: Level
        :param str mrq_preset: MovieRenderQueue preset
        :param list shots: Shots to render
        :param str output_dir_override: Movie Pipeline output directory
        :param str filename_format_override: Movie Pipeline filename format override
        """
        unreal.log(
            f"Executing sequence `{sequence}` with map `{level}` "
            f"and mrq preset `{mrq_preset}`"
        )
        unreal.log(f"Rendering shots: {shots}")

        # Get an executor instance
        executor = self._get_executor_instance()

        # Set executor callbacks

        # Set shot finished callbacks
        executor.on_individual_shot_work_finished_delegate.add_callable(
            self._on_individual_shot_finished_callback
        )

        # Set executor finished callbacks
        executor.on_executor_finished_delegate.add_callable(
            self._on_job_finished
        )
        executor.on_executor_errored_delegate.add_callable(self._on_job_failed)

        render_current_sequence(
            sequence,
            level,
            mrq_preset,
            shots=shots,
            user=self.proxy.get_job_user(),
            executor_instance=executor,
            output_dir_override=output_dir_override,
            output_filename_override=filename_format_override
        )

    @staticmethod
    def _get_executor_instance():
        """
        Gets an instance of the movie pipeline executor

        :return: Movie Pipeline Executor instance
        """
        return utils.get_executor_instance(False)

    def _on_individual_shot_finished_callback(self, shot_params):
        """
        Callback to execute when a shot is done rendering

        :param shot_params: Movie pipeline shot params
        """
        unreal.log("Executing On individual shot callback")

        # Since MRQ cannot parse certain parameters/arguments till an actual
        # render is complete (e.g. local version numbers), we will use this as
        # an opportunity to update the deadline proxy on the actual frame
        # details that were rendered

        file_patterns = set()

        # Iterate over all the shots in the shot list (typically one shot as
        # this callback is executed) on a shot by shot bases.
        for shot in shot_params.shot_data:
            for pass_identifier in shot.render_pass_data:

                # only get the first file
                paths = shot.render_pass_data[pass_identifier].file_paths

                # make sure we have paths to iterate on
                if len(paths) < 1:
                    continue

                # we only need the ext from the first file
                ext = os.path.splitext(paths[0])[1].replace(".", "")

                # Make sure we actually have an extension to use
                if not ext:
                    continue

                # Get the current job output settings
                output_settings = shot_params.job.get_configuration().find_or_add_setting_by_class(
                    unreal.MoviePipelineOutputSetting
                )

                resolve_params = unreal.MoviePipelineFilenameResolveParams()

                # Set the camera name from the shot data
                resolve_params.camera_name_override = shot_params.shot_data[
                    0
                ].shot.inner_name

                # set the shot name from the shot data
                resolve_params.shot_name_override = shot_params.shot_data[
                    0
                ].shot.outer_name

                # Get the zero padding configuration
                resolve_params.zero_pad_frame_number_count = (
                    output_settings.zero_pad_frame_numbers
                )

                # Update the formatting of frame numbers based on the padding.
                # Deadline uses # (* padding) to display the file names in a job
                resolve_params.file_name_format_overrides[
                    "frame_number"
                ] = "#" * int(output_settings.zero_pad_frame_numbers)

                # Update the extension
                resolve_params.file_name_format_overrides["ext"] = ext

                # Set the job on the resolver
                resolve_params.job = shot_params.job

                # Set the initialization time on the resolver
                resolve_params.initialization_time = (
                    unreal.MoviePipelineLibrary.get_job_initialization_time(
                        shot_params.pipeline
                    )
                )

                # Set the shot overrides
                resolve_params.shot_override = shot_params.shot_data[0].shot

                combined_path = unreal.Paths.combine(
                    [
                        output_settings.output_directory.path,
                        output_settings.file_name_format,
                    ]
                )

                # Resolve the paths
                # The returned values are a tuple with the resolved paths as the
                # first index. Get the paths and add it to a list
                (
                    path,
                    _,
                ) = unreal.MoviePipelineLibrary.resolve_filename_format_arguments(
                    combined_path, resolve_params
                )

                # Make sure we are getting the right type from resolved
                # arguments
                if isinstance(path, str):
                    # Sanitize the paths
                    path = os.path.normpath(path).replace("\\", "/")
                    file_patterns.add(path)

                elif isinstance(path, list):

                    file_patterns.update(
                        set(
                            [
                                os.path.normpath(p).replace("\\", "/")
                                for p in path
                            ]
                        )
                    )

                else:
                    raise RuntimeError(
                        f"Expected the shot file paths to be a "
                        f"string or list but got: {type(path)}"
                    )

        if file_patterns:
            unreal.log(f'Updating remote filenames: {", ".join(file_patterns)}')

            # Update the paths on the deadline job
            self.proxy.update_job_output_filenames(list(file_patterns))

    def _on_job_finished(self, executor=None, success=None):
        """
        Callback to execute on executor finished
        """
        # TODO: add th ability to set the output directory for the task
        unreal.log(f"Task {self.current_task_id} complete!")
        self.task_complete = True

    def _on_job_failed(self, executor, pipeline, is_fatal, error):
        """
        Callback to execute on job failed
        """
        unreal.log_error(f"Is fatal job error: {is_fatal}")
        unreal.log_error(
            f"An error occurred executing task `{self.current_task_id}`: \n\t{error}"
        )
        self.proxy.fail_render(error)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="This parser is used to run an mrq render with rpc"
    )
    parser.add_argument(
        "--port", type=int, default=None, help="Port number for rpc server"
    )
    parser.add_argument(
        "--verbose", action="store_true", help="Enable verbose logging"
    )

    arguments = parser.parse_args()

    MRQRender(port=arguments.port, verbose=arguments.verbose)
