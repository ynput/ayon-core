import re
import os
import json
import contextlib
import functools
import platform
import tempfile
import warnings
from copy import deepcopy

import ayon_api

from ayon_core import AYON_CORE_ROOT
from ayon_core.settings import get_project_settings
from ayon_core.lib import (
    filter_profiles,
    StringTemplate,
    run_ayon_launcher_process,
    Logger,
)
from ayon_core.lib.transcoding import VIDEO_EXTENSIONS, IMAGE_EXTENSIONS
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.template_data import get_template_data
from ayon_core.pipeline.load import get_representation_path_with_anatomy

log = Logger.get_logger(__name__)


class CachedData:
    remapping = {}
    has_compatible_ocio_package = None
    config_version_data = {}
    ocio_config_colorspaces = {}
    allowed_exts = {
        ext.lstrip(".") for ext in IMAGE_EXTENSIONS.union(VIDEO_EXTENSIONS)
    }


def deprecated(new_destination):
    """Mark functions as deprecated.

    It will result in a warning being emitted when the function is used.
    """

    func = None
    if callable(new_destination):
        func = new_destination
        new_destination = None

    def _decorator(decorated_func):
        if new_destination is None:
            warning_message = (
                " Please check content of deprecated function to figure out"
                " possible replacement."
            )
        else:
            warning_message = " Please replace your usage with '{}'.".format(
                new_destination
            )

        @functools.wraps(decorated_func)
        def wrapper(*args, **kwargs):
            warnings.simplefilter("always", DeprecationWarning)
            warnings.warn(
                (
                    "Call to deprecated function '{}'"
                    "\nFunction was moved or removed.{}"
                ).format(decorated_func.__name__, warning_message),
                category=DeprecationWarning,
                stacklevel=4
            )
            return decorated_func(*args, **kwargs)
        return wrapper

    if func is None:
        return _decorator
    return _decorator(func)


@contextlib.contextmanager
def _make_temp_json_file():
    """Wrapping function for json temp file
    """
    temporary_json_file = None
    try:
        # Store dumped json to temporary file
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False
        ) as tmpfile:
            temporary_json_filepath = tmpfile.name.replace("\\", "/")

        yield temporary_json_filepath

    except IOError as exc:
        raise IOError(
            "Unable to create temp json file: {}".format(exc)
        )

    finally:
        # Remove the temporary json
        if temporary_json_file is not None:
            os.remove(temporary_json_filepath)


def has_compatible_ocio_package():
    """Current process has available compatible 'PyOpenColorIO'.

    Returns:
        bool: True if compatible package is available.

    """
    if CachedData.has_compatible_ocio_package is not None:
        return CachedData.has_compatible_ocio_package

    is_compatible = False
    try:
        import PyOpenColorIO

        # Check if PyOpenColorIO is compatible
        # - version 2.0.0 or higher is required
        # NOTE version 1 does not have '__version__' attribute
        if hasattr(PyOpenColorIO, "__version__"):
            version_parts = PyOpenColorIO.__version__.split(".")
            major = int(version_parts[0])
            is_compatible = (major, ) >= (2, )
    except ImportError:
        pass

    CachedData.has_compatible_ocio_package = is_compatible
    # compatible
    return CachedData.has_compatible_ocio_package


def get_ocio_config_script_path():
    """Get path to ocio wrapper script

    Returns:
        str: path string

    """
    return os.path.join(
        os.path.normpath(AYON_CORE_ROOT),
        "scripts",
        "ocio_wrapper.py"
    )


def get_colorspace_name_from_filepath(
    filepath,
    host_name,
    project_name,
    config_data,
    file_rules=None,
    project_settings=None,
    validate=True
):
    """Get colorspace name from filepath

    Args:
        filepath (str): Path string, file rule pattern is tested on it.
        host_name (str): Host name.
        project_name (str): Project name.
        config_data (dict): Config path and template in dict.
        file_rules (Optional[dict]): File rule data from settings.
        project_settings (Optional[dict]): Project settings.
        validate (Optional[bool]): should resulting colorspace be validated
            with config file? Defaults to True.

    Returns:
        Union[str, None]: name of colorspace

    """
    if not config_data:
        # in case global or host color management is not enabled
        return None

    if file_rules is None:
        if project_settings is None:
            project_settings = get_project_settings(project_name)
        file_rules = get_imageio_file_rules(
            project_name, host_name, project_settings
        )

    # use ImageIO file rules
    colorspace_name = get_imageio_file_rules_colorspace_from_filepath(
        filepath,
        host_name,
        project_name,
        config_data=config_data,
        file_rules=file_rules,
        project_settings=project_settings
    )

    # try to get colorspace from OCIO v2 file rules
    if (
        not colorspace_name
        and compatibility_check_config_version(config_data["path"], major=2)
    ):
        colorspace_name = get_config_file_rules_colorspace_from_filepath(
            config_data["path"], filepath)

    # use parse colorspace from filepath as fallback
    colorspace_name = colorspace_name or parse_colorspace_from_filepath(
        filepath, config_path=config_data["path"]
    )

    if not colorspace_name:
        log.info("No imageio file rule matched input path: '{}'".format(
            filepath
        ))
        return None

    # validate matching colorspace with config
    if validate:
        validate_imageio_colorspace_in_config(
            config_data["path"], colorspace_name
        )

    return colorspace_name


