import os
import sys
import inspect
import copy
import warnings
import xml.etree.ElementTree
from typing import Optional, Union, List

import ayon_api
import pyblish.util
import pyblish.plugin
import pyblish.api

from ayon_core.lib import (
    Logger,
    import_filepath,
    filter_profiles,
)
from ayon_core.settings import get_project_settings
from ayon_core.addon import AddonsManager
from ayon_core.pipeline import get_staging_dir_info
from ayon_core.pipeline.plugin_discover import DiscoverResult
from .constants import (
    DEFAULT_PUBLISH_TEMPLATE,
    DEFAULT_HERO_PUBLISH_TEMPLATE,
)


def get_template_name_profiles(
    project_name, project_settings=None, logger=None
):
    """Receive profiles for publish template keys.

    At least one of arguments must be passed.

    Args:
        project_name (str): Name of project where to look for templates.
        project_settings (Dict[str, Any]): Prepared project settings.
        logger (Optional[logging.Logger]): Logger object to be used instead
            of default logger.

    Returns:
        List[Dict[str, Any]]: Publish template profiles.
    """

    if not project_name and not project_settings:
        raise ValueError((
            "Both project name and project settings are missing."
            " At least one must be entered."
        ))

    if not project_settings:
        project_settings = get_project_settings(project_name)

    return copy.deepcopy(
        project_settings
        ["core"]
        ["tools"]
        ["publish"]
        ["template_name_profiles"]
    )


def get_hero_template_name_profiles(
    project_name, project_settings=None, logger=None
):
    """Receive profiles for hero publish template keys.

    At least one of arguments must be passed.

    Args:
        project_name (str): Name of project where to look for templates.
        project_settings (Dict[str, Any]): Prepared project settings.
        logger (Optional[logging.Logger]): Logger object to be used instead
            of default logger.

    Returns:
        List[Dict[str, Any]]: Publish template profiles.
    """

    if not project_name and not project_settings:
        raise ValueError((
            "Both project name and project settings are missing."
            " At least one must be entered."
        ))

    if not project_settings:
        project_settings = get_project_settings(project_name)

    return copy.deepcopy(
        project_settings
        ["core"]
        ["tools"]
        ["publish"]
        ["hero_template_name_profiles"]
    )


def get_publish_template_name(
    project_name,
    host_name,
    product_type,
    task_name,
    task_type,
    project_settings=None,
    hero=False,
    logger=None
):
    """Get template name which should be used for passed context.

    Publish templates are filtered by host name, family, task name and
    task type.

    Default template which is used at if profiles are not available or profile
    has empty value is defined by 'DEFAULT_PUBLISH_TEMPLATE' constant.

    Args:
        project_name (str): Name of project where to look for settings.
        host_name (str): Name of host integration.
        product_type (str): Product type for which should be found template.
        task_name (str): Task name on which is instance working.
        task_type (str): Task type on which is instance working.
        project_settings (Dict[str, Any]): Prepared project settings.
        hero (bool): Template is for hero version publishing.
        logger (logging.Logger): Custom logger used for 'filter_profiles'
            function.

    Returns:
        str: Template name which should be used for integration.
    """

    template = None
    filter_criteria = {
        "hosts": host_name,
        "product_types": product_type,
        "task_names": task_name,
        "task_types": task_type,
    }
    if hero:
        default_template = DEFAULT_HERO_PUBLISH_TEMPLATE
        profiles = get_hero_template_name_profiles(
            project_name, project_settings, logger
        )

    else:
        profiles = get_template_name_profiles(
            project_name, project_settings, logger
        )
        default_template = DEFAULT_PUBLISH_TEMPLATE

    profile = filter_profiles(profiles, filter_criteria, logger=logger)
    if profile:
        template = profile["template_name"]
    return template or default_template


class HelpContent:
    def __init__(self, title, description, detail=None):
        self.title = title
        self.description = description
        self.detail = detail


