import os
import platform
import json
import copy

from ayon_core.lib import find_executable


class LaunchTypes:
    """Launch types are filters for pre/post-launch hooks.

    Please use these variables in case they'll change values.
    """

    # Local launch - application is launched on local machine
    local = "local"
    # Farm render job - application is on farm
    farm_render = "farm-render"
    # Farm publish job - integration post-render job
    farm_publish = "farm-publish"
    # Remote launch - application is launched on remote machine from which
    #     can be started publishing
    remote = "remote"
    # Automated launch - application is launched with automated publishing
    automated = "automated"


class ApplicationExecutable:
    """Representation of executable loaded from settings."""

    def __init__(self, executable):
        # Try to format executable with environments
        try:
            executable = executable.format(**os.environ)
        except Exception:
            pass

        # On MacOS check if exists path to executable when ends with `.app`
        # - it is common that path will lead to "/Applications/Blender" but
        #   real path is "/Applications/Blender.app"
        if platform.system().lower() == "darwin":
            executable = self.macos_executable_prep(executable)

        self.executable_path = executable

    def __str__(self):
        return self.executable_path

    def __repr__(self):
        return "<{}> {}".format(self.__class__.__name__, self.executable_path)

    @staticmethod
    def macos_executable_prep(executable):
        """Try to find full path to executable file.

        Real executable is stored in '*.app/Contents/MacOS/<executable>'.

        Having path to '*.app' gives ability to read it's plist info and
        use "CFBundleExecutable" key from plist to know what is "executable."

        Plist is stored in '*.app/Contents/Info.plist'.

        This is because some '*.app' directories don't have same permissions
        as real executable.
        """
        # Try to find if there is `.app` file
        if not os.path.exists(executable):
            _executable = executable + ".app"
            if os.path.exists(_executable):
                executable = _executable

        # Try to find real executable if executable has `Contents` subfolder
        contents_dir = os.path.join(executable, "Contents")
        if os.path.exists(contents_dir):
            executable_filename = None
            # Load plist file and check for bundle executable
            plist_filepath = os.path.join(contents_dir, "Info.plist")
            if os.path.exists(plist_filepath):
                import plistlib

                if hasattr(plistlib, "load"):
                    with open(plist_filepath, "rb") as stream:
                        parsed_plist = plistlib.load(stream)
                else:
                    parsed_plist = plistlib.readPlist(plist_filepath)
                executable_filename = parsed_plist.get("CFBundleExecutable")

            if executable_filename:
                executable = os.path.join(
                    contents_dir, "MacOS", executable_filename
                )

        return executable

    def as_args(self):
        return [self.executable_path]

    def _realpath(self):
        """Check if path is valid executable path."""
        # Check for executable in PATH
        result = find_executable(self.executable_path)
        if result is not None:
            return result

        # This is not 100% validation but it is better than remove ability to
        #   launch .bat, .sh or extentionless files
        if os.path.exists(self.executable_path):
            return self.executable_path
        return None

    def exists(self):
        if not self.executable_path:
            return False
        return bool(self._realpath())


class UndefinedApplicationExecutable(ApplicationExecutable):
    """Some applications do not require executable path from settings.

    In that case this class is used to "fake" existing executable.
    """
    def __init__(self):
        pass

    def __str__(self):
        return self.__class__.__name__

    def __repr__(self):
        return "<{}>".format(self.__class__.__name__)

    def as_args(self):
        return []

    def exists(self):
        return True


class ApplicationGroup:
    """Hold information about application group.

    Application group wraps different versions(variants) of application.
    e.g. "maya" is group and "maya_2020" is variant.

    Group hold `host_name` which is implementation name used in AYON. Also
    holds `enabled` if whole app group is enabled or `icon` for application
    icon path in resources.

    Group has also `environment` which hold same environments for all variants.

    Args:
        name (str): Groups' name.
        data (dict): Group defying data loaded from settings.
        manager (ApplicationManager): Manager that created the group.
    """

    def __init__(self, name, data, manager):
        self.name = name
        self.manager = manager
        self._data = data

        self.enabled = data["enabled"]
        self.label = data["label"] or None
        self.icon = data["icon"] or None
        env = {}
        try:
            env = json.loads(data["environment"])
        except Exception:
            pass
        self._environment = env

        host_name = data["host_name"] or None
        self.is_host = host_name is not None
        self.host_name = host_name

        settings_variants = data["variants"]
        variants = {}
        for variant_data in settings_variants:
            app_variant = Application(variant_data, self)
            variants[app_variant.name] = app_variant

        self.variants = variants

    def __repr__(self):
        return "<{}> - {}".format(self.__class__.__name__, self.name)

    def __iter__(self):
        for variant in self.variants.values():
            yield variant

    @property
    def environment(self):
        return copy.deepcopy(self._environment)


