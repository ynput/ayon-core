import os
import re
import copy
import platform
import collections
import time

import ayon_api

from ayon_core.lib import Logger, get_local_site_id, StringTemplate
from ayon_core.addon import AddonsManager

from .exceptions import RootCombinationError, ProjectNotSet
from .roots import AnatomyRoots
from .templates import AnatomyTemplates

log = Logger.get_logger(__name__)


class BaseAnatomy(object):
    """Anatomy module helps to keep project settings.

    Wraps key project specifications, AnatomyTemplates and AnatomyRoots.
    """
    root_key_regex = re.compile(r"{(root?[^}]+)}")
    root_name_regex = re.compile(r"root\[([^]]+)\]")

    def __init__(self, project_entity, root_overrides=None):
        self._project_name = project_entity["name"]
        self._project_code = project_entity["code"]

        self._data = self._prepare_anatomy_data(
            project_entity, root_overrides
        )
        self._templates_obj = AnatomyTemplates(self)
        self._roots_obj = AnatomyRoots(self)

    # Anatomy used as dictionary
    # - implemented only getters returning copy
    def __getitem__(self, key):
        return copy.deepcopy(self._data[key])

    def get(self, key, default=None):
        if key not in self._data:
            return default
        return copy.deepcopy(self._data[key])

    def keys(self):
        return copy.deepcopy(self._data).keys()

    def values(self):
        return copy.deepcopy(self._data).values()

    def items(self):
        return copy.deepcopy(self._data).items()

    @property
    def project_name(self):
        """Project name for which is anatomy prepared.

        Returns:
            str: Project name.

        """
        return self._project_name

    @property
    def project_code(self):
        """Project name for which is anatomy prepared.

        Returns:
            str: Project code.

        """
        return self._project_code

    def _prepare_anatomy_data(self, project_entity, root_overrides):
        """Prepare anatomy data for further processing.

        Method added to replace `{task}` with `{task[name]}` in templates.
        """

        anatomy_data = self._project_entity_to_anatomy_data(project_entity)

        self._apply_local_settings_on_anatomy_data(
            anatomy_data,
            root_overrides
        )

        return anatomy_data

    @property
    def templates(self):
        """Wrap property `templates` of Anatomy's AnatomyTemplates instance."""
        return self._templates_obj.templates

    @property
    def templates_obj(self):
        """Return `AnatomyTemplates` object of current Anatomy instance."""
        return self._templates_obj

    def get_template_item(self, *args, **kwargs):
        """Get template item from category.

        Args:
            category_name (str): Category name.
            template_name (str): Template name.
            subkey (Optional[str]): Subkey name.
            default (Any): Default value.

        Returns:
            Any: Template item, subkey value as AnatomyStringTemplate or None.

        """
        return self._templates_obj.get_template_item(*args, **kwargs)

    def format(self, *args, **kwargs):
        """Wrap `format` method of Anatomy's `templates_obj`."""
        return self._templates_obj.format(*args, **kwargs)

    def format_all(self, *args, **kwargs):
        """Wrap `format_all` method of Anatomy's `templates_obj`.

        Deprecated:
            Use ``format`` method with ``strict=False`` instead.

        """
        return self._templates_obj.format_all(*args, **kwargs)

    @property
    def roots(self):
        """Wrap `roots` property of Anatomy's `roots_obj`."""
        return self._roots_obj.roots

    @property
    def roots_obj(self):
        """Roots wrapper object.

        Returns:
            AnatomyRoots: Roots wrapper.

        """
        return self._roots_obj

    def root_environments(self):
        """Return AYON_PROJECT_ROOT_* environments for current project."""
        return self._roots_obj.root_environments()

    def root_environmets_fill_data(self, template=None):
        """Environment variable values in dictionary for rootless path.

        Args:
            template (str): Template for environment variable key fill.
                By default is set to `"${}"`.
        """
        return self.roots_obj.root_environmets_fill_data(template)

    def find_root_template_from_path(self, *args, **kwargs):
        """Wrapper for AnatomyRoots `find_root_template_from_path`."""
        return self.roots_obj.find_root_template_from_path(*args, **kwargs)

    def path_remapper(self, *args, **kwargs):
        """Wrapper for AnatomyRoots `path_remapper`."""
        return self.roots_obj.path_remapper(*args, **kwargs)

    def all_root_paths(self):
        """Wrapper for AnatomyRoots `all_root_paths`."""
        return self.roots_obj.all_root_paths()

    def set_root_environments(self):
        """Set AYON_PROJECT_ROOT_* environments for current project."""
        self._roots_obj.set_root_environments()

    def root_names(self):
        """Return root names for current project."""
        return self.root_names_from_templates(self.templates)

    def _root_keys_from_templates(self, data):
        """Extract root key from templates in data.

        Args:
            data (dict): Data that may contain templates as string.

        Return:
            set: Set of all root names from templates as strings.

        Output example: `{"root[work]", "root[publish]"}`
        """

        output = set()
        keys_queue = collections.deque()
        keys_queue.append(data)
        while keys_queue:
            queue_data = keys_queue.popleft()
            if isinstance(queue_data, StringTemplate):
                queue_data = queue_data.template

            if isinstance(queue_data, dict):
                for value in queue_data.values():
                    keys_queue.append(value)

            elif isinstance(queue_data, str):
                for group in re.findall(self.root_key_regex, queue_data):
                    output.add(group)

        return output

    def root_value_for_template(self, template):
        """Returns value of root key from template."""
        if isinstance(template, StringTemplate):
            template = template.template
        root_templates = []
        for group in re.findall(self.root_key_regex, template):
            root_templates.append("{" + group + "}")

        if not root_templates:
            return None

        return root_templates[0].format(**{"root": self.roots})

    def root_names_from_templates(self, templates):
        """Extract root names form anatomy templates.

        Returns None if values in templates contain only "{root}".
        Empty list is returned if there is no "root" in templates.
        Else returns all root names from templates in list.

        RootCombinationError is raised when templates contain both root types,
        basic "{root}" and with root name specification "{root[work]}".

        Args:
            templates (dict): Anatomy templates where roots are not filled.

        Return:
            list/None: List of all root names from templates as strings when
            multiroot setup is used, otherwise None is returned.
        """
        roots = list(self._root_keys_from_templates(templates))
        # Return empty list if no roots found in templates
        if not roots:
            return roots

        # Raise exception when root keys have roots with and without root name.
        # Invalid output example: ["root", "root[project]", "root[render]"]
        if len(roots) > 1 and "root" in roots:
            raise RootCombinationError(roots)

        # Return None if "root" without root name in templates
        if len(roots) == 1 and roots[0] == "root":
            return None

        names = set()
        for root in roots:
            for group in re.findall(self.root_name_regex, root):
                names.add(group)
        return list(names)

    def fill_root(self, template_path):
        """Fill template path where is only "root" key unfilled.

        Args:
            template_path (str): Path with "root" key in.
                Example path: "{root}/projects/MyProject/Shot01/Lighting/..."

        Return:
            str: formatted path
        """
        # NOTE does not care if there are different keys than "root"
        return template_path.format(**{"root": self.roots})

    @classmethod
    def fill_root_with_path(cls, rootless_path, root_path):
        """Fill path without filled "root" key with passed path.

        This is helper to fill root with different directory path than anatomy
        has defined no matter if is single or multiroot.

        Output path is same as input path if `rootless_path` does not contain
        unfilled root key.

        Args:
            rootless_path (str): Path without filled "root" key. Example:
                "{root[work]}/MyProject/..."
            root_path (str): What should replace root key in `rootless_path`.

        Returns:
            str: Path with filled root.
        """
        output = str(rootless_path)
        for group in re.findall(cls.root_key_regex, rootless_path):
            replacement = "{" + group + "}"
            output = output.replace(replacement, root_path)

        return output

    def replace_root_with_env_key(self, filepath, template=None):
        """Replace root of path with environment key.

        # Example:
        ## Project with roots:
        ```
        {
            "nas": {
                "windows": P:/projects",
                ...
            }
            ...
        }
        ```

        ## Entered filepath
        "P:/projects/project/folder/task/animation_v001.ma"

        ## Entered template
        "<{}>"

        ## Output
        "<AYON_PROJECT_ROOT_NAS>/project/folder/task/animation_v001.ma"

        Args:
            filepath (str): Full file path where root should be replaced.
            template (str): Optional template for environment key. Must
                have one index format key.
                Default value if not entered: "${}"

        Returns:
            str: Path where root is replaced with environment root key.

        Raise:
            ValueError: When project's roots were not found in entered path.
        """
        success, rootless_path = self.find_root_template_from_path(filepath)
        if not success:
            raise ValueError(
                "{}: Project's roots were not found in path: {}".format(
                    self.project_name, filepath
                )
            )

        data = self.root_environmets_fill_data(template)
        return rootless_path.format(**data)

    def _project_entity_to_anatomy_data(self, project_entity):
        """Convert project document to anatomy data.

        Probably should fill missing keys and values.
        """

        output = copy.deepcopy(project_entity["config"])
        # TODO remove AYON convertion
        task_types = copy.deepcopy(project_entity["taskTypes"])
        new_task_types = {}
        for task_type in task_types:
            name = task_type["name"]
            new_task_types[name] = task_type
        output["tasks"] = new_task_types
        output["attributes"] = copy.deepcopy(project_entity["attrib"])

        return output

    def _apply_local_settings_on_anatomy_data(
        self, anatomy_data, root_overrides
    ):
        """Apply local settings on anatomy data.

        ATM local settings can modify project roots. Project name is required
        as local settings have data stored data by project's name.

        Local settings override root values in this order:
        1.) Check if local settings contain overrides for default project and
            apply it's values on roots if there are any.
        2.) If passed `project_name` is not None then check project specific
            overrides in local settings for the project and apply it's value on
            roots if there are any.

        NOTE: Root values of default project from local settings are always
        applied if are set.

        Args:
            anatomy_data (dict): Data for anatomy.
            root_overrides (dict): Data of local settings.
        """

        # Skip processing if roots for current active site are not available in
        #   local settings
        if not root_overrides:
            return

        current_platform = platform.system().lower()

        root_data = anatomy_data["roots"]
        for root_name, path in root_overrides.items():
            if root_name not in root_data:
                continue
            anatomy_data["roots"][root_name][current_platform] = (
                path
            )


