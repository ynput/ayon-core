""""Pre launch hook to remove launcher paths from the system."""
import os

from ayon_applications import PreLaunchHook


class PreRemoveLauncherPaths(PreLaunchHook):
    """Remove launcher paths from the system.

    This hook is used to remove launcher paths from the system before launching
    an application. It is used to ensure that the application is launched with
    the correct environment variables. Especially for Windows, where
    paths in `PATH` are used to load DLLs. This is important to avoid
    conflicts with other applications that may have the same DLLs in their
    paths.
    """
    order = 1

    def execute(self) -> None:
        """Execute the hook."""
        # Remove launcher paths from the system
        ayon_root = os.path.normpath(os.environ["AYON_ROOT"])

        paths = [
            path
            for path in self.launch_context.env.get(
                "PATH", "").split(os.pathsep)
            if not os.path.normpath(path).startswith(ayon_root)
        ]
        self.launch_context.env["PATH"] = os.pathsep.join(paths)
