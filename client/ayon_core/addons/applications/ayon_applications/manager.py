import os
import sys
import copy
import json
import tempfile
import platform
import inspect
import subprocess

import six

from ayon_core import AYON_CORE_ROOT
from ayon_core.settings import get_studio_settings
from ayon_core.lib import (
    Logger,
    modules_from_path,
    classes_from_module,
    get_linux_launcher_args,
)
from ayon_core.addon import AddonsManager

from .constants import DEFAULT_ENV_SUBGROUP
from .exceptions import (
    ApplicationNotFound,
    ApplicationExecutableNotFound,
)
from .hooks import PostLaunchHook, PreLaunchHook
from .defs import EnvironmentToolGroup, ApplicationGroup, LaunchTypes


class ApplicationManager:
    """Load applications and tools and store them by their full name.

    Args:
        studio_settings (dict): Preloaded studio settings. When passed manager
            will always use these values. Gives ability to create manager
            using different settings.
    """

    def __init__(self, studio_settings=None):
        self.log = Logger.get_logger(self.__class__.__name__)

        self.app_groups = {}
        self.applications = {}
        self.tool_groups = {}
        self.tools = {}

        self._studio_settings = studio_settings

        self.refresh()

    def set_studio_settings(self, studio_settings):
        """Ability to change init system settings.

        This will trigger refresh of manager.
        """
        self._studio_settings = studio_settings

        self.refresh()

    def refresh(self):
        """Refresh applications from settings."""
        self.app_groups.clear()
        self.applications.clear()
        self.tool_groups.clear()
        self.tools.clear()

        if self._studio_settings is not None:
            settings = copy.deepcopy(self._studio_settings)
        else:
            settings = get_studio_settings(
                clear_metadata=False, exclude_locals=False
            )

        applications_addon_settings = settings["applications"]

        # Prepare known applications
        app_defs = applications_addon_settings["applications"]
        additional_apps = app_defs.pop("additional_apps")
        for additional_app in additional_apps:
            app_name = additional_app.pop("name")
            if app_name in app_defs:
                self.log.warning((
                    "Additional application '{}' is already"
                    " in built-in applications."
                ).format(app_name))
            app_defs[app_name] = additional_app

        for group_name, variant_defs in app_defs.items():
            group = ApplicationGroup(group_name, variant_defs, self)
            self.app_groups[group_name] = group
            for app in group:
                self.applications[app.full_name] = app

        tools_definitions = applications_addon_settings["tool_groups"]
        for tool_group_data in tools_definitions:
            group = EnvironmentToolGroup(tool_group_data, self)
            self.tool_groups[group.name] = group
            for tool in group:
                self.tools[tool.full_name] = tool

    def find_latest_available_variant_for_group(self, group_name):
        group = self.app_groups.get(group_name)
        if group is None or not group.enabled:
            return None

        output = None
        for _, variant in reversed(sorted(group.variants.items())):
            executable = variant.find_executable()
            if executable:
                output = variant
                break
        return output

    def create_launch_context(self, app_name, **data):
        """Prepare launch context for application.

        Args:
            app_name (str): Name of application that should be launched.
            **data (Any): Any additional data. Data may be used during

        Returns:
            ApplicationLaunchContext: Launch context for application.

        Raises:
            ApplicationNotFound: Application was not found by entered name.
        """

        app = self.applications.get(app_name)
        if not app:
            raise ApplicationNotFound(app_name)

        executable = app.find_executable()

        return ApplicationLaunchContext(
            app, executable, **data
        )

    def launch_with_context(self, launch_context):
        """Launch application using existing launch context.

        Args:
            launch_context (ApplicationLaunchContext): Prepared launch
                context.
        """

        if not launch_context.executable:
            raise ApplicationExecutableNotFound(launch_context.application)
        return launch_context.launch()

    def launch(self, app_name, **data):
        """Launch procedure.

        For host application it's expected to contain "project_name",
        "folder_path" and "task_name".

        Args:
            app_name (str): Name of application that should be launched.
            **data (dict): Any additional data. Data may be used during
                preparation to store objects usable in multiple places.

        Raises:
            ApplicationNotFound: Application was not found by entered
                argument `app_name`.
            ApplicationExecutableNotFound: Executables in application definition
                were not found on this machine.
            ApplicationLaunchFailed: Something important for application launch
                failed. Exception should contain explanation message,
                traceback should not be needed.
        """

        context = self.create_launch_context(app_name, **data)
        return self.launch_with_context(context)