def load_help_content_from_filepath(filepath):
    """Load help content from xml file.
    Xml file may containt errors and warnings.
    """
    errors = {}
    warnings = {}
    output = {
        "errors": errors,
        "warnings": warnings
    }
    if not os.path.exists(filepath):
        return output
    tree = xml.etree.ElementTree.parse(filepath)
    root = tree.getroot()
    for child in root:
        child_id = child.attrib.get("id")
        if child_id is None:
            continue

        # Make sure ID is string
        child_id = str(child_id)

        title = child.find("title").text
        description = child.find("description").text
        detail_node = child.find("detail")
        detail = None
        if detail_node is not None:
            detail = detail_node.text
        if child.tag == "error":
            errors[child_id] = HelpContent(title, description, detail)
        elif child.tag == "warning":
            warnings[child_id] = HelpContent(title, description, detail)
    return output


def load_help_content_from_plugin(plugin):
    cls = plugin
    if not inspect.isclass(plugin):
        cls = plugin.__class__
    plugin_filepath = inspect.getfile(cls)
    plugin_dir = os.path.dirname(plugin_filepath)
    basename = os.path.splitext(os.path.basename(plugin_filepath))[0]
    filename = basename + ".xml"
    filepath = os.path.join(plugin_dir, "help", filename)
    return load_help_content_from_filepath(filepath)


def publish_plugins_discover(paths=None):
    """Find and return available pyblish plug-ins

    Overridden function from `pyblish` module to be able to collect
        crashed files and reason of their crash.

    Arguments:
        paths (list, optional): Paths to discover plug-ins from.
            If no paths are provided, all paths are searched.
    """

    # The only difference with `pyblish.api.discover`
    result = DiscoverResult(pyblish.api.Plugin)

    plugins = {}
    plugin_names = []

    allow_duplicates = pyblish.plugin.ALLOW_DUPLICATES
    log = pyblish.plugin.log

    # Include plug-ins from registered paths
    if not paths:
        paths = pyblish.plugin.plugin_paths()

    for path in paths:
        path = os.path.normpath(path)
        if not os.path.isdir(path):
            continue

        for fname in os.listdir(path):
            if fname.startswith("_"):
                continue

            abspath = os.path.join(path, fname)

            if not os.path.isfile(abspath):
                continue

            mod_name, mod_ext = os.path.splitext(fname)

            if mod_ext != ".py":
                continue

            try:
                module = import_filepath(abspath, mod_name)

                # Store reference to original module, to avoid
                # garbage collection from collecting it's global
                # imports, such as `import os`.
                sys.modules[abspath] = module

            except Exception as err:
                result.crashed_file_paths[abspath] = sys.exc_info()

                log.debug("Skipped: \"%s\" (%s)", mod_name, err)
                continue

            for plugin in pyblish.plugin.plugins_from_module(module):
                # Ignore base plugin classes
                # NOTE 'pyblish.api.discover' does not ignore them!
                if (
                    plugin is pyblish.api.Plugin
                    or plugin is pyblish.api.ContextPlugin
                    or plugin is pyblish.api.InstancePlugin
                ):
                    continue
                if not allow_duplicates and plugin.__name__ in plugin_names:
                    result.duplicated_plugins.append(plugin)
                    log.debug("Duplicate plug-in found: %s", plugin)
                    continue

                plugin_names.append(plugin.__name__)

                plugin.__module__ = module.__file__
                key = "{0}.{1}".format(plugin.__module__, plugin.__name__)
                plugins[key] = plugin

    # Include plug-ins from registration.
    # Directly registered plug-ins take precedence.
    for plugin in pyblish.plugin.registered_plugins():
        if not allow_duplicates and plugin.__name__ in plugin_names:
            result.duplicated_plugins.append(plugin)
            log.debug("Duplicate plug-in found: %s", plugin)
            continue

        plugin_names.append(plugin.__name__)

        plugins[plugin.__name__] = plugin

    plugins = list(plugins.values())
    pyblish.plugin.sort(plugins)  # In-place

    # In-place user-defined filter
    for filter_ in pyblish.plugin._registered_plugin_filters:
        filter_(plugins)

    result.plugins = plugins

    return result


