# Copyright Epic Games, Inc. All Rights Reserved

# Built-In
import os
import re
import json
import traceback
from collections import OrderedDict

# External
import unreal

from deadline_service import get_global_deadline_service_instance
from deadline_job import DeadlineJob
from deadline_utils import get_deadline_info_from_preset


@unreal.uclass()
class MoviePipelineDeadlineRemoteExecutor(unreal.MoviePipelineExecutorBase):
    """
    This class defines the editor implementation for Deadline (what happens when you
    press 'Render (Remote)', which is in charge of taking a movie queue from the UI
    and processing it into something Deadline can handle.
    """

    # The queue we are working on, null if no queue has been provided.
    pipeline_queue = unreal.uproperty(unreal.MoviePipelineQueue)
    job_ids = unreal.uproperty(unreal.Array(str))

    # A MoviePipelineExecutor implementation must override this.
    @unreal.ufunction(override=True)
    def execute(self, pipeline_queue):
        """
        This is called when the user presses Render (Remote) in the UI. We will
        split the queue up into multiple jobs. Each job will be submitted to
        deadline separately, with each shot within the job split into one Deadline
        task per shot.
        """

        unreal.log(f"Asked to execute Queue: {pipeline_queue}")
        unreal.log(f"Queue has {len(pipeline_queue.get_jobs())} jobs")

        # Don't try to process empty/null Queues, no need to send them to
        # Deadline.
        if not pipeline_queue or (not pipeline_queue.get_jobs()):
            self.on_executor_finished_impl()
            return

        # The user must save their work and check it in so that Deadline
        # can sync it.
        dirty_packages = []
        dirty_packages.extend(
            unreal.EditorLoadingAndSavingUtils.get_dirty_content_packages()
        )
        dirty_packages.extend(
            unreal.EditorLoadingAndSavingUtils.get_dirty_map_packages()
        )

        # Sometimes the dialog will return `False`
        # even when there are no packages to save. so we are
        # being explict about the packages we need to save
        if dirty_packages:
            if not unreal.EditorLoadingAndSavingUtils.save_dirty_packages_with_dialog(
                True, True
            ):
                message = (
                    "One or more jobs in the queue have an unsaved map/content. "
                    "{packages} "
                    "Please save and check-in all work before submission.".format(
                        packages="\n".join(dirty_packages)
                    )
                )

                unreal.log_error(message)
                unreal.EditorDialog.show_message(
                    "Unsaved Maps/Content", message, unreal.AppMsgType.OK
                )
                self.on_executor_finished_impl()
                return

        # Make sure all the maps in the queue exist on disk somewhere,
        # unsaved maps can't be loaded on the remote machine, and it's common
        # to have the wrong map name if you submit without loading the map.
        has_valid_map = (
            unreal.MoviePipelineEditorLibrary.is_map_valid_for_remote_render(
                pipeline_queue.get_jobs()
            )
        )
        if not has_valid_map:
            message = (
                "One or more jobs in the queue have an unsaved map as "
                "their target map. "
                "These unsaved maps cannot be loaded by an external process, "
                "and the render has been aborted."
            )
            unreal.log_error(message)
            unreal.EditorDialog.show_message(
                "Unsaved Maps", message, unreal.AppMsgType.OK
            )
            self.on_executor_finished_impl()
            return

        self.pipeline_queue = pipeline_queue

        deadline_settings = unreal.get_default_object(
            unreal.MoviePipelineDeadlineSettings
        )

        # Arguments to pass to the executable. This can be modified by settings
        # in the event a setting needs to be applied early.
        # In the format of -foo -bar
        # commandLineArgs = ""
        command_args = []

        # Append all of our inherited command line arguments from the editor.
        in_process_executor_settings = unreal.get_default_object(
            unreal.MoviePipelineInProcessExecutorSettings
        )
        inherited_cmds = in_process_executor_settings.inherited_command_line_arguments

        # Sanitize the commandline by removing any execcmds that may
        # have passed through the commandline.
        # We remove the execcmds because, in some cases, users may execute a
        # script that is local to their editor build for some automated
        # workflow but this is not ideal on the farm. We will expect all
        # custom startup commands for rendering to go through the `Start
        # Command` in the MRQ settings.
        inherited_cmds = re.sub(
            ".*(?P<cmds>-execcmds=[\s\S]+[\'\"])",
            "",
            inherited_cmds
        )

        command_args.extend(inherited_cmds.split(" "))
        command_args.extend(
            in_process_executor_settings.additional_command_line_arguments.split(
                " "
            )
        )

        command_args.extend(
            ["-nohmd", "-windowed", f"-ResX=1280", f"-ResY=720"]
        )

        # Get the project level preset
        project_preset = deadline_settings.default_job_preset

        # Get the job and plugin info string.
        # Note:
        #   Sometimes a project level default may not be set,
        #   so if this returns an empty dictionary, that is okay
        #   as we primarily care about the job level preset.
        #   Catch any exceptions here and continue
        try:
            project_job_info, project_plugin_info = get_deadline_info_from_preset(job_preset=project_preset)

        except Exception:
            pass

        deadline_service = get_global_deadline_service_instance()

        for job in self.pipeline_queue.get_jobs():

            unreal.log(f"Submitting Job `{job.job_name}` to Deadline...")

            try:
                # Create a Deadline job object with the default project level
                # job info and plugin info
                deadline_job = DeadlineJob(project_job_info, project_plugin_info)

                deadline_job_id = self.submit_job(
                    job, deadline_job, command_args, deadline_service
                )

            except Exception as err:
                unreal.log_error(
                    f"Failed to submit job `{job.job_name}` to Deadline, aborting render. \n\tError: {str(err)}"
                )
                unreal.log_error(traceback.format_exc())
                self.on_executor_errored_impl(None, True, str(err))
                unreal.EditorDialog.show_message(
                    "Submission Result",
                    f"Failed to submit job `{job.job_name}` to Deadline with error: {str(err)}. "
                    f"See log for more details.",
                    unreal.AppMsgType.OK,
                )
                self.on_executor_finished_impl()
                return

            if not deadline_job_id:
                message = (
                    f"A problem occurred submitting `{job.job_name}`. "
                    f"Either the job doesn't have any data to submit, "
                    f"or an error occurred getting the Deadline JobID. "
                    f"This job status would not be reflected in the UI. "
                    f"Check the logs for more details."
                )
                unreal.log_warning(message)
                unreal.EditorDialog.show_message(
                    "Submission Result", message, unreal.AppMsgType.OK
                )
                return

            else:
                unreal.log(f"Deadline JobId: {deadline_job_id}")
                self.job_ids.append(deadline_job_id)

                # Store the Deadline JobId in our job (the one that exists in
                # the queue, not the duplicate) so we can match up Movie
                # Pipeline jobs with status updates from Deadline.
                job.user_data = deadline_job_id

        # Now that we've sent a job to Deadline, we're going to request a status
        # update on them so that they transition from "Ready" to "Queued" or
        # their actual status in Deadline. self.request_job_status_update(
        # deadline_service)

        message = (
            f"Successfully submitted {len(self.job_ids)} jobs to Deadline. JobIds: {', '.join(self.job_ids)}. "
            f"\nPlease use Deadline Monitor to track render job statuses"
        )
        unreal.log(message)

        unreal.EditorDialog.show_message(
            "Submission Result", message, unreal.AppMsgType.OK
        )

        # Set the executor to finished
        self.on_executor_finished_impl()

    @unreal.ufunction(override=True)
    def is_rendering(self):
        # Because we forward unfinished jobs onto another service when the
        # button is pressed, they can always submit what is in the queue and
        # there's no need to block the queue.
        # A MoviePipelineExecutor implementation must override this. If you
        # override a ufunction from a base class you don't specify the return
        # type or parameter types.
        return False

    def submit_job(self, job, deadline_job, command_args, deadline_service):
        """
        Submit a new Job to Deadline
        :param job: Queued job to submit
        :param deadline_job: Deadline job object
        :param list[str] command_args: Commandline arguments to configure for the Deadline Job
        :param deadline_service: An instance of the deadline service object
        :returns: Deadline Job ID
        :rtype: str
        """

        # Get the Job Info and plugin Info
        # If we have a preset set on the job, get the deadline submission details
        try:
            job_info, plugin_info = get_deadline_info_from_preset(job_preset_struct=job.get_deadline_job_preset_struct_with_overrides())

        # Fail the submission if any errors occur
        except Exception as err:
            raise RuntimeError(
                f"An error occurred getting the deadline job and plugin "
                f"details. \n\tError: {err} "
            )

        # check for required fields in pluginInfo
        if "Executable" not in plugin_info:
            raise RuntimeError("An error occurred formatting the Plugin Info string. \n\tMissing \"Executable\" key")
        elif not plugin_info["Executable"]:
            raise RuntimeError(f"An error occurred formatting the Plugin Info string. \n\tExecutable value cannot be empty")
        if "ProjectFile" not in plugin_info:
            raise RuntimeError("An error occurred formatting the Plugin Info string. \n\tMissing \"ProjectFile\" key")
        elif not plugin_info["ProjectFile"]:
            raise RuntimeError(f"An error occurred formatting the Plugin Info string. \n\tProjectFile value cannot be empty")

        # Update the job info with overrides from the UI
        if job.batch_name:
            job_info["BatchName"] = job.batch_name

        if hasattr(job, "comment") and not job_info.get("Comment"):
            job_info["Comment"] = job.comment

        if not job_info.get("Name") or job_info["Name"] == "Untitled":
            job_info["Name"] = job.job_name

        if job.author:
            job_info["UserName"] = job.author

        if unreal.Paths.is_project_file_path_set():
            # Trim down to just "Game.uproject" instead of absolute path.
            game_name_or_project_file = (
                unreal.Paths.convert_relative_path_to_full(
                    unreal.Paths.get_project_file_path()
                )
            )

        else:
            raise RuntimeError(
                "Failed to get a project name. Please set a project!"
            )

        # Create a new queue with only this job in it and save it to disk,
        # then load it, so we can send it with the REST API
        new_queue = unreal.MoviePipelineQueue()
        new_job = new_queue.duplicate_job(job)

        duplicated_queue, manifest_path = unreal.MoviePipelineEditorLibrary.save_queue_to_manifest_file(
            new_queue
        )

        # Convert the queue to text (load the serialized json from disk) so we
        # can send it via deadline, and deadline will write the queue to the
        # local machines on job startup.
        serialized_pipeline = unreal.MoviePipelineEditorLibrary.convert_manifest_file_to_string(
            manifest_path
        )

        # Loop through our settings in the job and let them modify the command
        # line arguments/params.
        new_job.get_configuration().initialize_transient_settings()
        # Look for our Game Override setting to pull the game mode to start
        # with. We start with this game mode even on a blank map to override
        # the project default from kicking in.
        game_override_class = None

        out_url_params = []
        out_command_line_args = []
        out_device_profile_cvars = []
        out_exec_cmds = []
        for setting in new_job.get_configuration().get_all_settings():

            out_url_params, out_command_line_args, out_device_profile_cvars, out_exec_cmds = setting.build_new_process_command_line_args(
                out_url_params,
                out_command_line_args,
                out_device_profile_cvars,
                out_exec_cmds,
            )

            # Set the game override
            if setting.get_class() == unreal.MoviePipelineGameOverrideSetting.static_class():
                game_override_class = setting.game_mode_override

        # This triggers the editor to start looking for render jobs when it
        # finishes loading.
        out_exec_cmds.append("py mrq_rpc.py")

        # Convert the arrays of command line args, device profile cvars,
        # and exec cmds into actual commands for our command line.
        command_args.extend(out_command_line_args)

        if out_device_profile_cvars:
            # -dpcvars="arg0,arg1,..."
            command_args.append(
                '-dpcvars="{dpcvars}"'.format(
                    dpcvars=",".join(out_device_profile_cvars)
                )
            )

        if out_exec_cmds:
            # -execcmds="cmd0,cmd1,..."
            command_args.append(
                '-execcmds="{cmds}"'.format(cmds=",".join(out_exec_cmds))
            )

        # Add support for telling the remote process to wait for the
        # asset registry to complete synchronously
        command_args.append("-waitonassetregistry")

        # Build a shot-mask from this sequence, to split into the appropriate
        # number of tasks. Remove any already-disabled shots before we
        # generate a list, otherwise we make unneeded tasks which get sent to
        # machines
        shots_to_render = []
        for shot_index, shot in enumerate(new_job.shot_info):
            if not shot.enabled:
                unreal.log(
                    f"Skipped submitting shot {shot_index} in {job.job_name} "
                    f"to server due to being already disabled!"
                )
            else:
                shots_to_render.append(shot.outer_name)

        # If there are no shots enabled,
        # "these are not the droids we are looking for", move along ;)
        # We will catch this later and deal with it
        if not shots_to_render:
            unreal.log_warning("No shots enabled in shot mask, not submitting.")
            return

        # Divide the job to render by the chunk size
        # i.e {"O": "my_new_shot"} or {"0", "shot_1,shot_2,shot_4"}
        chunk_size = int(job_info.get("ChunkSize", 1))
        shots = {}
        frame_list = []
        for index in range(0, len(shots_to_render), chunk_size):

            shots[str(index)] = ",".join(shots_to_render[index : index + chunk_size])

            frame_list.append(str(index))

        job_info["Frames"] = ",".join(frame_list)

        # Get the current index of the ExtraInfoKeyValue pair, we will
        # increment the index, so we do not stomp other settings
        extra_info_key_indexs = set()
        for key in job_info.keys():
            if key.startswith("ExtraInfoKeyValue"):
                _, index = key.split("ExtraInfoKeyValue")
                extra_info_key_indexs.add(int(index))

        # Get the highest number in the index list and increment the number
        # by one
        current_index = max(extra_info_key_indexs) + 1 if extra_info_key_indexs else 0

        # Put the serialized Queue into the Job data but hidden from
        # Deadline UI
        job_info[f"ExtraInfoKeyValue{current_index}"] = f"serialized_pipeline={serialized_pipeline}"

        # Increment the index
        current_index += 1

        # Put the shot info in the job extra info keys
        job_info[f"ExtraInfoKeyValue{current_index}"] = f"shot_info={json.dumps(shots)}"
        current_index += 1

        # Set the job output directory override on the deadline job
        if hasattr(new_job, "output_directory_override"):
            if new_job.output_directory_override.path:
                job_info[f"ExtraInfoKeyValue{current_index}"] = f"output_directory_override={new_job.output_directory_override.path}"

                current_index += 1

        # Set the job filename format override on the deadline job
        if hasattr(new_job, "filename_format_override"):
            if new_job.filename_format_override:
                job_info[f"ExtraInfoKeyValue{current_index}"] = f"filename_format_override={new_job.filename_format_override}"

                current_index += 1

        # Build the command line arguments the remote machine will use.
        # The Deadline plugin will provide the executable since it is local to
        # the machine. It will also write out queue manifest to the correct
        # location relative to the Saved folder

        # Get the current commandline args from the plugin info
        plugin_info_cmd_args = [plugin_info.get("CommandLineArguments", "")]

        if not plugin_info.get("ProjectFile"):
            project_file = plugin_info.get("ProjectFile", game_name_or_project_file)
            plugin_info["ProjectFile"] = project_file

        # This is the map included in the plugin to boot up to.
        project_cmd_args = [
            f"MoviePipelineEntryMap?game={game_override_class.get_path_name()}"
        ]

        # Combine all the compiled arguments
        full_cmd_args = project_cmd_args + command_args + plugin_info_cmd_args

        # Remove any duplicates in the commandline args and convert to a string
        full_cmd_args = " ".join(list(OrderedDict.fromkeys(full_cmd_args))).strip()

        unreal.log(f"Deadline job command line args: {full_cmd_args}")

        # Update the plugin info with the commandline arguments
        plugin_info.update(
            {
                "CommandLineArguments": full_cmd_args,
                "CommandLineMode": "false",
            }
        )

        deadline_job.job_info = job_info
        deadline_job.plugin_info = plugin_info

        # Submit the deadline job
        return deadline_service.submit_job(deadline_job)

    # TODO: For performance reasons, we will skip updating the UI and request
    #  that users use a different mechanism for checking on job statuses.
    #  This will be updated once we have a performant solution.
