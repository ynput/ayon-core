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

        rvcon = RVConnector(port=45129)

        if not rvcon.is_connected:
            project = representation["data"]["context"].get("project")
            folder = representation["data"]["context"].get("folder")
            task = representation["data"]["context"].get("task")
            if not all([project, folder, task]):
                raise Exception(f"Missing context data: {project = }, {folder = }, {task = }")

            ctx = {
                "project_name": project["name"],
                "folder_path": folder["name"],
                "task_name": task["name"] or "generic",
            }
            self.log.warning(f"{ctx = }")

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
