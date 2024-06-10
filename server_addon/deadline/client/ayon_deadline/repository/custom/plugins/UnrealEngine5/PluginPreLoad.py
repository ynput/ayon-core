#!/usr/bin/env python3
#  Copyright Epic Games, Inc. All Rights Reserved

import sys
from pathlib import Path


def __main__():
    # Add the location of the plugin package to the system path so the plugin
    # can import supplemental modules if it needs to
    plugin_path = Path(__file__)
    if plugin_path.parent not in sys.path:
        sys.path.append(plugin_path.parent.as_posix())