def get_imageio_file_rules_colorspace_from_filepath(
    filepath,
    host_name,
    project_name,
    config_data,
    file_rules=None,
    project_settings=None
):
    """Get colorspace name from filepath

    ImageIO Settings file rules are tested for matching rule.

    Args:
        filepath (str): Path string, file rule pattern is tested on it.
        host_name (str): Host name.
        project_name (str): Project name.
        config_data (dict): Config path and template in dict.
        file_rules (Optional[dict]): File rule data from settings.
        project_settings (Optional[dict]): Project settings.

    Returns:
        Union[str, None]: Name of colorspace.

    """
    if not config_data:
        # in case global or host color management is not enabled
        return None

    if file_rules is None:
        if project_settings is None:
            project_settings = get_project_settings(project_name)
        file_rules = get_imageio_file_rules(
            project_name, host_name, project_settings
        )

    # match file rule from path
    colorspace_name = None
    for file_rule in file_rules:
        pattern = file_rule["pattern"]
        extension = file_rule["ext"]
        ext_match = re.match(
            r".*(?=.{})".format(extension), filepath
        )
        file_match = re.search(
            pattern, filepath
        )

        if ext_match and file_match:
            colorspace_name = file_rule["colorspace"]

    return colorspace_name


def get_config_file_rules_colorspace_from_filepath(config_path, filepath):
    """Get colorspace from file path wrapper.

    Wrapper function for getting colorspace from file path
    with use of OCIO v2 file-rules.

    Args:
        config_path (str): path leading to config.ocio file
        filepath (str): path leading to a file

    Returns:
        Union[str, None]: matching colorspace name

    """
    if has_compatible_ocio_package():
        result_data = _get_config_file_rules_colorspace_from_filepath(
            config_path, filepath
        )
    else:
        result_data = _get_wrapped_with_subprocess(
            "get_config_file_rules_colorspace_from_filepath",
            config_path=config_path,
            filepath=filepath
        )

    if result_data:
        return result_data[0]
    return None


def get_config_version_data(config_path):
    """Return major and minor version info.

    Args:
        config_path (str): path string leading to config.ocio

    Raises:
        IOError: Input config does not exist.

    Returns:
        dict: minor and major keys with values

    """
    if config_path not in CachedData.config_version_data:
        if has_compatible_ocio_package():
            version_data = _get_config_version_data(config_path)
        else:
            version_data = _get_wrapped_with_subprocess(
                "get_config_version_data",
                config_path=config_path
            )
        CachedData.config_version_data[config_path] = version_data

    return deepcopy(CachedData.config_version_data[config_path])


def parse_colorspace_from_filepath(
    filepath, colorspaces=None, config_path=None
):
    """Parse colorspace name from filepath

    An input path can have colorspace name used as part of name
    or as folder name.

    Example:
        >>> config_path = "path/to/config.ocio"
        >>> colorspaces = get_ocio_config_colorspaces(config_path)
        >>> colorspace = parse_colorspace_from_filepath(
                "path/to/file/acescg/file.exr",
                colorspaces=colorspaces
            )
        >>> print(colorspace)
        acescg

    Args:
        filepath (str): path string
        colorspaces (Optional[dict[str]]): list of colorspaces
        config_path (Optional[str]): path to config.ocio file

    Returns:
        str: name of colorspace
    """
    def _get_colorspace_match_regex(colorspaces):
        """Return a regex pattern

        Allows to search a colorspace match in a filename

        Args:
            colorspaces (list): List of colorspace names

        Returns:
            re.Pattern: regex pattern
        """
        pattern = "|".join(
            # Allow to match spaces also as underscores because the
            # integrator replaces spaces with underscores in filenames
            re.escape(colorspace)
            # Sort by longest first so the regex matches longer matches
            # over smaller matches, e.g. matching 'Output - sRGB' over 'sRGB'
            for colorspace in sorted(colorspaces, key=len, reverse=True)
        )
        return re.compile(pattern)

    if not colorspaces and not config_path:
        raise ValueError(
            "Must provide `config_path` if `colorspaces` is not provided."
        )

    colorspaces = (
        colorspaces
        or get_ocio_config_colorspaces(config_path)["colorspaces"]
    )
    underscored_colorspaces = {
        key.replace(" ", "_"): key for key in colorspaces
        if " " in key
    }

    # match colorspace from  filepath
    regex_pattern = _get_colorspace_match_regex(
        list(colorspaces) + list(underscored_colorspaces))
    match = regex_pattern.search(filepath)
    colorspace = match.group(0) if match else None

    if colorspace in underscored_colorspaces:
        return underscored_colorspaces[colorspace]

    if colorspace:
        return colorspace

    log.info("No matching colorspace in config '{}' for path: '{}'".format(
        config_path, filepath
    ))
    return None


