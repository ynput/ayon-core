"""Functions to parse asset names, versions from file names"""
import os
import re

import ayon_api

from ayon_core.lib import Logger


def get_folder_entity_from_filename(
    project_name,
    source_filename,
    version_regex,
    all_selected_folder_ids=None
):
    """Try to parse out folder name from file name provided.

    Artists might provide various file name formats.
    Currently handled:
        - chair.mov
        - chair_v001.mov
        - my_chair_to_upload.mov
    """
    version = None
    folder_name = os.path.splitext(source_filename)[0]
    # Always first check if source filename is directly folder
    #   (eg. 'chair.mov')
    matching_folder_entity = get_folder_by_name_case_not_sensitive(
        project_name, folder_name, all_selected_folder_ids)

    if matching_folder_entity is None:
        # name contains also a version
        matching_folder_entity, version = (
            parse_with_version(
                project_name,
                folder_name,
                version_regex,
                all_selected_folder_ids
            )
        )

    if matching_folder_entity is None:
        matching_folder_entity = parse_containing(
            project_name,
            folder_name,
            all_selected_folder_ids
        )

    return matching_folder_entity, version


def parse_with_version(
    project_name,
    folder_name,
    version_regex,
    all_selected_folder_ids=None,
    log=None
):
    """Try to parse folder name from a file name containing version too

    Eg. 'chair_v001.mov' >> 'chair', 1
    """
    if not log:
        log = Logger.get_logger(__name__)
    log.debug(
        ("Folder entity by \"{}\" was not found, trying version regex.".
         format(folder_name)))

    matching_folder_entity = version_number = None

    regex_result = version_regex.findall(folder_name)
    if regex_result:
        _folder_name, _version_number = regex_result[0]
        matching_folder_entity = get_folder_by_name_case_not_sensitive(
            project_name,
            _folder_name,
            all_selected_folder_ids=all_selected_folder_ids
        )
        if matching_folder_entity:
            version_number = int(_version_number)

    return matching_folder_entity, version_number


def parse_containing(project_name, folder_name, all_selected_folder_ids=None):
    """Look if file name contains any existing folder name"""
    for folder_entity in ayon_api.get_folders(
        project_name,
        folder_ids=all_selected_folder_ids,
        fields={"id", "name"}
    ):
        if folder_entity["name"].lower() in folder_name.lower():
            return ayon_api.get_folder_by_id(
                project_name,
                folder_entity["id"]
            )


def get_folder_by_name_case_not_sensitive(
    project_name,
    folder_name,
    all_selected_folder_ids=None,
    log=None
):
    """Handle more cases in file names"""
    if not log:
        log = Logger.get_logger(__name__)
    folder_name = re.compile(folder_name, re.IGNORECASE)

    folder_entities = list(ayon_api.get_folders(
        project_name,
        folder_ids=all_selected_folder_ids,
        folder_names=[folder_name]
    ))

    if len(folder_entities) > 1:
        log.warning("Too many records found for {}".format(
            folder_name))
        return None

    if folder_entities:
        return folder_entities.pop()