class Application:
    """Hold information about application.

    Object by itself does nothing special.

    Args:
        data (dict): Data for the version containing information about
            executables, variant label or if is enabled.
            Only required key is `executables`.
        group (ApplicationGroup): App group object that created the application
            and under which application belongs.

    """
    def __init__(self, data, group):
        self._data = data
        name = data["name"]
        label = data["label"] or name
        enabled = False
        if group.enabled:
            enabled = data.get("enabled", True)

        if group.label:
            full_label = " ".join((group.label, label))
        else:
            full_label = label
        env = {}
        try:
            env = json.loads(data["environment"])
        except Exception:
            pass

        arguments = data["arguments"]
        if isinstance(arguments, dict):
            arguments = arguments.get(platform.system().lower())

        if not arguments:
            arguments = []

        _executables = data["executables"].get(platform.system().lower(), [])
        executables = [
            ApplicationExecutable(executable)
            for executable in _executables
        ]

        self.group = group

        self.name = name
        self.label = label
        self.enabled = enabled
        self.use_python_2 = data.get("use_python_2", False)

        self.full_name = "/".join((group.name, name))
        self.full_label = full_label
        self.arguments = arguments
        self.executables = executables
        self._environment = env

    def __repr__(self):
        return "<{}> - {}".format(self.__class__.__name__, self.full_name)

    @property
    def environment(self):
        return copy.deepcopy(self._environment)

    @property
    def manager(self):
        return self.group.manager

    @property
    def host_name(self):
        return self.group.host_name

    @property
    def icon(self):
        return self.group.icon

    @property
    def is_host(self):
        return self.group.is_host

    def find_executable(self):
        """Try to find existing executable for application.

        Returns (str): Path to executable from `executables` or None if any
            exists.
        """
        for executable in self.executables:
            if executable.exists():
                return executable
        return None

    def launch(self, *args, **kwargs):
        """Launch the application.

        For this purpose is used manager's launch method to keep logic at one
        place.

        Arguments must match with manager's launch method. That's why *args
        **kwargs are used.

        Returns:
            subprocess.Popen: Return executed process as Popen object.
        """
        return self.manager.launch(self.full_name, *args, **kwargs)


class EnvironmentToolGroup:
    """Hold information about environment tool group.

    Environment tool group may hold different variants of same tool and set
    environments that are same for all of them.

    e.g. "mtoa" may have different versions but all environments except one
        are same.

    Args:
        data (dict): Group information with variants.
        manager (ApplicationManager): Manager that creates the group.
    """

    def __init__(self, data, manager):
        name = data["name"]
        label = data["label"]

        self.name = name
        self.label = label
        self._data = data
        self.manager = manager

        environment = {}
        try:
            environment = json.loads(data["environment"])
        except Exception:
            pass
        self._environment = environment

        variants = data.get("variants") or []
        variants_by_name = {}
        for variant_data in variants:
            tool = EnvironmentTool(variant_data, self)
            variants_by_name[tool.name] = tool
        self.variants = variants_by_name

    def __repr__(self):
        return "<{}> - {}".format(self.__class__.__name__, self.name)

    def __iter__(self):
        for variant in self.variants.values():
            yield variant

    @property
    def environment(self):
        return copy.deepcopy(self._environment)


class EnvironmentTool:
    """Hold information about application tool.

    Structure of tool information.

    Args:
        variant_data (dict): Variant data with environments and
            host and app variant filters.
        group (EnvironmentToolGroup): Name of group which wraps tool.
    """

    def __init__(self, variant_data, group):
        # Backwards compatibility 3.9.1 - 3.9.2
        # - 'variant_data' contained only environments but contain also host
        #   and application variant filters
        name = variant_data["name"]
        label = variant_data["label"]
        host_names = variant_data["host_names"]
        app_variants = variant_data["app_variants"]

        environment = {}
        try:
            environment = json.loads(variant_data["environment"])
        except Exception:
            pass

        self.host_names = host_names
        self.app_variants = app_variants
        self.name = name
        self.variant_label = label
        self.label = " ".join((group.label, label))
        self.group = group

        self._environment = environment
        self.full_name = "/".join((group.name, name))

    def __repr__(self):
        return "<{}> - {}".format(self.__class__.__name__, self.full_name)

    @property
    def environment(self):
        return copy.deepcopy(self._environment)

    def is_valid_for_app(self, app):
        """Is tool valid for application.

        Args:
            app (Application): Application for which are prepared environments.
        """
        if self.app_variants and app.full_name not in self.app_variants:
            return False

        if self.host_names and app.host_name not in self.host_names:
            return False
        return True
