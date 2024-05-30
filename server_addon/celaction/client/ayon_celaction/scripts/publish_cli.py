import os
import sys

import pyblish.api
import pyblish.util

import ayon_core.hosts.celaction
from ayon_core.lib import Logger
from ayon_core.tools.utils import host_tools
from ayon_core.pipeline import install_ayon_plugins


log = Logger.get_logger("celaction")

PUBLISH_HOST = "celaction"
HOST_DIR = os.path.dirname(os.path.abspath(ayon_core.hosts.celaction.__file__))
PLUGINS_DIR = os.path.join(HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")


def main():
    # Registers pype's Global pyblish plugins
    install_ayon_plugins()

    if os.path.exists(PUBLISH_PATH):
        log.info(f"Registering path: {PUBLISH_PATH}")
        pyblish.api.register_plugin_path(PUBLISH_PATH)

    pyblish.api.register_host(PUBLISH_HOST)
    pyblish.api.register_target("local")

    return host_tools.show_publish()


if __name__ == "__main__":
    result = main()
    sys.exit(not bool(result))
