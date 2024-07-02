# Copyright Epic Games, Inc. All Rights Reserved

# Built-in
import argparse
from getpass import getuser

# Internal
from deadline_service import get_global_deadline_service_instance
from deadline_job import DeadlineJob
from deadline_menus import DeadlineToolBarMenu

# Third Party
import unreal

# Editor Utility Widget path
# NOTE: This is very fragile and can break if naming or pathing changes
EDITOR_UTILITY_WIDGET = "/UnrealDeadlineService/Widgets/DeadlineJobSubmitter"


def _launch_job_submitter():
    """
    Callback to execute to launch the job submitter
    """
    unreal.log("Launching job submitter.")

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
            f"EUW {EDITOR_UTILITY_WIDGET} does not exist in the Asset registry!"
        )
        return

    toolbar = DeadlineToolBarMenu()

    toolbar.register_submenu(
        "SubmitDeadlineJob",
        _launch_job_submitter,
        label_name="Submit Deadline Job",
        description="Submits a job to Deadline"
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
    Creates and submits a job to Deadline
    :param args: Commandline args
    """

    unreal.log("Executing job submission")

    # Create a Deadline job from the selected job preset
    deadline_job = DeadlineJob(job_preset=unreal.load_asset(args.job_preset_asset))

    # If there is no author set, use the current user
    if not deadline_job.job_info.get("UserName", None):
        deadline_job.job_info = {"UserName": getuser()}

    deadline_service = get_global_deadline_service_instance()

    # Submit the Deadline Job
    job_id = deadline_service.submit_job(deadline_job)

    unreal.log(f"Deadline job submitted. JobId: {job_id}")


if __name__ == "__main__":
    unreal.log("Executing job submitter action")

    parser = argparse.ArgumentParser(
        description="Submits a job to Deadline",
        add_help=False,
    )

    parser.add_argument(
        "--job_preset_asset",
        type=str,
        help="Deadline Job Preset Asset"
    )

    parser.set_defaults(func=_execute_submission)

    # Parse the arguments and execute the function callback
    arguments = parser.parse_args()
    arguments.func(arguments)