def validate_imageio_colorspace_in_config(config_path, colorspace_name):
    """Validator making sure colorspace name is used in config.ocio

    Args:
        config_path (str): path leading to config.ocio file
        colorspace_name (str): tested colorspace name

    Raises:
        KeyError: missing colorspace name

    Returns:
        bool: True if exists

    """
    colorspaces = get_ocio_config_colorspaces(config_path)["colorspaces"]
    if colorspace_name not in colorspaces:
        raise KeyError(
            "Missing colorspace '{}' in config file '{}'".format(
                colorspace_name, config_path)
        )
    return True


def _get_wrapped_with_subprocess(command, **kwargs):
    """Get data via subprocess.

    Args:
        command (str): command name
        **kwargs: command arguments

    Returns:
        Any[dict, None]: data
    """
    with _make_temp_json_file() as tmp_json_path:
        # Prepare subprocess arguments
        args = [
            "run",
            get_ocio_config_script_path(),
            command
        ]

        for key, value in kwargs.items():
            args.extend(("--{}".format(key), value))

        args.append("--output_path")
        args.append(tmp_json_path)

        log.info("Executing: {}".format(" ".join(args)))

        run_ayon_launcher_process(*args, logger=log)

        # return all colorspaces
        with open(tmp_json_path, "r") as stream:
            return json.load(stream)


def compatibility_check_config_version(config_path, major=1, minor=None):
    """Making sure PyOpenColorIO config version is compatible"""

    version_data = get_config_version_data(config_path)

    # check major version
    if version_data["major"] != major:
        return False

    # check minor version
    if minor is not None and version_data["minor"] != minor:
        return False

    return True


def get_ocio_config_colorspaces(config_path):
    """Get all colorspace data

    Wrapper function for aggregating all names and its families.
    Families can be used for building menu and submenus in gui.

    Args:
        config_path (str): path leading to config.ocio file

    Returns:
        dict: colorspace and family in couple

    """
    if config_path not in CachedData.ocio_config_colorspaces:
        if has_compatible_ocio_package():
            config_colorspaces = _get_ocio_config_colorspaces(config_path)
        else:
            config_colorspaces = _get_wrapped_with_subprocess(
                "get_ocio_config_colorspaces",
                config_path=config_path
            )
        CachedData.ocio_config_colorspaces[config_path] = config_colorspaces

    return deepcopy(CachedData.ocio_config_colorspaces[config_path])


def convert_colorspace_enumerator_item(
    colorspace_enum_item,
    config_items
):
    """Convert colorspace enumerator item to dictionary

    Args:
        colorspace_enum_item (str): Colorspace and family in couple.
        config_items (dict[str,dict]): Colorspace data.

    Returns:
        dict: colorspace data

    """
    if "::" not in colorspace_enum_item:
        return None

    # split string with `::` separator and set first as key and second as value
    item_type, item_name = colorspace_enum_item.split("::")

    item_data = None
    if item_type == "aliases":
        # loop through all colorspaces and find matching alias
        for name, _data in config_items.get("colorspaces", {}).items():
            if item_name in _data.get("aliases", []):
                item_data = deepcopy(_data)
                item_data.update({
                    "name": name,
                    "type": "colorspace"
                })
                break
    else:
        # find matching colorspace item found in labeled_colorspaces
        item_data = config_items.get(item_type, {}).get(item_name)
        if item_data:
            item_data = deepcopy(item_data)
            item_data.update({
                "name": item_name,
                "type": item_type
            })

    # raise exception if item is not found
    if not item_data:
        message_config_keys = ", ".join(
            "'{}':{}".format(
                key,
                set(config_items.get(key, {}).keys())
            ) for key in config_items.keys()
        )
        raise KeyError(
            "Missing colorspace item '{}' in config data: [{}]".format(
                colorspace_enum_item, message_config_keys
            )
        )

    return item_data


