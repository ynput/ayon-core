# -*- coding: utf-8 -*-
"""OpenPype startup script."""
from ayon_core.pipeline import install_host
from ayon_houdini.api import HoudiniHost


def main():
    print("Installing AYON ...")
    install_host(HoudiniHost())


main()
