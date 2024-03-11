# Copyright Epic Games, Inc. All Rights Reserved

"""
General Deadline utility functions
"""
# Built-in
from copy import deepcopy
import json
import re

import unreal


def format_job_info_json_string(json_string, exclude_aux_files=False):
    """
    Deadline Data asset returns a json string, load the string and format the job info in a dictionary
    :param str json_string: Json string from deadline preset struct
    :param bool exclude_aux_files: Excludes the aux files from the returned job info dictionary if True
    :return: job Info dictionary
    """

    if not json_string:
        raise RuntimeError(f"Expected json string value but got `{json_string}`")

    job_info = {}

    try:
        intermediate_info = json.loads(json_string)
    except Exception as err:
        raise RuntimeError(f"An error occurred formatting the Job Info string. \n\t{err}")
       
    project_settings = unreal.get_default_object(unreal.DeadlineServiceEditorSettings)
    script_category_mappings = project_settings.script_category_mappings

    # The json string keys are camelCased keys which are not the expected input
    # types for Deadline. Format the keys to PascalCase.
    for key, value in intermediate_info.items():

        # Remove empty values
        if not value:
            continue

        # Deadline does not support native boolean so make it a string
        if isinstance(value, bool):
            value = str(value).lower()

        pascal_case_key = re.sub("(^\S)", lambda string: string.group(1).upper(), key)

        if (pascal_case_key == "AuxFiles") and not exclude_aux_files:

            # The returned json string lists AuxFiles as a list of
            # Dictionaries but the expected value is a list of
            # strings. reformat this input into the expected value
            aux_files = []
            for files in value:
                aux_files.append(files["filePath"])

            job_info[pascal_case_key] = aux_files

            continue

        # Extra option that can be set on the job info are packed inside a
        # ExtraJobOptions key in the json string.
        # Extract this is and add it as a flat setting in the job info
        elif pascal_case_key == "ExtraJobOptions":
            job_info.update(value)

            continue

        # Resolve the job script paths to be sent to be sent to the farm.
        elif pascal_case_key in ["PreJobScript", "PostJobScript", "PreTaskScript", "PostTaskScript"]:

            # The path mappings in the project settings are a dictionary
            # type with the script category as a named path for specifying
            # the root directory of a particular script. The User interface
            # exposes the category which is what's in the json string. We
            # will use this category to look up the actual path mappings in
            # the project settings.
            script_category = intermediate_info[key]["scriptCategory"]
            script_name = intermediate_info[key]["scriptName"]
            if script_category and script_name:
                job_info[pascal_case_key] = f"{script_category_mappings[script_category]}/{script_name}"

            continue

        # Environment variables for Deadline are numbered key value pairs in
        # the form EnvironmentKeyValue#.
        # Conform the Env settings to the expected Deadline configuration
        elif (pascal_case_key == "EnvironmentKeyValue") and value:

            for index, (env_key, env_value) in enumerate(value.items()):
                job_info[f"EnvironmentKeyValue{index}"] = f"{env_key}={env_value}"

            continue

        # ExtraInfoKeyValue for Deadline are numbered key value pairs in the
        # form ExtraInfoKeyValue#.
        # Conform the setting to the expected Deadline configuration
        elif (pascal_case_key == "ExtraInfoKeyValue") and value:

            for index, (env_key, env_value) in enumerate(value.items()):
                job_info[f"ExtraInfoKeyValue{index}"] = f"{env_key}={env_value}"

            continue

        else:
            # Set the rest of the functions
            job_info[pascal_case_key] = value

    # Remove our custom representation of Environment and ExtraInfo Key value
    # pairs from the dictionary as the expectation is that these have been
    # conformed to deadline's expected key value representation
    for key in ["EnvironmentKeyValue", "ExtraInfoKeyValue"]:
        job_info.pop(key, None)

    return job_info


def format_plugin_info_json_string(json_string):
    """
    Deadline Data asset returns a json string, load the string and format the plugin info in a dictionary
    :param str json_string: Json string from deadline preset struct
    :return: job Info dictionary
    """

    if not json_string:
        raise RuntimeError(f"Expected json string value but got `{json_string}`")

    plugin_info = {}

    try:
        info = json.loads(json_string)
        plugin_info = info["pluginInfo"]

    except Exception as err:
        raise RuntimeError(f"An error occurred formatting the Plugin Info string. \n\t{err}")
    
    # The plugin info is listed under the `plugin_info` key.
    # The json string keys are camelCased on struct conversion to json.
    return plugin_info


def get_deadline_info_from_preset(job_preset=None, job_preset_struct=None):
    """
    This method returns the job info and plugin info from a deadline preset
    :param unreal.DeadlineJobPreset job_preset:  Deadline preset asset
    :param unreal.DeadlineJobPresetStruct job_preset_struct: The job info and plugin info in the job preset
    :return: Returns a tuple with the job info and plugin info dictionary
    :rtype: Tuple
    """

    job_info = {}
    plugin_info = {}
    preset_struct = None

    # TODO: Make sure the preset library is a loaded asset
    if job_preset is not None:
        preset_struct = job_preset.job_preset_struct

    if job_preset_struct is not None:
        preset_struct = job_preset_struct

    if preset_struct:
        # Get the Job Info and plugin Info
        try:
            job_info = dict(unreal.DeadlineServiceEditorHelpers.get_deadline_job_info(preset_struct))

            plugin_info = dict(unreal.DeadlineServiceEditorHelpers.get_deadline_plugin_info(preset_struct))

        # Fail the submission if any errors occur
        except Exception as err:
            unreal.log_error(
                f"Error occurred getting deadline job and plugin details. \n\tError: {err}"
            )
            raise

    return job_info, plugin_info


def merge_dictionaries(first_dictionary, second_dictionary):
    """
    This method merges two dictionaries and returns a new dictionary as a merger between the two
    :param dict first_dictionary: The first dictionary
    :param dict second_dictionary: The new dictionary to merge in
    :return: A new dictionary based on a merger of the input dictionaries
    :rtype: dict
    """
    # Make sure we do not overwrite our input dictionary
    output_dictionary = deepcopy(first_dictionary)

    for key in second_dictionary:
        if isinstance(second_dictionary[key], dict):
            if key not in output_dictionary:
                output_dictionary[key] = {}
            output_dictionary[key] = merge_dictionaries(output_dictionary[key], second_dictionary[key])
        else:
            output_dictionary[key] = second_dictionary[key]

    return output_dictionary


def get_editor_deadline_globals():
    """
    Get global storage that will persist for the duration of the
    current interpreter/process.

    .. tip::

        Please namespace or otherwise ensure unique naming of any data stored
        into this dictionary, as key clashes are not handled/safety checked.

    :return: Global storage
    :rtype: dict
    """
    import __main__
    try:
        return __main__.__editor_deadline_globals__
    except AttributeError:
        __main__.__editor_deadline_globals__ = {}
        return __main__.__editor_deadline_globals__
