import json
from ayon_core.lib import ApplicationManager
from ayon_core.pipeline import load

try:
    from ayon_openrv.api import RVConnector
except ImportError:
    raise Exception("Failed to import RVConnector from ayon_openrv.api. Is the OpenRV Addon enabled?")


class PlayInRV(load.LoaderPlugin):
    """Open Image Sequence with system default"""

    product_types = ["*"]
    representations = ["*"]
    extensions = {
        "cin", "dpx", "avi", "dv", "gif", "flv", "mkv", "mov", "mpg", "mpeg",
        "mp4", "m4v", "mxf", "iff", "z", "ifl", "jpeg", "jpg", "jfif", "lut",
        "1dl", "exr", "pic", "png", "ppm", "pnm", "pgm", "pbm", "rla", "rpf",
        "sgi", "rgba", "rgb", "bw", "tga", "tiff", "tif", "img", "h264",
    }

    label = "Open in RV"
    order = -10
    icon = "play-circle"
    color = "orange"

    def load(self, context, name, namespace, data):
        app_manager = ApplicationManager()

        representation = context.get("representation")
        if not representation:
            raise Exception(f"Missing representation data: {representation = }")
        
        folder = context.get("folder")
        if not folder:
            raise Exception(f"Missing folder data: {folder = }")

        project = context.get("project")
        if not folder:
            raise Exception(f"Missing project data: {project = }")

        rvcon = RVConnector(port=45129)

        if not rvcon.is_connected:
            # get launch context variables
            task = representation["data"]["context"].get("task")
            folder_path = folder.get("path")
            if not all([project, folder_path, task]):
                raise Exception(f"Missing context data: {project = }, {folder_path = }, {task = }")

            # launch RV with context
            ctx = {
                "project_name": project["name"],
                "folder_path": folder_path,
                "task_name": task["name"] or "generic",
            }
            openrv_app = app_manager.find_latest_available_variant_for_group("openrv")
            openrv_app.launch(**ctx)

        _data = [{
            "project_name": project["name"],
            "objectName": representation["context"]["representation"],
            "representation": representation["id"],
        }]
        payload = json.dumps(_data)
        self.log.warning(f"{payload = }")
        with rvcon: # this also retries the connection
            rvcon.send_event("ayon_load_container", payload, shall_return=False)
