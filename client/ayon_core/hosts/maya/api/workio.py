"""Host API required Work Files tool"""
import os
from maya import cmds


def file_extensions():
    return [".ma", ".mb"]


def has_unsaved_changes():
    return cmds.file(query=True, modified=True)


def save_file(filepath):
    cmds.file(rename=filepath)
    ext = os.path.splitext(filepath)[1]
    if ext == ".mb":
        file_type = "mayaBinary"
    else:
        file_type = "mayaAscii"
    cmds.file(save=True, type=file_type)


def open_file(filepath):
    return cmds.file(filepath, open=True, force=True)


def current_file():

    current_filepath = cmds.file(query=True, sceneName=True)
    if not current_filepath:
        return None

    return current_filepath
