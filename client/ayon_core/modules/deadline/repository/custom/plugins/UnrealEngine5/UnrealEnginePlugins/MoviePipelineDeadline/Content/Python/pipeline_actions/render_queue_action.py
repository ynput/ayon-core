# Copyright Epic Games, Inc. All Rights Reserved

# Built-in
import argparse
import re
from pathlib import Path
from getpass import getuser
from collections import OrderedDict

# Internal
from deadline_service import get_global_deadline_service_instance
from deadline_job import DeadlineJob
from deadline_menus import DeadlineToolBarMenu
from deadline_utils import get_deadline_info_from_preset

# Third Party
import unreal


# Editor Utility Widget path
# NOTE: This is very fragile and can break if naming or pathing changes
EDITOR_UTILITY_WIDGET = "/MoviePipelineDeadline/Widgets/QueueAssetSubmitter"


def _launch_queue_asset_submitter():
    """
    Callback to execute to launch the queue asset submitter
    """
    unreal.log("Launching queue submitter.")

    submitter_widget = unreal.EditorAssetLibrary.load_asset(EDITOR_UTILITY_WIDGET)

    # Get editor subsystem
    subsystem = unreal.get_editor_subsystem(unreal.EditorUtilitySubsystem)

    # Spawn the submitter widget
    subsystem.spawn_and_register_tab(submitter_widget)


def register_menu_action():
    """
    Creates the toolbar menu
    """

    if not _validate_euw_asset_exists():
        unreal.log_warning(
            f"EUW `{EDITOR_UTILITY_WIDGET}` does not exist in the Asset registry!"
        )
        return

    toolbar = DeadlineToolBarMenu()

    toolbar.register_submenu(
        "SubmitMRQAsset",
        _launch_queue_asset_submitter,
        label_name="Submit Movie Render Queue Asset",
        description="Submits a Movie Render Queue asset to Deadline"
    )


def _validate_euw_asset_exists():
    """
    Make sure our reference editor utility widget exists in
    the asset registry
    :returns: Array(AssetData) or None
    """

    asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
    asset_data = asset_registry.get_assets_by_package_name(
        EDITOR_UTILITY_WIDGET,
        include_only_on_disk_assets=True
    )

    return True if asset_data else False


def _execute_submission(args):
    """
    Creates and submits the queue asset as a job to Deadline
    :param args: Commandline args
    """

    unreal.log("Executing job submission")

    job_info, plugin_info = get_deadline_info_from_preset(
        job_preset=unreal.load_asset(args.submission_job_preset)
    )

    # Due to some odd behavior in how Unreal passes string to the argparse,
    # it adds extra quotes to the string, so we will strip the quotes out to get
    # a single string representation.
    batch_name = args.batch_name[0].strip('"')

    # Update the Job Batch Name
    job_info["BatchName"] = batch_name

    # Set the name of the job if one is not set
    if not job_info.get("Name"):
        job_info["Name"] = Path(args.queue_asset).stem

    # Set the Author of the job
    if not job_info.get("UserName"):
        job_info["UserName"] = getuser()

    # Arguments to pass to the executable.
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
        ".(?P<cmds>-execcmds=[\w\W]+[\'\"])",
        "",
        inherited_cmds
    )

    command_args.extend(inherited_cmds.split(" "))
    command_args.extend(
        in_process_executor_settings.additional_command_line_arguments.split(
            " "
        )
    )

    # Build out custom queue command that will be used to render the queue on
    # the farm.
    queue_cmds = [
        "py",
        "mrq_cli.py",
        "queue",
        str(args.queue_asset),
        "--remote",
        "--cmdline",
        "--batch_name",
        batch_name,
        "--deadline_job_preset",
        str(args.remote_job_preset)
    ]

    command_args.extend(
        [
            "-nohmd",
            "-windowed",
            "-ResX=1280",
            "-ResY=720",
            '-execcmds="{cmds}"'.format(cmds=" ".join(queue_cmds))
        ]
    )

    # Append the commandline args from the deadline plugin info
    command_args.extend(plugin_info.get("CommandLineArguments", "").split(" "))

    # Sanitize the commandline args
    command_args = [arg for arg in command_args if arg not in [None, "", " "]]

    # Remove all duplicates from the command args
    full_cmd_args = " ".join(list(OrderedDict.fromkeys(command_args)))

    # Get the current launched project file
    if unreal.Paths.is_project_file_path_set():
        # Trim down to just "Game.uproject" instead of absolute path.
        game_name_or_project_file = (
            unreal.Paths.convert_relative_path_to_full(
                unreal.Paths.get_project_file_path()
            )
        )

    else:
        raise RuntimeError(
            "Failed to get a project name. Please specify a project!"
        )

    if not plugin_info.get("ProjectFile"):
        project_file = plugin_info.get("ProjectFile", game_name_or_project_file)
        plugin_info["ProjectFile"] = project_file

    # Update the plugin info. "CommandLineMode" tells Deadline to not use an
    # interactive process to execute the job but launch it like a shell
    # command and wait for the process to exit. `--cmdline` in our
    # commandline arguments will tell the editor to shut down when the job is
    # complete
    plugin_info.update(
        {
            "CommandLineArguments": full_cmd_args,
            "CommandLineMode": "true"
        }
    )

    # Create a Deadline job from the selected preset library
    deadline_job = DeadlineJob(job_info, plugin_info)

    deadline_service = get_global_deadline_service_instance()

    # Submit the Deadline Job
    job_id = deadline_service.submit_job(deadline_job)

    unreal.log(f"Deadline job submitted. JobId: {job_id}")


if __name__ == "__main__":
    unreal.log("Executing queue submitter action")

    parser = argparse.ArgumentParser(
        description="Submits queue asset to Deadline",
        add_help=False,
    )
    parser.add_argument(
        "--batch_name",
        type=str,
        nargs='+',
        help="Deadline Batch Name"
    )
    parser.add_argument(
        "--submission_job_preset",
        type=str,
        help="Submitter Deadline Job Preset"
    )
    parser.add_argument(
        "--remote_job_preset",
        type=str,
        help="Remote Deadline Job Preset"
    )
    parser.add_argument(
        "--queue_asset",
        type=str,
        help="Movie Pipeline Queue Asset"
    )

    parser.set_defaults(func=_execute_submission)

    # Parse the arguments and execute the function callback
    arguments = parser.parse_args()
    arguments.func(arguments)