class ApplicationLaunchContext:
    """Context of launching application.

    Main purpose of context is to prepare launch arguments and keyword
    arguments for new process. Most important part of keyword arguments
    preparations are environment variables.

    During the whole process is possible to use `data` attribute to store
    object usable in multiple places.

    Launch arguments are strings in list. It is possible to "chain" argument
    when order of them matters. That is possible to do with adding list where
    order is right and should not change.
    NOTE: This is recommendation, not requirement.
    e.g.: `["nuke.exe", "--NukeX"]` -> In this case any part of process may
    insert argument between `nuke.exe` and `--NukeX`. To keep them together
    it is better to wrap them in another list: `[["nuke.exe", "--NukeX"]]`.

    Notes:
        It is possible to use launch context only to prepare environment
            variables. In that case `executable` may be None and can be used
            'run_prelaunch_hooks' method to run prelaunch hooks which prepare
            them.

    Args:
        application (Application): Application definition.
        executable (ApplicationExecutable): Object with path to executable.
        env_group (Optional[str]): Environment variable group. If not set
            'DEFAULT_ENV_SUBGROUP' is used.
        launch_type (Optional[str]): Launch type. If not set 'local' is used.
        **data (dict): Any additional data. Data may be used during
            preparation to store objects usable in multiple places.
    """

    def __init__(
        self,
        application,
        executable,
        env_group=None,
        launch_type=None,
        **data
    ):
        # Application object
        self.application = application

        self.addons_manager = AddonsManager()

        # Logger
        logger_name = "{}-{}".format(self.__class__.__name__,
                                     self.application.full_name)
        self.log = Logger.get_logger(logger_name)

        self.executable = executable

        if launch_type is None:
            launch_type = LaunchTypes.local
        self.launch_type = launch_type

        if env_group is None:
            env_group = DEFAULT_ENV_SUBGROUP

        self.env_group = env_group

        self.data = dict(data)

        launch_args = []
        if executable is not None:
            launch_args = executable.as_args()
        # subprocess.Popen launch arguments (first argument in constructor)
        self.launch_args = launch_args
        self.launch_args.extend(application.arguments)
        if self.data.get("app_args"):
            self.launch_args.extend(self.data.pop("app_args"))

        # Handle launch environemtns
        src_env = self.data.pop("env", None)
        if src_env is not None and not isinstance(src_env, dict):
            self.log.warning((
                "Passed `env` kwarg has invalid type: {}. Expected: `dict`."
                " Using `os.environ` instead."
            ).format(str(type(src_env))))
            src_env = None

        if src_env is None:
            src_env = os.environ

        ignored_env = {"QT_API", }
        env = {
            key: str(value)
            for key, value in src_env.items()
            if key not in ignored_env
        }
        # subprocess.Popen keyword arguments
        self.kwargs = {"env": env}

        if platform.system().lower() == "windows":
            # Detach new process from currently running process on Windows
            flags = (
                subprocess.CREATE_NEW_PROCESS_GROUP
                | subprocess.DETACHED_PROCESS
            )
            self.kwargs["creationflags"] = flags

        if not sys.stdout:
            self.kwargs["stdout"] = subprocess.DEVNULL
            self.kwargs["stderr"] = subprocess.DEVNULL

        self.prelaunch_hooks = None
        self.postlaunch_hooks = None

        self.process = None
        self._prelaunch_hooks_executed = False

    @property
    def env(self):
        if (
            "env" not in self.kwargs
            or self.kwargs["env"] is None
        ):
            self.kwargs["env"] = {}
        return self.kwargs["env"]

    @env.setter
    def env(self, value):
        if not isinstance(value, dict):
            raise ValueError(
                "'env' attribute expect 'dict' object. Got: {}".format(
                    str(type(value))
                )
            )
        self.kwargs["env"] = value

    @property
    def modules_manager(self):
        """
        Deprecated:
            Use 'addons_manager' instead.

        """
        return self.addons_manager

    def _collect_addons_launch_hook_paths(self):
        """Helper to collect application launch hooks from addons.

        Module have to have implemented 'get_launch_hook_paths' method which
        can expect application as argument or nothing.

        Returns:
            List[str]: Paths to launch hook directories.
        """

        expected_types = (list, tuple, set)

        output = []
        for module in self.addons_manager.get_enabled_addons():
            # Skip module if does not have implemented 'get_launch_hook_paths'
            func = getattr(module, "get_launch_hook_paths", None)
            if func is None:
                continue

            func = module.get_launch_hook_paths
            if hasattr(inspect, "signature"):
                sig = inspect.signature(func)
                expect_args = len(sig.parameters) > 0
            else:
                expect_args = len(inspect.getargspec(func)[0]) > 0

            # Pass application argument if method expect it.
            try:
                if expect_args:
                    hook_paths = func(self.application)
                else:
                    hook_paths = func()
            except Exception:
                self.log.warning(
                    "Failed to call 'get_launch_hook_paths'",
                    exc_info=True
                )
                continue

            if not hook_paths:
                continue

            # Convert string to list
            if isinstance(hook_paths, six.string_types):
                hook_paths = [hook_paths]

            # Skip invalid types
            if not isinstance(hook_paths, expected_types):
                self.log.warning((
                    "Result of `get_launch_hook_paths`"
                    " has invalid type {}. Expected {}"
                ).format(type(hook_paths), expected_types))
                continue

            output.extend(hook_paths)
        return output

    def paths_to_launch_hooks(self):
        """Directory paths where to look for launch hooks."""
        # This method has potential to be part of application manager (maybe).
        paths = []

        # TODO load additional studio paths from settings
        global_hooks_dir = os.path.join(AYON_CORE_ROOT, "hooks")

        hooks_dirs = [
            global_hooks_dir
        ]
        if self.host_name:
            # If host requires launch hooks and is module then launch hooks
            #   should be collected using 'collect_launch_hook_paths'
            #   - module have to implement 'get_launch_hook_paths'
            host_module = self.addons_manager.get_host_addon(self.host_name)
            if not host_module:
                hooks_dirs.append(os.path.join(
                    AYON_CORE_ROOT, "hosts", self.host_name, "hooks"
                ))

        for path in hooks_dirs:
            if (
                os.path.exists(path)
                and os.path.isdir(path)
                and path not in paths
            ):
                paths.append(path)

        # Load modules paths
        paths.extend(self._collect_addons_launch_hook_paths())

        return paths

    def discover_launch_hooks(self, force=False):
        """Load and prepare launch hooks."""
        if (
            self.prelaunch_hooks is not None
            or self.postlaunch_hooks is not None
        ):
            if not force:
                self.log.info("Launch hooks were already discovered.")
                return

            self.prelaunch_hooks.clear()
            self.postlaunch_hooks.clear()

        self.log.debug("Discovery of launch hooks started.")

        paths = self.paths_to_launch_hooks()
        self.log.debug("Paths searched for launch hooks:\n{}".format(
            "\n".join("- {}".format(path) for path in paths)
        ))

        all_classes = {
            "pre": [],
            "post": []
        }
        for path in paths:
            if not os.path.exists(path):
                self.log.info(
                    "Path to launch hooks does not exist: \"{}\"".format(path)
                )
                continue

            modules, _crashed = modules_from_path(path)
            for _filepath, module in modules:
                all_classes["pre"].extend(
                    classes_from_module(PreLaunchHook, module)
                )
                all_classes["post"].extend(
                    classes_from_module(PostLaunchHook, module)
                )

        for launch_type, classes in all_classes.items():
            hooks_with_order = []
            hooks_without_order = []
            for klass in classes:
                try:
                    hook = klass(self)
                    if not hook.is_valid:
                        self.log.debug(
                            "Skipped hook invalid for current launch context: "
                            "{}".format(klass.__name__)
                        )
                        continue

                    if inspect.isabstract(hook):
                        self.log.debug("Skipped abstract hook: {}".format(
                            klass.__name__
                        ))
                        continue

                    # Separate hooks by pre/post class
                    if hook.order is None:
                        hooks_without_order.append(hook)
                    else:
                        hooks_with_order.append(hook)

                except Exception:
                    self.log.warning(
                        "Initialization of hook failed: "
                        "{}".format(klass.__name__),
                        exc_info=True
                    )

            # Sort hooks with order by order
            ordered_hooks = list(sorted(
                hooks_with_order, key=lambda obj: obj.order
            ))
            # Extend ordered hooks with hooks without defined order
            ordered_hooks.extend(hooks_without_order)

            if launch_type == "pre":
                self.prelaunch_hooks = ordered_hooks
            else:
                self.postlaunch_hooks = ordered_hooks

        self.log.debug("Found {} prelaunch and {} postlaunch hooks.".format(
            len(self.prelaunch_hooks), len(self.postlaunch_hooks)
        ))

    @property
    def app_name(self):
        return self.application.name

    @property
    def host_name(self):
        return self.application.host_name

    @property
    def app_group(self):
        return self.application.group

    @property
    def manager(self):
        return self.application.manager

    def _run_process(self):
        # Windows and MacOS have easier process start
        low_platform = platform.system().lower()
        if low_platform in ("windows", "darwin"):
            return subprocess.Popen(self.launch_args, **self.kwargs)

        # Linux uses mid process
        # - it is possible that the mid process executable is not
        #   available for this version of AYON in that case use standard
        #   launch
        launch_args = get_linux_launcher_args()
        if launch_args is None:
            return subprocess.Popen(self.launch_args, **self.kwargs)

        # Prepare data that will be passed to midprocess
        # - store arguments to a json and pass path to json as last argument
        # - pass environments to set
        app_env = self.kwargs.pop("env", {})
        json_data = {
            "args": self.launch_args,
            "env": app_env
        }
        if app_env:
            # Filter environments of subprocess
            self.kwargs["env"] = {
                key: value
                for key, value in os.environ.items()
                if key in app_env
            }

        # Create temp file
        json_temp = tempfile.NamedTemporaryFile(
            mode="w", prefix="op_app_args", suffix=".json", delete=False
        )
        json_temp.close()
        json_temp_filpath = json_temp.name
        with open(json_temp_filpath, "w") as stream:
            json.dump(json_data, stream)

        launch_args.append(json_temp_filpath)

        # Create mid-process which will launch application
        process = subprocess.Popen(launch_args, **self.kwargs)
        # Wait until the process finishes
        #   - This is important! The process would stay in "open" state.
        process.wait()
        # Remove the temp file
        os.remove(json_temp_filpath)
        # Return process which is already terminated
        return process

    def run_prelaunch_hooks(self):
        """Run prelaunch hooks.

        This method will be executed only once, any future calls will skip
            the processing.
        """

        if self._prelaunch_hooks_executed:
            self.log.warning("Prelaunch hooks were already executed.")
            return
        # Discover launch hooks
        self.discover_launch_hooks()

        # Execute prelaunch hooks
        for prelaunch_hook in self.prelaunch_hooks:
            self.log.debug("Executing prelaunch hook: {}".format(
                str(prelaunch_hook.__class__.__name__)
            ))
            prelaunch_hook.execute()
        self._prelaunch_hooks_executed = True

    def launch(self):
        """Collect data for new process and then create it.

        This method must not be executed more than once.

        Returns:
            subprocess.Popen: Created process as Popen object.
        """
        if self.process is not None:
            self.log.warning("Application was already launched.")
            return

        if not self._prelaunch_hooks_executed:
            self.run_prelaunch_hooks()

        self.log.debug("All prelaunch hook executed. Starting new process.")

        # Prepare subprocess args
        args_len_str = ""
        if isinstance(self.launch_args, str):
            args = self.launch_args
        else:
            args = self.clear_launch_args(self.launch_args)
            args_len_str = " ({})".format(len(args))
        self.log.info(
            "Launching \"{}\" with args{}: {}".format(
                self.application.full_name, args_len_str, args
            )
        )
        self.launch_args = args

        # Run process
        self.process = self._run_process()

        # Process post launch hooks
        for postlaunch_hook in self.postlaunch_hooks:
            self.log.debug("Executing postlaunch hook: {}".format(
                str(postlaunch_hook.__class__.__name__)
            ))

            # TODO how to handle errors?
            # - store to variable to let them accessible?
            try:
                postlaunch_hook.execute()

            except Exception:
                self.log.warning(
                    "After launch procedures were not successful.",
                    exc_info=True
                )

        self.log.debug("Launch of {} finished.".format(
            self.application.full_name
        ))

        return self.process

    @staticmethod
    def clear_launch_args(args):
        """Collect launch arguments to final order.

        Launch argument should be list that may contain another lists this
        function will upack inner lists and keep ordering.

        ```
        # source
        [ [ arg1, [ arg2, arg3 ] ], arg4, [arg5, arg6]]
        # result
        [ arg1, arg2, arg3, arg4, arg5, arg6]

        Args:
            args (list): Source arguments in list may contain inner lists.

        Return:
            list: Unpacked arguments.
        """
        if isinstance(args, str):
            return args
        all_cleared = False
        while not all_cleared:
            all_cleared = True
            new_args = []
            for arg in args:
                if isinstance(arg, (list, tuple, set)):
                    all_cleared = False
                    for _arg in arg:
                        new_args.append(_arg)
                else:
                    new_args.append(arg)
            args = new_args

        return args