def get_colorspaces_enumerator_items(
    config_items,
    include_aliases=False,
    include_looks=False,
    include_roles=False,
    include_display_views=False
):
    """Get all colorspace data with labels

    Wrapper function for aggregating all names and its families.
    Families can be used for building menu and submenus in gui.

    Args:
        config_items (dict[str,dict]): Colorspace data coming from
            `get_ocio_config_colorspaces` function.
        include_aliases (Optional[bool]): Include aliases in result.
        include_looks (Optional[bool]): Include looks in result.
        include_roles (Optional[bool]): Include roles in result.
        include_display_views (Optional[bool]): Include display views
            in result.

    Returns:
        list[tuple[str, str]]: Colorspace and family in couples.

    """
    aliases = set()
    colorspaces = set()
    looks = set()
    roles = set()
    display_views = set()
    for items_type, colorspace_items in config_items.items():
        if items_type == "colorspaces":
            for color_name, color_data in colorspace_items.items():
                if color_data.get("aliases"):
                    aliases.update({
                        (
                            "aliases::{}".format(alias_name),
                            "[alias] {} ({})".format(alias_name, color_name)
                        )
                        for alias_name in color_data["aliases"]
                    })
                colorspaces.add((
                    "{}::{}".format(items_type, color_name),
                    "[colorspace] {}".format(color_name)
                ))

        elif items_type == "looks":
            looks.update({
                (
                    "{}::{}".format(items_type, name),
                    "[look] {} ({})".format(name, role_data["process_space"])
                )
                for name, role_data in colorspace_items.items()
            })

        elif items_type == "displays_views":
            display_views.update({
                (
                    "{}::{}".format(items_type, name),
                    "[view (display)] {}".format(name)
                )
                for name, _ in colorspace_items.items()
            })

        elif items_type == "roles":
            roles.update({
                (
                    "{}::{}".format(items_type, name),
                    "[role] {} ({})".format(name, role_data["colorspace"])
                )
                for name, role_data in colorspace_items.items()
            })

    def _sort_key_getter(item):
        """Use colorspace for sorting.

        Args:
            item (tuple[str, str]): Item with colorspace and label.

        Returns:
            str: Colorspace.

        """
        return item[0]

    labeled_colorspaces = []
    if include_roles:
        labeled_colorspaces.extend(
            sorted(roles, key=_sort_key_getter)
        )

    # Add colorspaces after roles, so it is not first in menu
    labeled_colorspaces.extend(
        sorted(colorspaces, key=_sort_key_getter)
    )

    if include_aliases:
        labeled_colorspaces.extend(
            sorted(aliases, key=_sort_key_getter)
        )

    if include_looks:
        labeled_colorspaces.extend(
            sorted(looks, key=_sort_key_getter)
        )

    if include_display_views:
        labeled_colorspaces.extend(
            sorted(display_views, key=_sort_key_getter)
        )

    return labeled_colorspaces


def get_ocio_config_views(config_path):
    """Get all viewer data

    Wrapper function for aggregating all display and related viewers.
    Key can be used for building gui menu with submenus.

    Args:
        config_path (str): path leading to config.ocio file

    Returns:
        dict: `display/viewer` and viewer data

    """
    if has_compatible_ocio_package():
        return _get_ocio_config_views(config_path)

    return _get_wrapped_with_subprocess(
        "get_ocio_config_views",
        config_path=config_path
    )


def _get_global_config_data(
    project_name,
    host_name,
    anatomy,
    template_data,
    imageio_global,
    folder_id,
    log,
):
    """Get global config data.

    Global config from core settings is using profiles that are based on
    host name, task name and task type. The filtered profile can define 3
    types of config sources:
    1. AYON ocio addon configs.
    2. Custom path to ocio config.
    3. Path to 'ocioconfig' representation on product. Name of product can be
        defined in settings. Product name can be regex but exact match is
        always preferred.

    None is returned when no profile is found, when path

    Args:
        project_name (str): Project name.
        host_name (str): Host name.
        anatomy (Anatomy): Project anatomy object.
        template_data (dict[str, Any]): Template data.
        imageio_global (dict[str, Any]): Core imagio settings.
        folder_id (Union[dict[str, Any], None]): Folder id.
        log (logging.Logger): Logger object.

    Returns:
        Union[dict[str, str], None]: Config data with path and template
            or None.

    """
    task_name = task_type = None
    task_data = template_data.get("task")
    if task_data:
        task_name = task_data["name"]
        task_type = task_data["type"]

    filter_values = {
        "task_names": task_name,
        "task_types": task_type,
        "host_names": host_name,
    }
    profile = filter_profiles(
        imageio_global["ocio_config_profiles"], filter_values
    )
    if profile is None:
        log.info(f"No config profile matched filters {str(filter_values)}")
        return None

    profile_type = profile["type"]
    if profile_type in ("builtin_path", "custom_path"):
        template = profile[profile_type]
        result = StringTemplate.format_strict_template(
            template, template_data
        )
        normalized_path = str(result.normalized())
        if not os.path.exists(normalized_path):
            log.warning(f"Path was not found '{normalized_path}'.")
            return None

        return {
            "path": normalized_path,
            "template": template
        }

    # TODO decide if this is the right name for representation
    repre_name = "ocioconfig"

    folder_info = template_data.get("folder")
    if not folder_info:
        log.warning("Folder info is missing.")
        return None
    folder_path = folder_info["path"]

    product_name = profile["product_name"]
    if folder_id is None:
        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path, fields={"id"}
        )
        if not folder_entity:
            log.warning(f"Folder entity '{folder_path}' was not found..")
            return None
        folder_id = folder_entity["id"]

    product_entities_by_name = {
        product_entity["name"]: product_entity
        for product_entity in ayon_api.get_products(
            project_name,
            folder_ids={folder_id},
            product_name_regex=product_name,
            fields={"id", "name"}
        )
    }
    if not product_entities_by_name:
        log.debug(
            f"No product entities were found for folder '{folder_path}' with"
            f" product name filter '{product_name}'."
        )
        return None

    # Try to use exact match first, otherwise use first available product
    product_entity = product_entities_by_name.get(product_name)
    if product_entity is None:
        product_entity = next(iter(product_entities_by_name.values()))

    product_name = product_entity["name"]
    # Find last product version
    version_entity = ayon_api.get_last_version_by_product_id(
        project_name,
        product_id=product_entity["id"],
        fields={"id"}
    )
    if not version_entity:
        log.info(
            f"Product '{product_name}' does not have available any versions."
        )
        return None

    # Find 'ocioconfig' representation entity
    repre_entity = ayon_api.get_representation_by_name(
        project_name,
        representation_name=repre_name,
        version_id=version_entity["id"],
    )
    if not repre_entity:
        log.debug(
            f"Representation '{repre_name}'"
            f" not found on product '{product_name}'."
        )
        return None

    path = get_representation_path_with_anatomy(repre_entity, anatomy)
    template = repre_entity["attrib"]["template"]
    return {
        "path": path,
        "template": template,
    }


