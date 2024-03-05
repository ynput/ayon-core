"""Pipeline tools for AYON Zbrush integration."""
import os
import ast
import json
import shutil
import logging
import requests
import tempfile
import pyblish.api
from ayon_core.host import HostBase, IWorkfileHost, ILoadHost, IPublishHost
from ayon_core.pipeline import (
    register_creator_plugin_path,
    register_loader_plugin_path,
    AVALON_CONTAINER_ID,
    registered_host
)
from ayon_core.pipeline.context_tools import get_global_context

from ayon_core.settings import get_current_project_settings
from ayon_core.lib import register_event_callback
from ayon_core.hosts.zbrush import ZBRUSH_HOST_DIR
from .lib import execute_zscript, get_workdir

METADATA_SECTION = "avalon"
ZBRUSH_SECTION_NAME_CONTEXT = "context"
ZBRUSH_METADATA_CREATE_CONTEXT = "create_context"
ZBRUSH_SECTION_NAME_INSTANCES = "instances"
ZBRUSH_SECTION_NAME_CONTAINERS = "containers"


log = logging.getLogger("ayon.hosts.zbrush")


class ZbrushHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "zbrush"

    def install(self):
        # Create workdir folder if does not exist yet
        workdir = os.getenv("AYON_WORKDIR")
        if not os.path.exists(workdir):
            os.makedirs(workdir)

        plugins_dir = os.path.join(ZBRUSH_HOST_DIR, "plugins")
        publish_dir = os.path.join(plugins_dir, "publish")
        load_dir = os.path.join(plugins_dir, "load")
        create_dir = os.path.join(plugins_dir, "create")

        pyblish.api.register_host("zbrush")
        pyblish.api.register_plugin_path(publish_dir)
        register_loader_plugin_path(load_dir)
        register_creator_plugin_path(create_dir)

        register_event_callback("application.launched", self.initial_app_launch)
        register_event_callback("application.exit", self.application_exit)


    def get_current_project_name(self):
        """
        Returns:
            Union[str, None]: Current project name.
        """

        return self.get_current_context().get("project_name")

    def get_current_folder_path(self):
        """
        Returns:
            Union[str, None]: Current asset name.
        """

        return self.get_current_context().get("folder_path")

    def get_current_task_name(self):
        """
        Returns:
            Union[str, None]: Current task name.
        """

        return self.get_current_context().get("task_name")

    def get_current_context(self):
        context = get_current_workfile_context()
        if not context:
            return get_global_context()
        if "project_name" in context:
            return context
        # This is legacy way how context was stored
        return {
            "project_name": context.get("project"),
            "folder_path": context.get("folder_path"),
            "task_name": context.get("task")
        }
    # --- Workfile ---
    def open_workfile(self, filepath):
        open_file_zscript = ("""
[IFreeze,
[MemCreate, currentfile, 1000, 0]
[VarSet, filename, "{filepath}"]
[MemWriteString, currentfile, #filename, 0]
[FileNameSetNext, #filename]
[IKeyPress, 13, [IPress, File:Open:Open]]]
[MemDelete, currentfile]
]
    """).format(filepath=filepath)
        execute_zscript(open_file_zscript)
        set_current_file(filepath=filepath)
        return filepath

    def save_workfile(self, filepath=None):
        if not filepath:
            filepath = self.get_current_workfile()
        filepath = filepath.replace("\\", "/")
        save_file_zscript = ("""
[IFreeze,
[MemCreate, currentfile, 1000, 0]
[VarSet, filename, "{filepath}"]
[MemWriteString, currentfile, #filename, 0]
[FileNameSetNext, #filename]
[IKeyPress, 13, [IPress, File:SaveAs:SaveAs]]]
[MemDelete, currentfile]
]
""").format(filepath=filepath)
        context = get_global_context()
        # save_current_workfile_context(context)
        # # move the json data to the files
        # # shutil.copy
        copy_ayon_data(filepath)
        set_current_file(filepath=filepath)
        execute_zscript(save_file_zscript)
        return filepath

    def work_root(self, session):
        return session["AYON_WORKDIR"]

    def get_current_workfile(self):
        project_name = get_current_context()["project_name"]
        folder_path = get_current_context()["folder_path"]
        task_name = get_current_context()["task_name"]
        work_dir = get_workdir(project_name, folder_path, task_name)
        txt_dir = os.path.join(
            work_dir, ".zbrush_metadata").replace(
                "\\", "/"
        )
        with open (f"{txt_dir}/current_file.txt", "r") as current_file:
            content = str(current_file.read())
            filepath = content.rstrip('\x00')
            current_file.close()
            return filepath

    def workfile_has_unsaved_changes(self):
        # Pop-up dialog would be located to ask if users
        # save scene if it has unsaved changes
        return False

    def get_workfile_extensions(self):
        return [".zpr"]

    def list_instances(self):
        """Get all AYON instances."""
        # Figure out how to deal with this
        return get_instance_workfile_metadata(ZBRUSH_SECTION_NAME_INSTANCES)

    def write_instances(self, data):
        return write_workfile_metadata(ZBRUSH_SECTION_NAME_INSTANCES, data)

    def get_containers(self):
        return get_containers()

    def initial_app_launch(self):
        #TODO: figure out how to deal with the last workfile issue
        set_current_file()

    def application_exit(self):
        """Logic related to TimerManager.

        Todo:
            This should be handled out of Zbrush integration logic.
        """
        remove_tmp_data()
        data = get_current_project_settings()
        stop_timer = data["zbrush"]["stop_timer_on_application_exit"]

        if not stop_timer:
            return

        # Stop application timer.
        webserver_url = os.environ.get("AYON_WEBSERVER_URL")
        rest_api_url = "{}/timers_manager/stop_timer".format(webserver_url)
        requests.post(rest_api_url)

    def update_context_data(self, data, changes):
        return write_workfile_metadata(ZBRUSH_METADATA_CREATE_CONTEXT, data)

    def get_context_data(self):
        get_load_workfile_metadata(ZBRUSH_METADATA_CREATE_CONTEXT)

