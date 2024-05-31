#!/usr/bin/env python
import os
import sys

from ayon_core.pipeline import install_host


def main(env):
    from ayon_resolve.utils import setup
    import ayon_resolve.api as bmdvr
    # Registers openpype's Global pyblish plugins
    install_host(bmdvr)
    setup(env)


if __name__ == "__main__":
    result = main(os.environ)
    sys.exit(not bool(result))
