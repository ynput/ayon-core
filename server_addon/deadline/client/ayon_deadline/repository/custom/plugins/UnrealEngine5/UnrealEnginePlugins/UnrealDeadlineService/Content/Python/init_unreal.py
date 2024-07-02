# Copyright Epic Games, Inc. All Rights Reserved

# Built-in
import sys
from pathlib import Path

from deadline_utils import get_editor_deadline_globals
from deadline_service import DeadlineService

# Third-party
import unreal

plugin_name = "DeadlineService"


# Add the actions path to sys path
actions_path = Path(__file__).parent.joinpath("service_actions").as_posix()

if actions_path not in sys.path:
    sys.path.append(actions_path)

# The asset registry may not be fully loaded by the time this is called,
# warn the user that attempts to look assets up may fail
# unexpectedly.
# Look for a custom commandline start key `-waitonassetregistry`. This key
# is used to trigger a synchronous wait on the asset registry to complete.
# This is useful in commandline states where you explicitly want all assets
# loaded before continuing.
asset_registry = unreal.AssetRegistryHelpers.get_asset_registry()
if asset_registry.is_loading_assets() and ("-waitonassetregistry" in unreal.SystemLibrary.get_command_line().split()):
    unreal.log_warning(
        f"Asset Registry is still loading. The {plugin_name} plugin will "
        f"be loaded after the Asset Registry is complete."
    )

    asset_registry.wait_for_completion()
    unreal.log(f"Asset Registry is complete. Loading {plugin_name} plugin.")

# Create a global instance of the deadline service. This is useful for
# unreal classes that are not able to save the instance as an
# attribute on the class. Because the Deadline Service is a singleton,
# any new instance created from the service module will return the global
# instance
deadline_globals = get_editor_deadline_globals()

try:
    deadline_globals["__deadline_service_instance__"] = DeadlineService()
except Exception as err:
    raise RuntimeError(f"An error occurred creating a Deadline service instance. \n\tError: {str(err)}")

from service_actions import submit_job_action

# Register the menu from the render queue actions
submit_job_action.register_menu_action()
