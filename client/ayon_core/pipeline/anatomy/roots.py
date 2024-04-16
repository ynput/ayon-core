import os
import platform
import numbers

from ayon_core.lib import Logger
from ayon_core.lib.path_templates import FormatObject


class RootItem(FormatObject):
    """Represents one item or roots.

    Holds raw data of root item specification. Raw data contain value
    for each platform, but current platform value is used when object
    is used for formatting of template.

    Args:
        parent (AnatomyRoots): Parent object.
        root_raw_data (dict): Dictionary containing root values by platform
            names. ["windows", "linux" and "darwin"]
        name (str): Root name which is representing. Used with
            multi root setup otherwise None value is expected.
    """
    def __init__(self, parent, root_raw_data, name):
        super(RootItem, self).__init__()
        self._log = None
        lowered_platform_keys = {}
        for key, value in root_raw_data.items():
            lowered_platform_keys[key.lower()] = value
        self.raw_data = lowered_platform_keys
        self.cleaned_data = self._clean_roots(lowered_platform_keys)
        self.name = name
        self.parent = parent

        self.available_platforms = set(lowered_platform_keys.keys())
        self.value = lowered_platform_keys.get(platform.system().lower())
        self.clean_value = self._clean_root(self.value)

    def __format__(self, *args, **kwargs):
        return self.value.__format__(*args, **kwargs)

    def __str__(self):
        return str(self.value)

    def __repr__(self):
        return self.__str__()

    def __getitem__(self, key):
        if isinstance(key, numbers.Number):
            return self.value[key]

        additional_info = ""
        if self.parent and self.parent.project_name:
            additional_info += " for project \"{}\"".format(
                self.parent.project_name
            )

        raise KeyError(
            "Root key \"{}\" is missing{}.".format(
                key, additional_info
            )
        )

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def full_key(self):
        """Full key value for dictionary formatting in template.

        Returns:
            str: Return full replacement key for formatting. This helps when
                multiple roots are set. In that case e.g. `"root[work]"` is
                returned.

        """
        return "root[{}]".format(self.name)

    @staticmethod
    def _clean_path(path):
        """Just replace backslashes with forward slashes.

        Args:
            path (str): Path which should be cleaned.

        Returns:
            str: Cleaned path with forward slashes.

        """
        return str(path).replace("\\", "/")

    def _clean_root(self, root):
        """Clean root value.

        Args:
            root (str): Root value which should be cleaned.

        Returns:
            str: Cleaned root value.

        """
        return self._clean_path(root).rstrip("/")

    def _clean_roots(self, raw_data):
        """Clean all values of raw root item values."""
        cleaned = {}
        for key, value in raw_data.items():
            cleaned[key] = self._clean_root(value)
        return cleaned

    def path_remapper(self, path, dst_platform=None, src_platform=None):
        """Remap path for specific platform.

        Args:
            path (str): Source path which need to be remapped.
            dst_platform (str, optional): Specify destination platform
                for which remapping should happen.
            src_platform (str, optional): Specify source platform. This is
                recommended to not use and keep unset until you really want
                to use specific platform.

        Returns:
            Union[str, None]: When path does not contain known root then
                None is returned else returns remapped path with
                "{root[<name>]}".

        """
        cleaned_path = self._clean_path(path)
        if dst_platform:
            dst_root_clean = self.cleaned_data.get(dst_platform)
            if not dst_root_clean:
                self.log.warning(
                    "Root \"{}\" miss platform \"{}\" definition.".format(
                        self.full_key, dst_platform
                    )
                )
                return None

            if cleaned_path.startswith(dst_root_clean):
                return cleaned_path

        if src_platform:
            src_root_clean = self.cleaned_data.get(src_platform)
            if src_root_clean is None:
                self.log.warning(
                    "Root \"{}\" miss platform \"{}\" definition.".format(
                        self.full_key, src_platform
                    )
                )
                return None

            if not cleaned_path.startswith(src_root_clean):
                return None

            subpath = cleaned_path[len(src_root_clean):]
            if dst_platform:
                # `dst_root_clean` is used from upper condition
                return dst_root_clean + subpath
            return self.clean_value + subpath

        result, template = self.find_root_template_from_path(path)
        if not result:
            return None

        if dst_platform:
            fill_data = {self.name: dst_root_clean}
        else:
            fill_data = {self.name: self.value}

        return template.format(**{"root": fill_data})

    def find_root_template_from_path(self, path):
        """Replaces known root value with formattable key in path.

        All platform values are checked for this replacement.

        Args:
            path (str): Path where root value should be found.

        Returns:
            tuple: Tuple contain 2 values: `success` (bool) and `path` (str).
                When success it True then path should contain replaced root
                value with formattable key.

        Example:
            When input path is::
                "C:/windows/path/root/projects/my_project/file.ext"

            And raw data of item looks like::
                {
                    "windows": "C:/windows/path/root",
                    "linux": "/mount/root"
                }

            Output will be::
                (True, "{root}/projects/my_project/file.ext")

            If any of raw data value wouldn't match path's root output is::
                (False, "C:/windows/path/root/projects/my_project/file.ext")
        """
        result = False
        output = str(path)

        mod_path = self._clean_path(path)
        for root_os, root_path in self.cleaned_data.items():
            # Skip empty paths
            if not root_path:
                continue

            _mod_path = mod_path  # reset to original cleaned value
            if root_os == "windows":
                root_path = root_path.lower()
                _mod_path = _mod_path.lower()

            if _mod_path.startswith(root_path):
                result = True
                replacement = "{" + self.full_key + "}"
                output = replacement + mod_path[len(root_path):]
                break

        return (result, output)


