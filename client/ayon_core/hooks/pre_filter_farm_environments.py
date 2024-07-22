import copy
import re

from ayon_applications import PreLaunchHook, LaunchTypes
from ayon_core.lib import filter_profiles


class FilterFarmEnvironments(PreLaunchHook):
    """Filter or modify calculated environment variables for farm rendering.

    This hook must run last, only after all other hooks are finished to get
    correct environment for launch context.

    Implemented modifications to self.launch_context.env:
    - skipping (list) of environment variable keys
    - removing value in environment variable:
        - supports regular expression in pattern
        - doesn't remove env var if value empty!
    """
    order = 1000

    launch_types = {LaunchTypes.farm_publish}

    def execute(self):
        data = self.launch_context.data
        project_settings = data["project_settings"]
        filter_env_profiles = (
            project_settings["core"]["filter_farm_environment"])

        if not filter_env_profiles:
            self.log.debug("No profiles found for env var filtering")
            return

        task_entity = data["task_entity"]

        filter_data = {
            "host_names": self.host_name,
            "task_types": task_entity["taskType"],
            "task_names": task_entity["name"],
            "folder_paths": data["folder_path"]
        }
        matching_profile = filter_profiles(
            filter_env_profiles, filter_data, logger=self.log
        )
        if not matching_profile:
            self.log.debug("No matching profile found for env var filtering "
                           f"for {filter_data}")
            return

        calculated_env = copy.deepcopy(self.launch_context.env)

        calculated_env = self._skip_environment_variables(
            calculated_env, matching_profile)

        calculated_env = self._modify_environment_variables(
            calculated_env, matching_profile)

        self.launch_context.env = calculated_env

    def _modify_environment_variables(self, calculated_env, matching_profile):
        """Modify environment variable values."""
        for env_item in matching_profile["replace_in_environment"]:
            value = calculated_env.get(env_item["environment_key"])
            if not value:
                continue

            value = re.sub(value, env_item["pattern"], env_item["replacement"])
            calculated_env[env_item["environment_key"]] = value

        return calculated_env

    def _skip_environment_variables(self, calculated_env, matching_profile):
        """Skips list of environment variable names"""
        for skip_env in matching_profile["skip_environment"]:
            self.log.info(f"Skipping {skip_env}")
            calculated_env.pop(skip_env)

        return calculated_env