def containerise(
        name, context, namespace="", loader=None, containers=None):
    data = {
        "schema": "openpype:container-2.0",
        "id": AVALON_CONTAINER_ID,
        "name": name,
        "namespace": namespace,
        "loader": str(loader),
        "representation": str(context["representation"]["_id"]),
    }
    if containers is None:
        containers = get_containers()

    containers.append(data)

    write_load_metadata(ZBRUSH_SECTION_NAME_CONTAINERS, containers)
    return data


def save_current_workfile_context(context):
    return write_workfile_metadata(ZBRUSH_SECTION_NAME_CONTEXT, context)

def write_workfile_metadata(metadata_key, data=None):
    if data is None:
        data = []
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, metadata_key).replace(
            "\\", "/"
        )
    os.makedirs(json_dir, exist_ok=True)
    with open (f"{json_dir}/{metadata_key}.json", "w") as file:
        value = json.dumps(data)
        file.write(value)
        file.close()


def get_current_workfile_context():
    return get_load_workfile_metadata(ZBRUSH_SECTION_NAME_CONTEXT)


def get_current_context():
    return {
        "project_name": os.environ.get("AYON_PROJECT_NAME"),
        "folder_path": os.environ.get("AYON_FOLDER_PATH"),
        "task_name": os.environ.get("AYON_TASK_NAME")
    }


def get_workfile_metadata(metadata_key, default=None):
    if default is None:
        default = []
    output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_zb_meta", suffix=".txt", delete=False
    )
    output_file.close()
    output_filepath = output_file.name.replace("\\", "/")
    context_data_zscript = ("""
[IFreeze,
[If, [MemCreate, {metadata_key}, 400000, 0] !=-1,
[MemCreate, {metadata_key}, 400000, 0]
[MemWriteString, {metadata_key}, "{default}", 0]]
[MemSaveToFile, {metadata_key}, "{output_filepath}", 1]
[MemDelete, {metadata_key}]
]
""").format(metadata_key=metadata_key,
            default=default, output_filepath=output_filepath)
    execute_zscript(context_data_zscript)
    with open(output_filepath) as data:
        file_content = str(data.read().strip()).rstrip('\x00')
        file_content = ast.literal_eval(file_content)
    return file_content


def get_containers():
    output = get_load_workfile_metadata(ZBRUSH_SECTION_NAME_CONTAINERS)
    if output:
        for item in output:
            if "objectName" not in item and "name" in item:
                members = item["name"]
                if isinstance(members, list):
                    members = "|".join([str(member) for member in members])
                item["objectName"] = members

    return output

def write_load_metadata(metadata_key, data):
    #TODO: create temp json file
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    name = next((d["name"] for d in data), None)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, metadata_key).replace(
            "\\", "/"
        )
    os.makedirs(json_dir, exist_ok=True)
    json_file = f"{json_dir}/{name}.json"
    if os.path.exists(json_file):
        with open(json_file, "w"): pass
    with open (json_file, "w") as file:
        value = json.dumps(data)
        file.write(value)
        file.close()


def get_load_workfile_metadata(metadata_key):
    # save zscript to the hidden folder
    # load json files
    file_content = []
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, metadata_key).replace(
            "\\", "/"
        )
    if not os.path.exists(json_dir):
        return file_content
    file_list = os.listdir(json_dir)
    if not file_list:
        return file_content
    for file in file_list:
        with open (f"{json_dir}/{file}", "r") as data:
            content = ast.literal_eval(str(data.read().strip()))
            file_content.extend(content)
            data.close()
    return file_content


def get_instance_workfile_metadata(metadata_key):
    # save zscript to the hidden folder
    # load json files
    file_content = []
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, metadata_key).replace(
            "\\", "/"
        )
    if not os.path.exists(json_dir) or not os.listdir(json_dir):
        return file_content
    for file in os.listdir(json_dir):
        with open (f"{json_dir}/{file}", "r") as data:
            file_content = json.load(data)

    return file_content