def get_plugin_settings(plugin, project_settings, log, category=None):
    """Get plugin settings based on host name and plugin name.

    Note:
        Default implementation of automated settings is passing host name
            into 'category'.

    Args:
        plugin (pyblish.Plugin): Plugin where settings are applied.
        project_settings (dict[str, Any]): Project settings.
        log (logging.Logger): Logger to log messages.
        category (Optional[str]): Settings category key where to look
            for plugin settings.

    Returns:
        dict[str, Any]: Plugin settings {'attribute': 'value'}.
    """

    # Plugin can define settings category by class attribute
    # - it's impossible to set `settings_category` via settings because
    #     obviously settings are not applied before it.
    # - if `settings_category` is set the fallback category method is ignored
    settings_category = getattr(plugin, "settings_category", None)
    if settings_category:
        try:
            category_settings = project_settings[settings_category]
        except KeyError:
            log.warning((
                "Couldn't find settings category '{}' in project settings"
            ).format(settings_category))
            return {}

        try:
            return category_settings["publish"][plugin.__name__]
        except KeyError:
            return {}

    # Use project settings based on a category name
    if category:
        try:
            return (
                project_settings
                [category]
                ["publish"]
                [plugin.__name__]
            )
        except KeyError:
            pass

    # Settings category determined from path
    # - usually path is './<category>/plugins/publish/<plugin file>'
    # - category can be host name of addon name ('maya', 'deadline', ...)
    filepath = os.path.normpath(inspect.getsourcefile(plugin))

    split_path = filepath.rsplit(os.path.sep, 5)
    if len(split_path) < 4:
        log.debug((
            "Plugin path is too short to automatically"
            " extract settings category. {}"
        ).format(filepath))
        return {}

    category_from_file = split_path[-4]
    plugin_kind = split_path[-2]

    # TODO: change after all plugins are moved one level up
    if category_from_file == "ayon_core":
        category_from_file = "core"

    try:
        return (
            project_settings
            [category_from_file]
            [plugin_kind]
            [plugin.__name__]
        )
    except KeyError:
        pass
    return {}


def apply_plugin_settings_automatically(plugin, settings, logger=None):
    """Automatically apply plugin settings to a plugin object.

    Note:
        This function was created to be able to use it in custom overrides of
            'apply_settings' class method.

    Args:
        plugin (type[pyblish.api.Plugin]): Class of a plugin.
        settings (dict[str, Any]): Plugin specific settings.
        logger (Optional[logging.Logger]): Logger to log debug messages about
            applied settings values.
    """

    for option, value in settings.items():
        if logger:
            logger.debug("Plugin %s - Attr: %s -> %s",
                         plugin.__name__, option, value)
        setattr(plugin, option, value)


def filter_pyblish_plugins(plugins):
    """Pyblish plugin filter which applies AYON settings.

    Apply settings on discovered plugins. On plugin with implemented
    class method 'def apply_settings(cls, project_settings)'
    is called the method. Default behavior looks for plugin name and current
    host name to look for

    Args:
        plugins (List[pyblish.plugin.Plugin]): Discovered plugins on which
            are applied settings.
    """

    log = Logger.get_logger("filter_pyblish_plugins")

    # TODO: Don't use host from 'pyblish.api' but from defined host by us.
    #   - kept becau on farm is probably used host 'shell' which propably
    #       affect how settings are applied there
    host_name = pyblish.api.current_host()
    project_name = os.environ.get("AYON_PROJECT_NAME")

    project_settings = get_project_settings(project_name)

    # iterate over plugins
    for plugin in plugins[:]:
        # Apply settings to plugins

        apply_settings_func = getattr(plugin, "apply_settings", None)
        if apply_settings_func is not None:
            # Use classmethod 'apply_settings'
            # - can be used to target settings from custom settings place
            # - skip default behavior when successful
            try:
                plugin.apply_settings(project_settings)

            except Exception:
                log.warning(
                    (
                        "Failed to apply settings on plugin {}"
                    ).format(plugin.__name__),
                    exc_info=True
                )
        else:
            # Automated
            plugin_settins = get_plugin_settings(
                plugin, project_settings, log, host_name
            )
            apply_plugin_settings_automatically(plugin, plugin_settins, log)

        # Remove disabled plugins
        if getattr(plugin, "enabled", True) is False:
            plugins.remove(plugin)