def get_imageio_config_preset(
    project_name,
    folder_path,
    task_name,
    host_name,
    anatomy=None,
    project_settings=None,
    template_data=None,
    env=None,
    folder_id=None,
):
    """Returns config data from settings

    Output contains 'path' key and 'template' key holds its template.

    Template data can be prepared with 'get_template_data'.

    Args:
        project_name (str): Project name.
        folder_path (str): Folder path.
        task_name (str): Task name.
        host_name (str): Host name.
        anatomy (Optional[Anatomy]): Project anatomy object.
        project_settings (Optional[dict]): Project settings.
        template_data (Optional[dict]): Template data used for
            template formatting.
        env (Optional[dict]): Environment variables. Environments are used
            for template formatting too. Values from 'os.environ' are used
            when not provided.
        folder_id (Optional[str]): Folder id. Is used only when config path
            is received from published representation. Is autofilled when
            not provided.

    Returns:
        dict: config path data or empty dict

    """
    if not project_settings:
        project_settings = get_project_settings(project_name)

    # Get colorspace settings
    imageio_global, imageio_host = _get_imageio_settings(
        project_settings, host_name
    )
    # Global color management must be enabled to be able to use host settings
    if not imageio_global["activate_global_color_management"]:
        log.info("Colorspace management is disabled globally.")
        return {}

    # Host 'ocio_config' is optional
    host_ocio_config = imageio_host.get("ocio_config") or {}
    # TODO remove
    #  - backward compatibility when host settings had only 'enabled' flag
    #      the flag was split into 'activate_global_color_management'
    #      and 'override_global_config'
    host_ocio_config_enabled = host_ocio_config.get("enabled", False)

    # Check if host settings group is having 'activate_host_color_management'
    # - if it does not have activation key then default it to True so it uses
    #       global settings
    activate_host_color_management = imageio_host.get(
        "activate_host_color_management"
    )
    if activate_host_color_management is None:
        activate_host_color_management = host_ocio_config_enabled

    if not activate_host_color_management:
        # if host settings are disabled return False because
        # it is expected that no colorspace management is needed
        log.info(
            f"Colorspace management for host '{host_name}' is disabled."
        )
        return {}

    project_entity = None
    if anatomy is None:
        project_entity = ayon_api.get_project(project_name)
        anatomy = Anatomy(project_name, project_entity=project_entity)

    if env is None:
        env = dict(os.environ.items())

    if template_data:
        template_data = deepcopy(template_data)
    else:
        if not project_entity:
            project_entity = ayon_api.get_project(project_name)

        folder_entity = task_entity = folder_id = None
        if folder_path:
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path
            )
            folder_id = folder_entity["id"]

        if folder_id and task_name:
            task_entity = ayon_api.get_task_by_name(
                project_name, folder_id, task_name
            )
        template_data = get_template_data(
            project_entity,
            folder_entity,
            task_entity,
            host_name,
            project_settings,
        )

    # Add project roots to anatomy data
    template_data["root"] = anatomy.roots
    template_data["platform"] = platform.system().lower()

    # Add environment variables to template data
    template_data.update(env)

    # Get config path from core or host settings
    #  - based on override flag in host settings
    # TODO: in future rewrite this to be more explicit
    override_global_config = host_ocio_config.get("override_global_config")
    if override_global_config is None:
        override_global_config = host_ocio_config_enabled

    if not override_global_config:
        config_data = _get_global_config_data(
            project_name,
            host_name,
            anatomy,
            template_data,
            imageio_global,
            folder_id,
            log,
        )
    else:
        config_data = _get_host_config_data(
            host_ocio_config["filepath"], template_data
        )

    if not config_data:
        raise FileExistsError(
            "No OCIO config found in settings. It is"
            " either missing or there is typo in path inputs"
        )

    return config_data


def _get_host_config_data(templates, template_data):
    """Return first existing path in path list.

    Use template data to fill possible formatting in paths.

    Args:
        templates (list[str]): List of templates to config paths.
        template_data (dict): Template data used to format templates.

    Returns:
        Union[dict, None]: Config data or 'None' if templates are empty
            or any path exists.

    """
    for template in templates:
        formatted_path = StringTemplate.format_template(
            template, template_data
        )
        if not formatted_path.solved:
            continue

        path = os.path.abspath(formatted_path)
        if os.path.exists(path):
            return {
                "path": os.path.normpath(path),
                "template": template
            }


