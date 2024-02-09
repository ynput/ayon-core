# Test for backward compatibility of restructure of lib.py into lib library
# Contains simple imports that should still work


def test_backward_compatibility(printer):
    printer("Test if imports still work")
    try:
        from ayon_core.lib import execute_hook
        from ayon_core.lib import PypeHook

        from ayon_core.lib import ApplicationLaunchFailed

        from ayon_core.lib import get_ffmpeg_tool_path
        from ayon_core.lib import get_last_version_from_path
        from ayon_core.lib import get_paths_from_environ
        from ayon_core.lib import get_version_from_path
        from ayon_core.lib import version_up

        from ayon_core.lib import get_ffprobe_streams

        from ayon_core.lib import source_hash
        from ayon_core.lib import run_subprocess

    except ImportError as e:
        raise
