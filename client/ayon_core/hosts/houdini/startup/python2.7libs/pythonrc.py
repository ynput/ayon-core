# -*- coding: utf-8 -*-
"""OpenPype startup script."""
from ayon_core.pipeline import install_host
from ayon_core.hosts.houdini.api import HoudiniHost
from ayon_core import AYON_SERVER_ENABLED


def main():
    print("Installing {} ...".format(
        "AYON" if AYON_SERVER_ENABLED else "OpenPype"))
    install_host(HoudiniHost())


main()