class AnatomyRoots:
    """Object which should be used for formatting "root" key in templates.

    Args:
        anatomy (Anatomy): Anatomy object created for a specific project.
    """

    env_prefix = "AYON_PROJECT_ROOT"

    def __init__(self, anatomy):
        self._log = None
        self._anatomy = anatomy
        self._loaded_project = None
        self._roots = None

    def __format__(self, *args, **kwargs):
        return self.roots.__format__(*args, **kwargs)

    def __getitem__(self, key):
        return self.roots[key]

    @property
    def log(self):
        if self._log is None:
            self._log = Logger.get_logger(self.__class__.__name__)
        return self._log

    @property
    def anatomy(self):
        """Parent Anatomy object.

        Returns:
            Anatomy: Parent anatomy object.

        """
        return self._anatomy

    def reset(self):
        """Reset current roots value."""
        self._roots = None

    def path_remapper(
        self, path, dst_platform=None, src_platform=None, roots=None
    ):
        """Remap path for specific platform.

        Args:
            path (str): Source path which need to be remapped.
            dst_platform (Optional[str]): Specify destination platform
                for which remapping should happen.
            src_platform (Optional[str]): Specify source platform. This is
                recommended to not use and keep unset until you really want
                to use specific platform.
            roots (Optional[Union[dict, RootItem])): It is possible to remap
                path with different roots then instance where method was
                called has.

        Returns:
            Union[str, None]: When path does not contain known root then
                None is returned else returns remapped path with "{root}"
                or "{root[<name>]}".

        """
        if roots is None:
            roots = self.roots

        if roots is None:
            raise ValueError("Roots are not set. Can't find path.")

        if "{root" in path:
            path = path.format(**{"root": roots})
            # If `dst_platform` is not specified then return else continue.
            if not dst_platform:
                return path

        if isinstance(roots, RootItem):
            return roots.path_remapper(path, dst_platform, src_platform)

        for _root in roots.values():
            result = self.path_remapper(
                path, dst_platform, src_platform, _root
            )
            if result is not None:
                return result

    def find_root_template_from_path(self, path, roots=None):
        """Find root value in entered path and replace it with formatting key.

        Args:
            path (str): Source path where root will be searched.
            roots (Optional[Union[AnatomyRoots, dict]): It is possible to use
                different roots than instance where method was triggered has.

        Returns:
            tuple: Output contains tuple with bool representing success as
                first value and path with or without replaced root with
                formatting key as second value.

        Raises:
            ValueError: When roots are not entered and can't be loaded.
        """
        if roots is None:
            self.log.debug(
                "Looking for matching root in path \"{}\".".format(path)
            )
            roots = self.roots

        if roots is None:
            raise ValueError("Roots are not set. Can't find path.")

        if isinstance(roots, RootItem):
            return roots.find_root_template_from_path(path)

        for root_name, _root in roots.items():
            success, result = self.find_root_template_from_path(path, _root)
            if success:
                self.log.debug(
                    "Found match in root \"{}\".".format(root_name)
                )
                return success, result

        self.log.warning("No matching root was found in current setting.")
        return (False, path)

    def set_root_environments(self):
        """Set root environments for current project."""
        for key, value in self.root_environments().items():
            os.environ[key] = value

    def root_environments(self):
        """Use root keys to create unique keys for environment variables.

        Concatenates prefix "AYON_PROJECT_ROOT_" with root keys to create
        unique keys.

        Returns:
            dict: Result is `{(str): (str)}` dicitonary where key represents
                unique key concatenated by keys and value is root value of
                current platform root.

        Example:
            With raw root values::
                "work": {
                    "windows": "P:/projects/work",
                    "linux": "/mnt/share/projects/work",
                    "darwin": "/darwin/path/work"
                },
                "publish": {
                    "windows": "P:/projects/publish",
                    "linux": "/mnt/share/projects/publish",
                    "darwin": "/darwin/path/publish"
                }

            Result on windows platform::
                {
                    "AYON_PROJECT_ROOT_WORK": "P:/projects/work",
                    "AYON_PROJECT_ROOT_PUBLISH": "P:/projects/publish"
                }

        """
        return self._root_environments()

    def all_root_paths(self, roots=None):
        """Return all paths for all roots of all platforms."""
        if roots is None:
            roots = self.roots

        output = []
        if isinstance(roots, RootItem):
            for value in roots.raw_data.values():
                output.append(value)
            return output

        for _roots in roots.values():
            output.extend(self.all_root_paths(_roots))
        return output

    def _root_environments(self, keys=None, roots=None):
        if not keys:
            keys = []
        if roots is None:
            roots = self.roots

        if isinstance(roots, RootItem):
            key_items = [self.env_prefix]
            for _key in keys:
                key_items.append(_key.upper())

            key = "_".join(key_items)
            # Make sure key and value does not contain unicode
            #   - can happen in Python 2 hosts
            return {str(key): str(roots.value)}

        output = {}
        for _key, _value in roots.items():
            _keys = list(keys)
            _keys.append(_key)
            output.update(self._root_environments(_keys, _value))
        return output

    def root_environmets_fill_data(self, template=None):
        """Environment variable values in dictionary for rootless path.

        Args:
            template (str): Template for environment variable key fill.
                By default is set to `"${}"`.
        """
        if template is None:
            template = "${}"
        return self._root_environmets_fill_data(template)

    def _root_environmets_fill_data(self, template, keys=None, roots=None):
        if keys is None and roots is None:
            return {
                "root": self._root_environmets_fill_data(
                    template, [], self.roots
                )
            }

        if isinstance(roots, RootItem):
            key_items = [AnatomyRoots.env_prefix]
            for _key in keys:
                key_items.append(_key.upper())
            key = "_".join(key_items)
            return template.format(key)

        output = {}
        for key, value in roots.items():
            _keys = list(keys)
            _keys.append(key)
            output[key] = self._root_environmets_fill_data(
                template, _keys, value
            )
        return output

    @property
    def project_name(self):
        """Current project name which will be used for loading root values.

        Returns:
            str: Project name.
        """
        return self._anatomy.project_name

    @property
    def roots(self):
        """Property for filling "root" key in templates.

        This property returns roots for current project or default root values.

        Warning:
            Default roots value may cause issues when project use different
            roots settings. That may happen when project use multiroot
            templates but default roots miss their keys.

        """
        if self.project_name != self._loaded_project:
            self._roots = None

        if self._roots is None:
            self._roots = self._discover()
            self._loaded_project = self.project_name
        return self._roots

    def _discover(self):
        """ Loads current project's roots or default.

        Default roots are loaded if project override's does not contain roots.

        Returns:
            `RootItem` or `dict` with multiple `RootItem`s when multiroot
            setting is used.
        """

        return self._parse_dict(self._anatomy["roots"], self)

    @staticmethod
    def _parse_dict(data, parent):
        """Parse roots raw data into RootItem or dictionary with RootItems.

        Converting raw roots data to `RootItem` helps to handle platform keys.
        This method is recursive to be able handle multiroot setup and
        is static to be able to load default roots without creating new object.

        Args:
            data (dict): Should contain raw roots data to be parsed.
            parent (AnatomyRoots): Parent object set as parent
                for ``RootItem``.

        Returns:
            dict[str, RootItem]: Root items by name.

        """
        output = {}
        for root_name, root_values in data.items():
            output[root_name] = RootItem(
                parent, root_values, root_name
            )
        return output
