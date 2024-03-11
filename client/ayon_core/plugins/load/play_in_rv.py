import json
from time import sleep, time
from ayon_core.lib import ApplicationManager
from ayon_core.pipeline import load, get_current_context

from ayon_openrv.api import RvCommunicator


class PlayInRV(load.LoaderPlugin):
    """Open Image Sequence with system default"""

    families = ["*"]
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

        representation = context.get("representation")
        if not representation:
            raise Exception(f"Missing representation data: {representation = }")

        try:
            app_manager = ApplicationManager()
            rvcon = RvCommunicator(name)
            rvcon.connect("localhost".encode("utf-8"), 45128)
        except Exception as err:
            self.log.warning(f"Failed to connect to RV: {err}")
        # finally:
        #     rvcon.disconnect()

        if not rvcon.connected:
            project = representation["data"]["context"].get("project")
            folder = representation["data"]["context"].get("folder")
            task = representation["data"]["context"].get("task")
            if not all([project, folder, task]):
                raise Exception(f"Missing context data: {project = }, {folder = }, {task = }")

            ctx = {
                "project_name": project["name"],
                "folder_path": folder["name"],
                "task_name": task["name"],
            }
            self.log.warning(f"{ctx = }")

            openrv_app = app_manager.find_latest_available_variant_for_group("openrv")
            openrv_app.launch(**ctx)

            try:
                for _ in range(60):
                    self.log.warning("Trying to connect to RV")
                    rvcon.connect("localhost".encode("utf-8"), 45128)
                    if rvcon.connected:
                        break
                    sleep(1)
            except Exception:
                raise Exception("Failed to connect to RV")

        _data = [{
            # "objectName": representation["context"]["representation"],
            "objectName": "LoadClip_exr",
            "representation": representation["_id"],
        }]
        payload = json.dumps(_data)
        self.log.warning(f"{payload = }")
        try:
            rvcon.sendEvent("ayon_load_container", payload)
        # rvcon.sendEvent("ayon_open_loader", "")
        # rvcon.sendEvent("key-down--l", "")
        except Exception as err:
            raise Exception(f"Failed to send event to RV: {err}")
        finally:
            rvcon.disconnect()