def get_imageio_file_rules(project_name, host_name, project_settings=None):
    """Get ImageIO File rules from project settings

    Args:
        project_name (str): Project name.
        host_name (str): Host name.
        project_settings (Optional[dict]): Project settings.

    Returns:
        list[dict[str, Any]]: file rules data

    """
    project_settings = project_settings or get_project_settings(project_name)

    imageio_global, imageio_host = _get_imageio_settings(
        project_settings, host_name)

    # host is optional, some might not have any settings
    frules_host = imageio_host.get("file_rules", {})

    # compile file rules dictionary
    activate_host_rules = frules_host.get("activate_host_rules")
    if activate_host_rules is None:
        # TODO: remove this in future - backward compatibility
        activate_host_rules = frules_host.get("enabled", False)

    if activate_host_rules:
        return frules_host["rules"]

    # get file rules from global and host_name
    frules_global = imageio_global["file_rules"]
    activate_global_rules = (
        frules_global.get("activate_global_file_rules", False)
        # TODO: remove this in future - backward compatibility
        or frules_global.get("enabled")
    )

    if not activate_global_rules:
        log.info(
            "Colorspace global file rules are disabled."
        )
        return []

    return frules_global["rules"]


def get_remapped_colorspace_to_native(
    ocio_colorspace_name, host_name, imageio_host_settings
):
    """Return native colorspace name.

    Args:
        ocio_colorspace_name (str | None): OCIO colorspace name.
        host_name (str): Host name.
        imageio_host_settings (dict[str, Any]): ImageIO host settings.

    Returns:
        Union[str, None]: native colorspace name defined in remapping or None
    """

    host_mapping = CachedData.remapping.setdefault(host_name, {})
    if "to_native" not in host_mapping:
        remapping_rules = imageio_host_settings["remapping"]["rules"]
        host_mapping["to_native"] = {
            rule["ocio_name"]: rule["host_native_name"]
            for rule in remapping_rules
        }

    return host_mapping["to_native"].get(ocio_colorspace_name)


def get_remapped_colorspace_from_native(
    host_native_colorspace_name, host_name, imageio_host_settings
):
    """Return ocio colorspace name remapped from host native used name.

    Args:
        host_native_colorspace_name (str): host native colorspace name
        host_name (str): Host name.
        imageio_host_settings (dict[str, Any]): ImageIO host settings.

    Returns:
        Union[str, None]: Ocio colorspace name defined in remapping or None.

    """
    host_mapping = CachedData.remapping.setdefault(host_name, {})
    if "from_native" not in host_mapping:
        remapping_rules = imageio_host_settings["remapping"]["rules"]
        host_mapping["from_native"] = {
            rule["host_native_name"]: rule["ocio_name"]
            for rule in remapping_rules
        }

    return host_mapping["from_native"].get(host_native_colorspace_name)


def _get_imageio_settings(project_settings, host_name):
    """Get ImageIO settings for global and host

    Args:
        project_settings (dict[str, Any]): Project settings.
        host_name (str): Host name.

    Returns:
        tuple[dict, dict]: Image io settings for global and host.

    """
    # get image io from global and host_name
    imageio_global = project_settings["core"]["imageio"]
    # host is optional, some might not have any settings
    imageio_host = project_settings.get(host_name, {}).get("imageio", {})

    return imageio_global, imageio_host


def get_colorspace_settings_from_publish_context(context_data):
    """Returns solved settings for the host context.

    Args:
        context_data (publish.Context.data): publishing context data

    Returns:
        tuple | bool: config, file rules or None

    """
    if "imageioSettings" in context_data and context_data["imageioSettings"]:
        return context_data["imageioSettings"]

    project_name = context_data["projectName"]
    folder_path = context_data["folderPath"]
    task_name = context_data["task"]
    host_name = context_data["hostName"]
    anatomy = context_data["anatomy"]
    template_data = context_data["anatomyData"]
    project_settings = context_data["project_settings"]
    folder_id = None
    folder_entity = context_data.get("folderEntity")
    if folder_entity:
        folder_id = folder_entity["id"]

    config_data = get_imageio_config_preset(
        project_name,
        folder_path,
        task_name,
        host_name,
        anatomy=anatomy,
        project_settings=project_settings,
        template_data=template_data,
        folder_id=folder_id,
    )

    # caching invalid state, so it's not recalculated all the time
    file_rules = None
    if config_data:
        file_rules = get_imageio_file_rules(
            project_name,
            host_name,
            project_settings=project_settings
        )

    # caching settings for future instance processing
    context_data["imageioSettings"] = (config_data, file_rules)

    return config_data, file_rules