def get_errored_instances_from_context(context, plugin=None):
    """Collect failed instances from pyblish context.

    Args:
        context (pyblish.api.Context): Publish context where we're looking
            for failed instances.
        plugin (pyblish.api.Plugin): If provided then only consider errors
            related to that plug-in.

    Returns:
        List[pyblish.lib.Instance]: Instances which failed during processing.
    """

    instances = list()
    for result in context.data["results"]:
        if result["instance"] is None:
            # When instance is None we are on the "context" result
            continue

        if plugin is not None and result.get("plugin") != plugin:
            continue

        if result["error"]:
            instances.append(result["instance"])

    return instances


def get_errored_plugins_from_context(context):
    """Collect failed plugins from pyblish context.

    Args:
        context (pyblish.api.Context): Publish context where we're looking
            for failed plugins.

    Returns:
        List[pyblish.api.Plugin]: Plugins which failed during processing.
    """

    plugins = list()
    results = context.data.get("results", [])
    for result in results:
        if result["success"] is True:
            continue
        plugins.append(result["plugin"])

    return plugins


def filter_instances_for_context_plugin(plugin, context):
    """Filter instances on context by context plugin filters.

    This is for cases when context plugin need similar filtering like instance
    plugin have, but for some reason must run on context or should find out
    if there is at least one instance with a family.

    Args:
        plugin (pyblish.api.Plugin): Plugin with filters.
        context (pyblish.api.Context): Pyblish context with insances.

    Returns:
        Iterator[pyblish.lib.Instance]: Iteration of valid instances.
    """

    instances = []
    plugin_families = set()
    all_families = False
    if plugin.families:
        instances = context
        plugin_families = set(plugin.families)
        all_families = "*" in plugin_families

    for instance in instances:
        # Ignore inactive instances
        if (
            not instance.data.get("publish", True)
            or not instance.data.get("active", True)
        ):
            continue

        family = instance.data.get("family")
        families = instance.data.get("families") or []
        if (
            all_families
            or (family and family in plugin_families)
            or any(f in plugin_families for f in families)
        ):
            yield instance


def context_plugin_should_run(plugin, context):
    """Return whether the ContextPlugin should run on the given context.

    This is a helper function to work around a bug pyblish-base#250
    Whenever a ContextPlugin sets specific families it will still trigger even
    when no instances are present that have those families.

    This actually checks it correctly and returns whether it should run.

    Args:
        plugin (pyblish.api.Plugin): Plugin with filters.
        context (pyblish.api.Context): Pyblish context with instances.

    Returns:
        bool: Context plugin should run based on valid instances.
    """

    for _ in filter_instances_for_context_plugin(plugin, context):
        return True
    return False


def get_publish_repre_path(instance, repre, only_published=False):
    """Get representation path that can be used for integration.

    When 'only_published' is set to true the validation of path is not
    relevant. In that case we just need what is set in 'published_path'
    as "reference". The reference is not used to get or upload the file but
    for reference where the file was published.

    Args:
        instance (pyblish.Instance): Processed instance object. Used
            for source of staging dir if representation does not have
            filled it.
        repre (dict): Representation on instance which could be and
            could not be integrated with main integrator.
        only_published (bool): Care only about published paths and
            ignore if filepath is not existing anymore.

    Returns:
        str: Path to representation file.
        None: Path is not filled or does not exists.
    """

    published_path = repre.get("published_path")
    if published_path:
        published_path = os.path.normpath(published_path)
        if os.path.exists(published_path):
            return published_path

    if only_published:
        return published_path

    comp_files = repre["files"]
    if isinstance(comp_files, (tuple, list, set)):
        filename = comp_files[0]
    else:
        filename = comp_files

    staging_dir = repre.get("stagingDir")
    if not staging_dir:
        staging_dir = get_instance_staging_dir(instance)

    # Expand the staging dir path in case it's been stored with the root
    # template syntax
    anatomy = instance.context.data["anatomy"]
    staging_dir = anatomy.fill_root(staging_dir)

    src_path = os.path.normpath(os.path.join(staging_dir, filename))
    if os.path.exists(src_path):
        return src_path
    return None