class CacheItem:
    """Helper to cache data.

    Helper does not handle refresh of data and does not mark data as outdated.
    Who uses the object should check of outdated state on his own will.
    """

    default_lifetime = 10

    def __init__(self, lifetime=None):
        self._data = None
        self._cached = None
        self._lifetime = lifetime or self.default_lifetime

    @property
    def data(self):
        """Cached data/object.

        Returns:
            Any: Whatever was cached.
        """

        return self._data

    @property
    def is_outdated(self):
        """Item has outdated cache.

        Lifetime of cache item expired or was not yet set.

        Returns:
            bool: Item is outdated.
        """

        if self._cached is None:
            return True
        return (time.time() - self._cached) > self._lifetime

    def update_data(self, data):
        """Update cache of data.

        Args:
            data (Any): Data to cache.
        """

        self._data = data
        self._cached = time.time()


class Anatomy(BaseAnatomy):
    _sitesync_addon_cache = CacheItem()
    _project_cache = collections.defaultdict(CacheItem)
    _default_site_id_cache = collections.defaultdict(CacheItem)
    _root_overrides_cache = collections.defaultdict(
        lambda: collections.defaultdict(CacheItem)
    )

    def __init__(
        self, project_name=None, site_name=None, project_entity=None
    ):
        if not project_name:
            project_name = os.environ.get("AYON_PROJECT_NAME")

        if not project_name:
            raise ProjectNotSet((
                "Implementation bug: Project name is not set. Anatomy requires"
                " to load data for specific project."
            ))

        if not project_entity:
            project_entity = self.get_project_entity_from_cache(project_name)
        root_overrides = self._get_site_root_overrides(
            project_name, site_name
        )

        super(Anatomy, self).__init__(project_entity, root_overrides)

    @classmethod
    def get_project_entity_from_cache(cls, project_name):
        project_cache = cls._project_cache[project_name]
        if project_cache.is_outdated:
            project_cache.update_data(ayon_api.get_project(project_name))
        return copy.deepcopy(project_cache.data)

    @classmethod
    def get_sitesync_addon(cls):
        if cls._sitesync_addon_cache.is_outdated:
            manager = AddonsManager()
            cls._sitesync_addon_cache.update_data(
                manager.get_enabled_addon("sitesync")
            )
        return cls._sitesync_addon_cache.data

    @classmethod
    def _get_studio_roots_overrides(cls, project_name):
        """This would return 'studio' site override by local settings.

        Notes:
            This logic handles local overrides of studio site which may be
                available even when sync server is not enabled.
            Handling of 'studio' and 'local' site was separated as preparation
                for AYON development where that will be received from
                separated sources.

        Args:
            project_name (str): Name of project.

        Returns:
            Union[Dict[str, str], None]): Local root overrides.
        """
        if not project_name:
            return
        return ayon_api.get_project_roots_for_site(
            project_name, get_local_site_id()
        )

    @classmethod
    def _get_site_root_overrides(cls, project_name, site_name):
        """Get root overrides for site.

        Args:
            project_name (str): Project name for which root overrides should be
                received.
            site_name (Union[str, None]): Name of site for which root overrides
                should be returned.
        """

        # First check if sync server is available and enabled
        sitesync_addon = cls.get_sitesync_addon()
        if sitesync_addon is None or not sitesync_addon.enabled:
            # QUESTION is ok to force 'studio' when site sync is not enabled?
            site_name = "studio"

        elif not site_name:
            # Use sync server to receive active site name
            project_cache = cls._default_site_id_cache[project_name]
            if project_cache.is_outdated:
                project_cache.update_data(
                    sitesync_addon.get_active_site_type(project_name)
                )
            site_name = project_cache.data

        site_cache = cls._root_overrides_cache[project_name][site_name]
        if site_cache.is_outdated:
            if site_name == "studio":
                # Handle studio root overrides without sync server
                # - studio root overrides can be done even without sync server
                roots_overrides = cls._get_studio_roots_overrides(
                    project_name
                )
            else:
                # Ask sync server to get roots overrides
                roots_overrides = sitesync_addon.get_site_root_overrides(
                    project_name, site_name
                )
            site_cache.update_data(roots_overrides)
        return site_cache.data