def set_colorspace_data_to_representation(
    representation,
    context_data,
    colorspace=None,
    log=None
):
    """Sets colorspace data to representation.

    Example:
        ```
        {
            # for other publish plugins and loaders
            "colorspace": "linear",
            "config": {
                # for future references in case need
                "path": "/abs/path/to/config.ocio",
                # for other plugins within remote publish cases
                "template": "{project[root]}/path/to/config.ocio"
            }
        }
        ```

    Args:
        representation (dict): publishing representation
        context_data (publish.Context.data): publishing context data
        colorspace (Optional[str]): Colorspace name.
        log (Optional[logging.Logger]): logger instance.

    """
    log = log or Logger.get_logger(__name__)

    file_ext = representation["ext"]

    # check if `file_ext` in lower case is in CachedData.allowed_exts
    if file_ext.lstrip(".").lower() not in CachedData.allowed_exts:
        log.debug(
            "Extension '{}' is not in allowed extensions.".format(file_ext)
        )
        return

    # get colorspace settings
    config_data, file_rules = get_colorspace_settings_from_publish_context(
        context_data)

    # in case host color management is not enabled
    if not config_data:
        log.warning("Host's colorspace management is disabled.")
        return

    log.debug("Config data is: `{}`".format(config_data))

    project_name = context_data["projectName"]
    host_name = context_data["hostName"]
    project_settings = context_data["project_settings"]

    # get one filename
    filename = representation["files"]
    if isinstance(filename, list):
        filename = filename[0]

    # get matching colorspace from rules
    if colorspace is None:
        colorspace = get_imageio_file_rules_colorspace_from_filepath(
            filename,
            host_name,
            project_name,
            config_data=config_data,
            file_rules=file_rules,
            project_settings=project_settings
        )

    # infuse data to representation
    if colorspace:
        colorspace_data = {
            "colorspace": colorspace,
            "config": config_data
        }

        # update data key
        representation["colorspaceData"] = colorspace_data


def get_display_view_colorspace_name(config_path, display, view):
    """Returns the colorspace attribute of the (display, view) pair.

    Args:
        config_path (str): path string leading to config.ocio
        display (str): display name e.g. "ACES"
        view (str): view name e.g. "sRGB"

    Returns:
        str: View color space name. e.g. "Output - sRGB"

    """
    if has_compatible_ocio_package():
        return _get_display_view_colorspace_name(
            config_path, display, view
        )
    return _get_wrapped_with_subprocess(
        "get_display_view_colorspace_name",
        config_path=config_path,
        display=display,
        view=view
    )


# --- Implementation of logic using 'PyOpenColorIO' ---
def _get_ocio_config(config_path):
    """Helper function to create OCIO config object.

    Args:
        config_path (str): Path to config.

    Returns:
        PyOpenColorIO.Config: OCIO config for the confing path.

    """
    import PyOpenColorIO

    config_path = os.path.abspath(config_path)

    if not os.path.isfile(config_path):
        raise IOError("Input path should be `config.ocio` file")

    return PyOpenColorIO.Config.CreateFromFile(config_path)


def _get_config_file_rules_colorspace_from_filepath(config_path, filepath):
    """Return found colorspace data found in v2 file rules.

    Args:
        config_path (str): path string leading to config.ocio
        filepath (str): path string leading to v2 file rules

    Raises:
        IOError: Input config does not exist.

    Returns:
        dict: aggregated available colorspaces

    """
    config = _get_ocio_config(config_path)

    # TODO: use `parseColorSpaceFromString` instead if ocio v1
    return config.getColorSpaceFromFilepath(str(filepath))


def _get_config_version_data(config_path):
    """Return major and minor version info.

    Args:
        config_path (str): path string leading to config.ocio

    Raises:
        IOError: Input config does not exist.

    Returns:
        dict: minor and major keys with values

    """
    config = _get_ocio_config(config_path)

    return {
        "major": config.getMajorVersion(),
        "minor": config.getMinorVersion()
    }


def _get_display_view_colorspace_name(config_path, display, view):
    """Returns the colorspace attribute of the (display, view) pair.

    Args:
        config_path (str): path string leading to config.ocio
        display (str): display name e.g. "ACES"
        view (str): view name e.g. "sRGB"

    Raises:
        IOError: Input config does not exist.

    Returns:
        str: view color space name e.g. "Output - sRGB"

    """
    config = _get_ocio_config(config_path)
    return config.getDisplayViewColorSpaceName(display, view)


def _get_ocio_config_colorspaces(config_path):
    """Return all found colorspace data.

    Args:
        config_path (str): path string leading to config.ocio

    Raises:
        IOError: Input config does not exist.

    Returns:
        dict: aggregated available colorspaces

    """
    config = _get_ocio_config(config_path)

    colorspace_data = {
        "roles": {},
        "colorspaces": {
            color.getName(): {
                "family": color.getFamily(),
                "categories": list(color.getCategories()),
                "aliases": list(color.getAliases()),
                "equalitygroup": color.getEqualityGroup(),
            }
            for color in config.getColorSpaces()
        },
        "displays_views": {
            f"{view} ({display})": {
                "display": display,
                "view": view

            }
            for display in config.getDisplays()
            for view in config.getViews(display)
        },
        "looks": {}
    }

    # add looks
    looks = config.getLooks()
    if looks:
        colorspace_data["looks"] = {
            look.getName(): {"process_space": look.getProcessSpace()}
            for look in looks
        }

    # add roles
    roles = config.getRoles()
    if roles:
        colorspace_data["roles"] = {
            role: {"colorspace": colorspace}
            for (role, colorspace) in roles
        }

    return colorspace_data