def remove_container_data(name):
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, ZBRUSH_SECTION_NAME_CONTAINERS).replace(
            "\\", "/"
        )
    all_fname_list = os.listdir(json_dir)
    json_file = next((jfile for jfile in all_fname_list
                               if jfile == f"{name}.json"), None)
    if json_file:
        os.remove(f"{json_dir}/{json_file}")


def remove_tmp_data():
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    work_dir = get_workdir(project_name, folder_path, task_name)
    for name in [ZBRUSH_SECTION_NAME_CONTEXT,
                 ZBRUSH_METADATA_CREATE_CONTEXT,
                 ZBRUSH_SECTION_NAME_INSTANCES,
                 ZBRUSH_SECTION_NAME_CONTAINERS]:
        json_dir = os.path.join(
            work_dir, ".zbrush_metadata", name).replace(
                "\\", "/"
            )
        if not os.path.exists(json_dir):
            continue
        all_fname_list = [jfile for jfile in os.listdir(json_dir)
                          if jfile.endswith("json")]
        for fname in all_fname_list:
            os.remove(f"{json_dir}/{fname}")


def copy_ayon_data(filepath):
    filename = os.path.splitext(os.path.basename(filepath))[0].strip()
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    for name in [ZBRUSH_SECTION_NAME_CONTEXT,
                 ZBRUSH_METADATA_CREATE_CONTEXT,
                 ZBRUSH_SECTION_NAME_INSTANCES,
                 ZBRUSH_SECTION_NAME_CONTAINERS]:
        src_json_dir = os.path.join(
            work_dir, ".zbrush_metadata", current_file, name).replace(
                "\\", "/"
            )
        if not os.path.exists(src_json_dir):
            continue
        dst_json_dir = os.path.join(
            work_dir, ".zbrush_metadata", filename, name).replace(
                "\\", "/"
            )
        os.makedirs(dst_json_dir, exist_ok=True)
        all_fname_list = [jfile for jfile in os.listdir(src_json_dir)
                        if jfile.endswith("json")]
        if all_fname_list:
            for fname in all_fname_list:
                src_json = f"{src_json_dir}/{fname}"
                dst_json = f"{dst_json_dir}/{fname}"
                shutil.copy(src_json, dst_json)


def set_current_file(filepath=None):
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    work_dir = get_workdir(project_name, folder_path, task_name)
    txt_dir = os.path.join(
        work_dir, ".zbrush_metadata").replace(
            "\\", "/"
    )
    os.makedirs(txt_dir, exist_ok=True)
    txt_file = f"{txt_dir}/current_file.txt"
    if filepath is None:
        with open(txt_file, 'w'): pass
        return filepath
    filepath_check = tmp_current_file_check()
    if filepath_check.endswith("zpr"):
        filepath = os.path.join(
            os.path.dirname(filepath), filepath_check).replace("\\", "/")
    with open (txt_file, "w") as current_file:
        current_file.write(filepath)
        current_file.close()


def imprint(container, representation_id):
    old_container_data = []
    data = {}
    name = container["objectName"]
    project_name = get_current_context()["project_name"]
    folder_path = get_current_context()["folder_path"]
    task_name = get_current_context()["task_name"]
    current_file = registered_host().get_current_workfile()
    if current_file:
        current_file = os.path.splitext(
            os.path.basename(current_file))[0].strip()
    work_dir = get_workdir(project_name, folder_path, task_name)
    json_dir = os.path.join(
        work_dir, ".zbrush_metadata",
        current_file, ZBRUSH_SECTION_NAME_CONTAINERS).replace(
            "\\", "/"
        )
    js_fname = next((jfile for jfile in os.listdir(json_dir)
                     if jfile.endswith(f"{name}.json")), None)
    if js_fname:
        with open(f"{json_dir}/{js_fname}", "r") as file:
            old_container_data = json.load(file)
            print(f"data: {type(old_container_data)}")
            file.close()

        open(f"{json_dir}/{js_fname}", 'w').close()
        for item in old_container_data:
            item["representation"] = representation_id
            data.update(item)
        with open(f"{json_dir}/{js_fname}", "w") as file:
            new_container_data = json.dumps([data])
            file.write(new_container_data)
            file.close()

def tmp_current_file_check():
    output_file = tempfile.NamedTemporaryFile(
        mode="w", prefix="a_zb_cfc", suffix=".txt", delete=False
    )
    output_file.close()
    output_filepath = output_file.name.replace("\\", "/")
    context_data_zscript = ("""
[IFreeze,
	[MemCreate, currentfile, 1000, 0]
    [VarSet, currentfile, [FileNameExtract, [FileNameGetLastUsed], 2+4]]
	[MemWriteString, currentfile, #filename, 0]
	[MemSaveToFile, currentfile, "{output_filepath}", 0]
	[Note, currentfile]
	[MemDelete, currentfile]
]
""").format(output_filepath=output_filepath)
    execute_zscript(context_data_zscript)
    with open(output_filepath) as data:
        file_content = str(data.read().strip()).rstrip('\x00')
    os.remove(output_filepath)
    return file_content