# deprecated: backward compatibility only (2024-09-12)
# TODO: remove in the future
def get_custom_staging_dir_info(
    project_name,
    host_name,
    product_type,
    task_name,
    task_type,
    product_name,
    project_settings=None,
    anatomy=None,
    log=None,
):
    from ayon_core.pipeline.staging_dir import get_staging_dir_config
    warnings.warn(
        (
            "Function 'get_custom_staging_dir_info' in"
            " 'ayon_core.pipeline.publish' is deprecated. Please use"
            " 'get_custom_staging_dir_info'"
            " in 'ayon_core.pipeline.stagingdir'."
        ),
        DeprecationWarning,
    )
    tr_data = get_staging_dir_config(
        project_name,
        task_type,
        task_name,
        product_type,
        product_name,
        host_name,
        project_settings=project_settings,
        anatomy=anatomy,
        log=log,
    )

    if not tr_data:
        return None, None

    return tr_data["template"], tr_data["persistence"]


def get_instance_staging_dir(instance):
    """Unified way how staging dir is stored and created on instances.

    First check if 'stagingDir' is already set in instance data.
    In case there already is new tempdir will not be created.

    Returns:
        str: Path to staging dir
    """
    staging_dir = instance.data.get("stagingDir")

    if staging_dir:
        return staging_dir

    anatomy_data = instance.data["anatomyData"]
    template_data = copy.deepcopy(anatomy_data)

    # context data based variables
    context = instance.context

    # add current file as workfile name into formatting data
    current_file = context.data.get("currentFile")
    if current_file:
        workfile = os.path.basename(current_file)
        workfile_name, _ = os.path.splitext(workfile)
        template_data["workfile_name"] = workfile_name

    staging_dir_info = get_staging_dir_info(
        context.data["projectEntity"],
        instance.data.get("folderEntity"),
        instance.data.get("taskEntity"),
        instance.data["productType"],
        instance.data["productName"],
        context.data["hostName"],
        anatomy=context.data["anatomy"],
        project_settings=context.data["project_settings"],
        template_data=template_data,
        always_return_path=True,
        username=context.data["user"],
    )

    staging_dir_path = staging_dir_info.directory

    # path might be already created by get_staging_dir_info
    os.makedirs(staging_dir_path, exist_ok=True)
    instance.data.update({
        "stagingDir": staging_dir_path,
        "stagingDir_persistent": staging_dir_info.is_persistent,
        "stagingDir_is_custom": staging_dir_info.is_custom
    })

    return staging_dir_path


def get_published_workfile_instance(context):
    """Find workfile instance in context"""
    for i in context:
        # test if there is instance of workfile waiting
        # to be published.
        if not i.data.get("publish", True):
            continue

        if not (
            i.data["productType"] == "workfile"
            # QUESTION Is check in 'families' valid?
            or "workfile" in i.data.get("families", [])
        ):
            continue

        return i