def _get_ocio_config_views(config_path):
    """Return all found viewer data.

    Args:
        config_path (str): path string leading to config.ocio

    Raises:
        IOError: Input config does not exist.

    Returns:
        dict: aggregated available viewers

    """
    config = _get_ocio_config(config_path)

    output = {}
    for display in config.getDisplays():
        for view in config.getViews(display):
            colorspace = config.getDisplayViewColorSpaceName(display, view)
            # Special token. See https://opencolorio.readthedocs.io/en/latest/guides/authoring/authoring.html#shared-views # noqa
            if colorspace == "<USE_DISPLAY_NAME>":
                colorspace = display

            output[f"{display}/{view}"] = {
                "display": display,
                "view": view,
                "colorspace": colorspace
            }

    return output


# --- Current context functions ---
def get_current_context_imageio_config_preset(
    anatomy=None,
    project_settings=None,
    template_data=None,
    env=None,
):
    """Get ImageIO config preset for current context.

    Args:
        anatomy (Optional[Anatomy]): Current project anatomy.
        project_settings (Optional[dict[str, Any]]): Current project settings.
        template_data (Optional[dict[str, Any]]): Prepared template data
            for current context.
        env (Optional[dict[str, str]]): Custom environment variable values.

    Returns:
        dict: ImageIO config preset.

    """
    from .context_tools import get_current_context, get_current_host_name

    context = get_current_context()
    host_name = get_current_host_name()
    return get_imageio_config_preset(
        context["project_name"],
        context["folder_path"],
        context["task_name"],
        host_name,
        anatomy=anatomy,
        project_settings=project_settings,
        template_data=template_data,
        env=env,
    )


# --- Deprecated functions ---
@deprecated("has_compatible_ocio_package")
def compatibility_check():
    """Making sure PyOpenColorIO is importable

    Deprecated:
        Deprecated since '0.3.2'. Use `has_compatible_ocio_package` instead.
    """

    return has_compatible_ocio_package()


@deprecated("get_imageio_file_rules_colorspace_from_filepath")
def get_imageio_colorspace_from_filepath(*args, **kwargs):
    return get_imageio_file_rules_colorspace_from_filepath(*args, **kwargs)


@deprecated("get_imageio_file_rules_colorspace_from_filepath")
def get_colorspace_from_filepath(*args, **kwargs):
    return get_imageio_file_rules_colorspace_from_filepath(*args, **kwargs)


@deprecated("_get_wrapped_with_subprocess")
def get_colorspace_data_subprocess(config_path):
    """[Deprecated] Get colorspace data via subprocess

    Deprecated:
        Deprecated since OpenPype. Use `_get_wrapped_with_subprocess` instead.

    Args:
        config_path (str): path leading to config.ocio file

    Returns:
        dict: colorspace and family in couple
    """
    return _get_wrapped_with_subprocess(
        "get_ocio_config_colorspaces",
        config_path=config_path
    )


@deprecated("_get_wrapped_with_subprocess")
def get_views_data_subprocess(config_path):
    """[Deprecated] Get viewers data via subprocess

    Deprecated:
        Deprecated since OpenPype. Use `_get_wrapped_with_subprocess` instead.

    Args:
        config_path (str): path leading to config.ocio file

    Returns:
        dict: `display/viewer` and viewer data

    """
    return _get_wrapped_with_subprocess(
        "get_ocio_config_views",
        config_path=config_path
    )


@deprecated("get_imageio_config_preset")
def get_imageio_config(
    project_name,
    host_name,
    project_settings=None,
    anatomy_data=None,
    anatomy=None,
    env=None
):
    """Returns config data from settings

    Config path is formatted in `path` key
    and original settings input is saved into `template` key.

    Deprecated:
        Deprecated since '0.3.1' . Use `get_imageio_config_preset` instead.

    Args:
        project_name (str): project name
        host_name (str): host name
        project_settings (Optional[dict]): Project settings.
        anatomy_data (Optional[dict]): anatomy formatting data.
        anatomy (Optional[Anatomy]): Anatomy object.
        env (Optional[dict]): Environment variables.

    Returns:
        dict: config path data or empty dict

    """
    if not anatomy_data:
        from .context_tools import get_current_context_template_data
        anatomy_data = get_current_context_template_data()

    task_name = anatomy_data.get("task", {}).get("name")
    folder_path = anatomy_data.get("folder", {}).get("path")
    return get_imageio_config_preset(
        project_name,
        folder_path,
        task_name,
        host_name,
        anatomy=anatomy,
        project_settings=project_settings,
        template_data=anatomy_data,
        env=env,
    )
