import os
import sys

from ayon_core.pipeline import install_host
from ayon_core.lib import Logger

log = Logger.get_logger(__name__)


def main(env):
    from ayon_core.hosts.resolve.api import ResolveHost, launch_ayon_menu

    # activate resolve from openpype
    host = ResolveHost()
    install_host(host)

    launch_ayon_menu()


if __name__ == "__main__":
    result = main(os.environ)
    sys.exit(not bool(result))