def replace_with_published_scene_path(instance, replace_in_path=True):
    """Switch work scene path for published scene.
    If rendering/exporting from published scenes is enabled, this will
    replace paths from working scene to published scene.
    This only works if publish contains workfile instance!
    Args:
        instance (pyblish.api.Instance): Pyblish instance.
        replace_in_path (bool): if True, it will try to find
            old scene name in path of expected files and replace it
            with name of published scene.
    Returns:
        str: Published scene path.
        None: if no published scene is found.
    Note:
        Published scene path is actually determined from project Anatomy
        as at the time this plugin is running scene can still not be
        published.
    """
    log = Logger.get_logger("published_workfile")
    workfile_instance = get_published_workfile_instance(instance.context)
    if workfile_instance is None:
        return

    # determine published path from Anatomy.
    template_data = copy.deepcopy(workfile_instance.data["anatomyData"])
    rep = workfile_instance.data["representations"][0]
    template_data["representation"] = rep.get("name")
    template_data["ext"] = rep.get("ext")
    template_data["comment"] = None

    anatomy = instance.context.data["anatomy"]
    template = anatomy.get_template_item("publish", "default", "path")
    template_filled = template.format_strict(template_data)
    file_path = os.path.normpath(template_filled)

    log.info("Using published scene for render {}".format(file_path))

    if not os.path.exists(file_path):
        log.error("published scene does not exist!")
        raise

    if not replace_in_path:
        return file_path

    # now we need to switch scene in expected files
    # because <scene> token will now point to published
    # scene file and that might differ from current one
    def _clean_name(path):
        return os.path.splitext(os.path.basename(path))[0]

    new_scene = _clean_name(file_path)
    orig_scene = _clean_name(instance.context.data["currentFile"])
    expected_files = instance.data.get("expectedFiles")

    if isinstance(expected_files[0], dict):
        # we have aovs and we need to iterate over them
        new_exp = {}
        for aov, files in expected_files[0].items():
            replaced_files = []
            for f in files:
                replaced_files.append(
                    str(f).replace(orig_scene, new_scene)
                )
            new_exp[aov] = replaced_files
        # [] might be too much here, TODO
        instance.data["expectedFiles"] = [new_exp]
    else:
        new_exp = []
        for f in expected_files:
            new_exp.append(
                str(f).replace(orig_scene, new_scene)
            )
        instance.data["expectedFiles"] = new_exp

    metadata_folder = instance.data.get("publishRenderMetadataFolder")
    if metadata_folder:
        metadata_folder = metadata_folder.replace(orig_scene,
                                                  new_scene)
        instance.data["publishRenderMetadataFolder"] = metadata_folder

    log.info("Scene name was switched {} -> {}".format(
        orig_scene, new_scene
    ))

    return file_path


def add_repre_files_for_cleanup(instance, repre):
    """ Explicitly mark repre files to be deleted.

    Should be used on intermediate files (eg. review, thumbnails) to be
    explicitly deleted.
    """
    files = repre["files"]
    staging_dir = repre.get("stagingDir")

    # first make sure representation level is not persistent
    if (
        not staging_dir
        or repre.get("stagingDir_persistent")
    ):
        return

    # then look into instance level if it's not persistent
    if instance.data.get("stagingDir_persistent"):
        return

    if isinstance(files, str):
        files = [files]

    for file_name in files:
        expected_file = os.path.join(staging_dir, file_name)
        instance.context.data["cleanupFullPaths"].append(expected_file)


def get_publish_instance_label(instance):
    """Try to get label from pyblish instance.

    First are used values in instance data under 'label' and 'name' keys. Then
    is used string conversion of instance object -> 'instance._name'.

    Todos:
        Maybe 'productName' key could be used too.

    Args:
        instance (pyblish.api.Instance): Pyblish instance.

    Returns:
        str: Instance label.
    """

    return (
        instance.data.get("label")
        or instance.data.get("name")
        or str(instance)
    )


def get_publish_instance_families(instance):
    """Get all families of the instance.

    Look for families under 'productType' and 'families' keys in instance data.
    Value of 'productType' is used as first family and then all other families
    in random order.

    Args:
        pyblish.api.Instance: Instance to get families from.

    Returns:
        list[str]: List of families.
    """

    family = instance.data.get("family")
    families = set(instance.data.get("families") or [])
    output = []
    if family:
        output.append(family)
        families.discard(family)
    output.extend(families)
    return output


def get_instance_expected_output_path(
        instance: pyblish.api.Instance,
        representation_name: str,
        ext: Union[str, None],
        version: Optional[str] = None
):
    """Return expected publish filepath for representation in instance

    This does not validate whether the instance has any representation by the
    given name, extension and/or version.

    Arguments:
        instance (pyblish.api.Instance): Publish instance
        representation_name (str): Representation name
        ext (Union[str, None]): Extension for the file.
            When None, the `ext` will be set to the representation name.
        version (Optional[int]): If provided, force it to format to this
            particular version.

    Returns:
        str: Resolved path

    """

    if ext is None:
        ext = representation_name
    if version is None:
        version = instance.data["version"]

    context = instance.context
    anatomy = context.data["anatomy"]

    template_data = copy.deepcopy(instance.data["anatomyData"])
    template_data.update({
        "ext": ext,
        "representation": representation_name,
        "variant": instance.data.get("variant"),
        "version": version
    })

    path_template_obj = anatomy.get_template_item("publish", "default")["path"]
    template_filled = path_template_obj.format_strict(template_data)
    return os.path.normpath(template_filled)


def main_cli_publish(
    path: str,
    targets: Optional[List[str]] = None,
    addons_manager: Optional[AddonsManager] = None,
):
    """Start headless publishing.

    Publish use json from passed path argument.

    Args:
        path (str): Path to JSON.
        targets (Optional[List[str]]): List of pyblish targets.
        addons_manager (Optional[AddonsManager]): Addons manager instance.

    Raises:
        RuntimeError: When there is no path to process or when executed with
            list of JSON paths.

    """
    from ayon_core.pipeline import (
        install_ayon_plugins,
        get_global_context,
    )

    # Register target and host
    if not isinstance(path, str):
        raise RuntimeError("Path to JSON must be a string.")

    # Fix older jobs
    for src_key, dst_key in (
        ("AVALON_PROJECT", "AYON_PROJECT_NAME"),
        ("AVALON_ASSET", "AYON_FOLDER_PATH"),
        ("AVALON_TASK", "AYON_TASK_NAME"),
        ("AVALON_WORKDIR", "AYON_WORKDIR"),
        ("AVALON_APP_NAME", "AYON_APP_NAME"),
        ("AVALON_APP", "AYON_HOST_NAME"),
    ):
        if src_key in os.environ and dst_key not in os.environ:
            os.environ[dst_key] = os.environ[src_key]
        # Remove old keys, so we're sure they're not used
        os.environ.pop(src_key, None)

    log = Logger.get_logger("CLI-publish")

    # Make public ayon api behave as other user
    # - this works only if public ayon api is using service user
    username = os.environ.get("AYON_USERNAME")
    if username:
        # NOTE: ayon-python-api does not have public api function to find
        #   out if is used service user. So we need to have try > except
        #   block.
        con = ayon_api.get_server_api_connection()
        try:
            con.set_default_service_username(username)
        except ValueError:
            pass

    install_ayon_plugins()

    if addons_manager is None:
        addons_manager = AddonsManager()

    # TODO validate if this has to happen
    # - it should happen during 'install_ayon_plugins'
    publish_paths = addons_manager.collect_plugin_paths()["publish"]
    for plugin_path in publish_paths:
        pyblish.api.register_plugin_path(plugin_path)

    applications_addon = addons_manager.get_enabled_addon("applications")
    if applications_addon is not None:
        context = get_global_context()
        env = applications_addon.get_farm_publish_environment_variables(
            context["project_name"],
            context["folder_path"],
            context["task_name"],
        )
        os.environ.update(env)

    pyblish.api.register_host("shell")

    if targets:
        for target in targets:
            print(f"setting target: {target}")
            pyblish.api.register_target(target)
    else:
        pyblish.api.register_target("farm")

    os.environ["AYON_PUBLISH_DATA"] = path
    os.environ["HEADLESS_PUBLISH"] = 'true'  # to use in app lib

    log.info("Running publish ...")

    plugins = pyblish.api.discover()
    print("Using plugins:")
    for plugin in plugins:
        print(plugin)

    # Error exit as soon as any error occurs.
    error_format = ("Failed {plugin.__name__}: "
                    "{error} -- {error.traceback}")

    for result in pyblish.util.publish_iter():
        if result["error"]:
            log.error(error_format.format(**result))
            # uninstall()
            sys.exit(1)

    log.info("Publish finished.")
