import os
import uuid
import platform
import logging
import inspect
import collections
import numbers
from typing import Optional, Union, Any

import ayon_api

from ayon_core.host import ILoadHost
from ayon_core.lib import (
    StringTemplate,
    TemplateUnsolved,
)
from ayon_core.pipeline import (
    Anatomy,
)

log = logging.getLogger(__name__)

ContainersFilterResult = collections.namedtuple(
    "ContainersFilterResult",
    ["latest", "outdated", "not_found", "invalid"]
)


class HeroVersionType(object):
    def __init__(self, version):
        assert isinstance(version, numbers.Integral), (
            "Version is not an integer. \"{}\" {}".format(
                version, str(type(version))
            )
        )
        self.version = version

    def __str__(self):
        return str(self.version)

    def __int__(self):
        return int(self.version)

    def __format__(self, format_spec):
        return self.version.__format__(format_spec)


class LoadError(Exception):
    """Known error that happened during loading.

    A message is shown to user (without traceback). Make sure an artist can
    understand the problem.
    """

    pass


class IncompatibleLoaderError(ValueError):
    """Error when Loader is incompatible with a representation."""
    pass


class InvalidRepresentationContext(ValueError):
    """Representation path can't be received using representation document."""
    pass


class LoaderSwitchNotImplementedError(NotImplementedError):
    """Error when `switch` is used with Loader that has no implementation."""
    pass


class LoaderNotFoundError(RuntimeError):
    """Error when Loader plugin for a loader name is not found."""
    pass


def get_repres_contexts(representation_ids, project_name=None):
    """Return parenthood context for representation.

    Args:
        representation_ids (list): The representation ids.
        project_name (Optional[str]): Project name.

    Returns:
        dict: The full representation context by representation id.
            keys are repre_id, value is dictionary with entities of
            folder, product, version and representation.
    """
    from ayon_core.pipeline import get_current_project_name

    if not representation_ids:
        return {}

    if not project_name:
        project_name = get_current_project_name()

    repre_entities = ayon_api.get_representations(
        project_name, representation_ids
    )

    return get_representation_contexts(project_name, repre_entities)


def get_product_contexts(product_ids, project_name=None):
    """Return parenthood context for product.

        Provides context on product granularity - less detail than
        'get_repre_contexts'.
    Args:
        product_ids (list): The product ids.
        project_name (Optional[str]): Project name.
    Returns:
        dict: The full representation context by representation id.
    """
    from ayon_core.pipeline import get_current_project_name

    contexts = {}
    if not product_ids:
        return contexts

    if not project_name:
        project_name = get_current_project_name()
    product_entities = ayon_api.get_products(
        project_name, product_ids=product_ids
    )
    product_entities_by_id = {}
    folder_ids = set()
    for product_entity in product_entities:
        product_entities_by_id[product_entity["id"]] = product_entity
        folder_ids.add(product_entity["folderId"])

    folder_entities_by_id = {
        folder_entity["id"]: folder_entity
        for folder_entity in ayon_api.get_folders(
            project_name, folder_ids=folder_ids
        )
    }

    project_entity = ayon_api.get_project(project_name)

    for product_id, product_entity in product_entities_by_id.items():
        folder_entity = folder_entities_by_id[product_entity["folderId"]]
        context = {
            "project": project_entity,
            "folder": folder_entity,
            "product": product_entity
        }
        contexts[product_id] = context

    return contexts


def get_representation_contexts(project_name, representation_entities):
    """Parenthood context for representations.

    Function fills ``None`` if any entity was not found or could
        not be queried.

    Args:
        project_name (str): Project name.
        representation_entities (Iterable[dict[str, Any]]): Representation
            entities.

    Returns:
        dict[str, dict[str, Any]]: The full representation context by
            representation id.

    """
    repre_entities_by_id = {
        repre_entity["id"]: repre_entity
        for repre_entity in representation_entities
    }

    if not repre_entities_by_id:
        return {}

    repre_ids = set(repre_entities_by_id)

    parents_by_repre_id = ayon_api.get_representations_parents(
        project_name, repre_ids
    )
    output = {}
    for repre_id in repre_ids:
        repre_entity = repre_entities_by_id[repre_id]
        (
            version_entity,
            product_entity,
            folder_entity,
            project_entity
        ) = parents_by_repre_id[repre_id]
        output[repre_id] = {
            "project": project_entity,
            "folder": folder_entity,
            "product": product_entity,
            "version": version_entity,
            "representation": repre_entity,
        }
    return output


def get_representation_contexts_by_ids(project_name, representation_ids):
    """Parenthood context for representations found by ids.

    Function fills ``None`` if any entity was not found or could
        not be queried.

    Args:
        project_name (str): Project name.
        representation_ids (Iterable[str]): Representation ids.

    Returns:
        dict[str, dict[str, Any]]: The full representation context by
            representation id.

    """
    repre_ids = set(representation_ids)
    if not repre_ids:
        return {}

    # Query representation entities by id
    repre_entities_by_id = {
        repre_entity["id"]: repre_entity
        for repre_entity in ayon_api.get_representations(
            project_name, repre_ids
        )
    }
    output = get_representation_contexts(
        project_name, repre_entities_by_id.values()
    )
    for repre_id in repre_ids:
        if repre_id not in output:
            output[repre_id] = {
                "project": None,
                "folder": None,
                "product": None,
                "version": None,
                "representation": None,
            }
    return output


def get_representation_context(project_name, representation):
    """Return parenthood context for representation.

    Args:
        project_name (str): Project name.
        representation (Union[dict[str, Any], str]): Representation entity
            or representation id.

    Returns:
        dict[str, dict[str, Any]]: The full representation context.

    Raises:
        ValueError: When representation is invalid or parents were not found.

    """
    if not representation:
        raise ValueError(
            "Invalid argument value {}".format(str(representation))
        )

    if isinstance(representation, dict):
        repre_entity = representation
        repre_id = repre_entity["id"]
        context = get_representation_contexts(
            project_name, [repre_entity]
        )[repre_id]
    else:
        repre_id = representation
        context = get_representation_contexts_by_ids(
            project_name, {repre_id}
        )[repre_id]

    missing_entities = []
    for key, value in context.items():
        if value is None:
            missing_entities.append(key)

    if missing_entities:
        raise ValueError(
            "Not able to receive representation parent types: {}".format(
                ", ".join(missing_entities)
            )
        )

    return context


def load_with_repre_context(
    Loader, repre_context, namespace=None, name=None, options=None, **kwargs
):

    # Ensure the Loader is compatible for the representation
    if not is_compatible_loader(Loader, repre_context):
        raise IncompatibleLoaderError(
            "Loader {} is incompatible with {}".format(
                Loader.__name__, repre_context["product"]["name"]
            )
        )

    # Ensure options is a dictionary when no explicit options provided
    if options is None:
        options = kwargs.get("data", dict())  # "data" for backward compat

    assert isinstance(options, dict), "Options must be a dictionary"

    # Fallback to product when name is None
    if name is None:
        name = repre_context["product"]["name"]

    log.info(
        "Running '%s' on '%s'" % (
            Loader.__name__, repre_context["folder"]["path"]
        )
    )

    loader = Loader()

    # Backwards compatibility: Originally the loader's __init__ required the
    # representation context to set `fname` attribute to the filename to load
    # Deprecated - to be removed in OpenPype 3.16.6 or 3.17.0.
    loader._fname = get_representation_path_from_context(repre_context)

    return loader.load(repre_context, name, namespace, options)


def load_with_product_context(
    Loader, product_context, namespace=None, name=None, options=None, **kwargs
):

    # Ensure options is a dictionary when no explicit options provided
    if options is None:
        options = kwargs.get("data", dict())  # "data" for backward compat

    assert isinstance(options, dict), "Options must be a dictionary"

    # Fallback to product when name is None
    if name is None:
        name = product_context["product"]["name"]

    log.info(
        "Running '%s' on '%s'" % (
            Loader.__name__, product_context["folder"]["path"]
        )
    )

    return Loader().load(product_context, name, namespace, options)


def load_with_product_contexts(
    Loader, product_contexts, namespace=None, name=None, options=None, **kwargs
):

    # Ensure options is a dictionary when no explicit options provided
    if options is None:
        options = kwargs.get("data", dict())  # "data" for backward compat

    assert isinstance(options, dict), "Options must be a dictionary"

    # Fallback to product when name is None
    joined_product_names = " | ".join(
        context["product"]["name"]
        for context in product_contexts
    )
    if name is None:
        name = joined_product_names

    log.info(
        "Running '{}' on '{}'".format(
            Loader.__name__, joined_product_names
        )
    )

    return Loader().load(product_contexts, name, namespace, options)


def load_container(
    Loader, representation, namespace=None, name=None, options=None, **kwargs
):
    """Use Loader to load a representation.

    Args:
        Loader (Loader): The loader class to trigger.
        representation (str or dict): The representation id
            or full representation as returned by the database.
        namespace (str, Optional): The namespace to assign. Defaults to None.
        name (str, Optional): The name to assign. Defaults to product name.
        options (dict, Optional): Additional options to pass on to the loader.

    Returns:
        The return of the `loader.load()` method.

    Raises:
        IncompatibleLoaderError: When the loader is not compatible with
            the representation.

    """
    from ayon_core.pipeline import get_current_project_name

    context = get_representation_context(
        get_current_project_name(), representation
    )
    return load_with_repre_context(
        Loader,
        context,
        namespace=namespace,
        name=name,
        options=options,
        **kwargs
    )


def get_loader_identifier(loader):
    """Loader identifier from loader plugin or object.

    Identifier should be stored to container for future management.
    """
    if not inspect.isclass(loader):
        loader = loader.__class__
    return loader.__name__


def get_loaders_by_name():
    from .plugins import discover_loader_plugins

    loaders_by_name = {}
    for loader in discover_loader_plugins():
        loader_name = loader.__name__
        if loader_name in loaders_by_name:
            raise KeyError(
                "Duplicated loader name {} !".format(loader_name)
            )
        loaders_by_name[loader_name] = loader
    return loaders_by_name


def _get_container_loader(container):
    """Return the Loader corresponding to the container"""
    from .plugins import discover_loader_plugins

    loader = container["loader"]
    for Plugin in discover_loader_plugins():
        # TODO: Ensure the loader is valid
        if get_loader_identifier(Plugin) == loader:
            return Plugin
    return None


def remove_container(container):
    """Remove a container"""

    Loader = _get_container_loader(container)
    if not Loader:
        raise LoaderNotFoundError(
            "Can't remove container because loader '{}' was not found."
            .format(container.get("loader"))
        )

    return Loader().remove(container)


def update_container(container, version=-1):
    """Update a container"""
    from ayon_core.pipeline import get_current_project_name

    # Compute the different version from 'representation'
    project_name = container.get("project_name", get_current_project_name())
    repre_id = container["representation"]
    if not _is_valid_representation_id(repre_id):
        raise ValueError(
            f"Got container with invalid representation id '{repre_id}'"
        )
    current_representation = ayon_api.get_representation_by_id(
        project_name, repre_id
    )

    assert current_representation is not None, "This is a bug"

    current_version_id = current_representation["versionId"]
    current_version = ayon_api.get_version_by_id(
        project_name, current_version_id, fields={"productId"}
    )
    if isinstance(version, HeroVersionType):
        new_version = ayon_api.get_hero_version_by_product_id(
            project_name, current_version["productId"]
        )
    elif version == -1:
        new_version = ayon_api.get_last_version_by_product_id(
            project_name, current_version["productId"]
        )

    else:
        new_version = ayon_api.get_version_by_name(
            project_name, version, current_version["productId"]
        )

    if new_version is None:
        raise ValueError("Failed to find matching version")

    product_entity = ayon_api.get_product_by_id(
        project_name, current_version["productId"]
    )
    folder_entity = ayon_api.get_folder_by_id(
        project_name, product_entity["folderId"]
    )

    # Run update on the Loader for this container
    Loader = _get_container_loader(container)
    if not Loader:
        raise LoaderNotFoundError(
            "Can't update container because loader '{}' was not found."
            .format(container.get("loader"))
        )

    repre_name = current_representation["name"]
    new_representation = ayon_api.get_representation_by_name(
        project_name, repre_name, new_version["id"]
    )
    if new_representation is None:
        # The representation name is not found in the new version.
        # Allow updating to a 'matching' representation if the loader
        # has defined compatible update conversions
        repre_name_aliases = Loader.get_representation_name_aliases(repre_name)
        if repre_name_aliases:
            representations = ayon_api.get_representations(
                project_name,
                representation_names=repre_name_aliases,
                version_ids=[new_version["id"]])
            representations_by_name = {
                repre["name"]: repre for repre in representations
            }
            for name in repre_name_aliases:
                if name in representations_by_name:
                    new_representation = representations_by_name[name]
                    break

        if new_representation is None:
            raise ValueError(
                "Representation '{}' wasn't found on requested version".format(
                    repre_name
                )
            )

    project_entity = ayon_api.get_project(project_name)
    context = {
        "project": project_entity,
        "folder": folder_entity,
        "product": product_entity,
        "version": new_version,
        "representation": new_representation,
    }
    path = get_representation_path_from_context(context)
    if not path or not os.path.exists(path):
        raise ValueError("Path {} doesn't exist".format(path))

    return Loader().update(container, context)


def switch_container(container, representation, loader_plugin=None):
    """Switch a container to representation

    Args:
        container (dict): container information
        representation (dict): representation entity

    Returns:
        function call
    """
    from ayon_core.pipeline import get_current_project_name

    # Get the Loader for this container
    if loader_plugin is None:
        loader_plugin = _get_container_loader(container)

    if not loader_plugin:
        raise LoaderNotFoundError(
            "Can't switch container because loader '{}' was not found."
            .format(container.get("loader"))
        )

    if not hasattr(loader_plugin, "switch"):
        # Backwards compatibility (classes without switch support
        # might be better to just have "switch" raise NotImplementedError
        # on the base class of Loader\
        raise LoaderSwitchNotImplementedError(
            "Loader {} does not support 'switch'".format(loader_plugin.label)
        )

    # Get the new representation to switch to
    project_name = container.get("project_name", get_current_project_name())

    context = get_representation_context(
        project_name, representation["id"]
    )
    if not is_compatible_loader(loader_plugin, context):
        raise IncompatibleLoaderError(
            "Loader {} is incompatible with {}".format(
                loader_plugin.__name__, context["product"]["name"]
            )
        )

    loader = loader_plugin(context)

    return loader.switch(container, context)


def _fix_representation_context_compatibility(repre_context):
    """Helper function to fix representation context compatibility.

    Args:
        repre_context (dict): Representation context.

    """
    # Auto-fix 'udim' being list of integers
    # - This is a legacy issue for old representation entities,
    #   added 24/07/10
    udim = repre_context.get("udim")
    if isinstance(udim, list):
        repre_context["udim"] = udim[0]


def get_representation_path_from_context(context):
    """Preparation wrapper using only context as a argument"""
    from ayon_core.pipeline import get_current_project_name

    representation = context["representation"]
    project_entity = context.get("project")
    root = None
    if (
        project_entity
        and project_entity["name"] != get_current_project_name()
    ):
        anatomy = Anatomy(project_entity["name"])
        root = anatomy.roots

    return get_representation_path(representation, root)


def get_representation_path_with_anatomy(repre_entity, anatomy):
    """Receive representation path using representation document and anatomy.

    Anatomy is used to replace 'root' key in representation file. Ideally
    should be used instead of 'get_representation_path' which is based on
    "current context".

    Future notes:
        We want also be able store resources into representation and I can
        imagine the result should also contain paths to possible resources.

    Args:
        repre_entity (Dict[str, Any]): Representation entity.
        anatomy (Anatomy): Project anatomy object.

    Returns:
        Union[None, TemplateResult]: None if path can't be received

    Raises:
        InvalidRepresentationContext: When representation data are probably
            invalid or not available.
    """

    try:
        template = repre_entity["attrib"]["template"]

    except KeyError:
        raise InvalidRepresentationContext((
            "Representation document does not"
            " contain template in data ('data.template')"
        ))

    try:
        context = repre_entity["context"]
        _fix_representation_context_compatibility(context)
        context["root"] = anatomy.roots

        path = StringTemplate.format_strict_template(template, context)

    except TemplateUnsolved as exc:
        raise InvalidRepresentationContext((
            "Couldn't resolve representation template with available data."
            " Reason: {}".format(str(exc))
        ))

    return path.normalized()


def get_representation_path(representation, root=None):
    """Get filename from representation document

    There are three ways of getting the path from representation which are
    tried in following sequence until successful.
    1. Get template from representation['data']['template'] and data from
       representation['context']. Then format template with the data.
    2. Get template from project['config'] and format it with default data set
    3. Get representation['data']['path'] and use it directly

    Args:
        representation(dict): representation document from the database

    Returns:
        str: fullpath of the representation

    """

    if root is None:
        from ayon_core.pipeline import registered_root

        root = registered_root()

    def path_from_representation():
        try:
            template = representation["attrib"]["template"]
        except KeyError:
            return None

        try:
            context = representation["context"]

            _fix_representation_context_compatibility(context)

            context["root"] = root
            path = StringTemplate.format_strict_template(
                template, context
            )
            # Force replacing backslashes with forward slashed if not on
            #   windows
            if platform.system().lower() != "windows":
                path = path.replace("\\", "/")
        except (TemplateUnsolved, KeyError):
            # Template references unavailable data
            return None

        if not path:
            return path

        normalized_path = os.path.normpath(path)
        if os.path.exists(normalized_path):
            return normalized_path
        return path

    def path_from_data():
        if "path" not in representation["attrib"]:
            return None

        path = representation["attrib"]["path"]
        # Force replacing backslashes with forward slashed if not on
        #   windows
        if platform.system().lower() != "windows":
            path = path.replace("\\", "/")

        if os.path.exists(path):
            return os.path.normpath(path)

        dir_path, file_name = os.path.split(path)
        if not os.path.exists(dir_path):
            return

        base_name, ext = os.path.splitext(file_name)
        file_name_items = None
        if "#" in base_name:
            file_name_items = [part for part in base_name.split("#") if part]
        elif "%" in base_name:
            file_name_items = base_name.split("%")

        if not file_name_items:
            return

        filename_start = file_name_items[0]

        for _file in os.listdir(dir_path):
            if _file.startswith(filename_start) and _file.endswith(ext):
                return os.path.normpath(path)

    return (
        path_from_representation() or path_from_data()
    )


def get_representation_path_by_names(
        project_name: str,
        folder_path: str,
        product_name: str,
        version_name: str,
        representation_name: str,
        anatomy: Optional[Anatomy] = None) -> Optional[str]:
    """Get (latest) filepath for representation for folder and product.

    See `get_representation_by_names` for more details.

    Returns:
        str: The representation path if the representation exists.

    """
    representation = get_representation_by_names(
        project_name,
        folder_path,
        product_name,
        version_name,
        representation_name
    )
    if not representation:
        return

    if not anatomy:
        anatomy = Anatomy(project_name)

    if representation:
        path = get_representation_path_with_anatomy(representation, anatomy)
        return str(path).replace("\\", "/")


def get_representation_by_names(
        project_name: str,
        folder_path: str,
        product_name: str,
        version_name: Union[int, str],
        representation_name: str,
) -> Optional[dict]:
    """Get representation entity for asset and subset.

    If version_name is "hero" then return the hero version
    If version_name is "latest" then return the latest version
    Otherwise use version_name as the exact integer version name.

    """

    if isinstance(folder_path, dict) and "name" in folder_path:
        # Allow explicitly passing asset document
        folder_entity = folder_path
    else:
        folder_entity = ayon_api.get_folder_by_path(
            project_name, folder_path, fields=["id"])
    if not folder_entity:
        return

    if isinstance(product_name, dict) and "name" in product_name:
        # Allow explicitly passing subset document
        product_entity = product_name
    else:
        product_entity = ayon_api.get_product_by_name(
            project_name,
            product_name,
            folder_id=folder_entity["id"],
            fields=["id"])
    if not product_entity:
        return

    if version_name == "hero":
        version_entity = ayon_api.get_hero_version_by_product_id(
            project_name, product_id=product_entity["id"])
    elif version_name == "latest":
        version_entity = ayon_api.get_last_version_by_product_id(
            project_name, product_id=product_entity["id"])
    else:
        version_entity = ayon_api.get_version_by_name(
            project_name, version_name, product_id=product_entity["id"])
    if not version_entity:
        return

    return ayon_api.get_representation_by_name(
        project_name, representation_name, version_id=version_entity["id"])


def is_compatible_loader(Loader, context):
    """Return whether a loader is compatible with a context.

    This checks the product type and the representation for the given
    Loader.

    Returns:
        bool
    """

    return Loader.is_compatible_loader(context)


def loaders_from_repre_context(loaders, repre_context):
    """Return compatible loaders for by representaiton's context."""

    return [
        loader
        for loader in loaders
        if is_compatible_loader(loader, repre_context)
    ]


def filter_repre_contexts_by_loader(repre_contexts, loader):
    """Filter representation contexts for loader.

    Args:
        repre_contexts (list[dict[str, Ant]]): Representation context.
        loader (LoaderPlugin): Loader plugin to filter contexts for.

    Returns:
        list[dict[str, Any]]: Filtered representation contexts.
    """

    return [
        repre_context
        for repre_context in repre_contexts
        if is_compatible_loader(loader, repre_context)
    ]


def loaders_from_representation(loaders, representation):
    """Return all compatible loaders for a representation."""
    from ayon_core.pipeline import get_current_project_name

    project_name = get_current_project_name()
    context = get_representation_context(
        project_name, representation
    )
    return loaders_from_repre_context(loaders, context)


def any_outdated_containers(host=None, project_name=None):
    """Check if there are any outdated containers in scene."""

    if get_outdated_containers(host, project_name):
        return True
    return False


def get_outdated_containers(host=None, project_name=None):
    """Collect outdated containers from host scene.

    Currently registered host and project in global session are used if
    arguments are not passed.

    Args:
        host (ModuleType): Host implementation with 'ls' function available.
        project_name (str): Name of project in which context we are.
    """
    from ayon_core.pipeline import registered_host, get_current_project_name

    if host is None:
        host = registered_host()

    if project_name is None:
        project_name = get_current_project_name()

    if isinstance(host, ILoadHost):
        containers = host.get_containers()
    else:
        containers = host.ls()
    return filter_containers(containers, project_name).outdated


def _is_valid_representation_id(repre_id: Any) -> bool:
    if not repre_id:
        return False
    try:
        uuid.UUID(repre_id)
    except (ValueError, TypeError, AttributeError):
        return False
    return True


def filter_containers(containers, project_name):
    """Filter containers and split them into 4 categories.

    Categories are 'latest', 'outdated', 'invalid' and 'not_found'.
    The 'lastest' containers are from last version, 'outdated' are not,
    'invalid' are invalid containers (invalid content) and 'not_found' has
    some missing entity in database.

    Args:
        containers (Iterable[dict]): List of containers referenced into scene.
        project_name (str): Name of project in which context shoud look for
            versions.

    Returns:
        ContainersFilterResult: Named tuple with 'latest', 'outdated',
            'invalid' and 'not_found' containers.
    """

    # Make sure containers is list that won't change
    containers = list(containers)

    outdated_containers = []
    uptodate_containers = []
    not_found_containers = []
    invalid_containers = []
    output = ContainersFilterResult(
        uptodate_containers,
        outdated_containers,
        not_found_containers,
        invalid_containers
    )
    # Query representation docs to get it's version ids
    repre_ids = {
        container["representation"]
        for container in containers
        if _is_valid_representation_id(container["representation"])
    }
    if not repre_ids:
        if containers:
            invalid_containers.extend(containers)
        return output

    repre_entities = ayon_api.get_representations(
        project_name,
        representation_ids=repre_ids,
        fields={"id", "versionId"}
    )
    # Store representations by stringified representation id
    repre_entities_by_id = {}
    repre_entities_by_version_id = collections.defaultdict(list)
    for repre_entity in repre_entities:
        repre_id = repre_entity["id"]
        version_id = repre_entity["versionId"]
        repre_entities_by_id[repre_id] = repre_entity
        repre_entities_by_version_id[version_id].append(repre_entity)

    # Query version docs to get it's product ids
    # - also query hero version to be able identify if representation
    #   belongs to existing version
    version_entities = ayon_api.get_versions(
        project_name,
        version_ids=repre_entities_by_version_id.keys(),
        hero=True,
        fields={"id", "productId", "version"}
    )
    verisons_by_id = {}
    versions_by_product_id = collections.defaultdict(list)
    hero_version_ids = set()
    for version_entity in version_entities:
        version_id = version_entity["id"]
        # Store versions by their ids
        verisons_by_id[version_id] = version_entity
        # There's no need to query products for hero versions
        #   - they are considered as latest?
        if version_entity["version"] < 0:
            hero_version_ids.add(version_id)
            continue
        product_id = version_entity["productId"]
        versions_by_product_id[product_id].append(version_entity)

    last_versions = ayon_api.get_last_versions(
        project_name,
        versions_by_product_id.keys(),
        fields={"id"}
    )
    # Figure out which versions are outdated
    outdated_version_ids = set()
    for product_id, last_version_entity in last_versions.items():
        for version_entity in versions_by_product_id[product_id]:
            version_id = version_entity["id"]
            if version_id in hero_version_ids:
                continue
            if version_id != last_version_entity["id"]:
                outdated_version_ids.add(version_id)

    # Based on all collected data figure out which containers are outdated
    #   - log out if there are missing representation or version documents
    for container in containers:
        container_name = container["objectName"]
        repre_id = container["representation"]
        if not _is_valid_representation_id(repre_id):
            invalid_containers.append(container)
            continue

        repre_entity = repre_entities_by_id.get(repre_id)
        if not repre_entity:
            log.debug((
                "Container '{}' has an invalid representation."
                " It is missing in the database."
            ).format(container_name))
            not_found_containers.append(container)
            continue

        version_id = repre_entity["versionId"]
        if version_id in outdated_version_ids:
            outdated_containers.append(container)

        elif version_id not in verisons_by_id:
            log.debug((
                "Representation on container '{}' has an invalid version."
                " It is missing in the database."
            ).format(container_name))
            not_found_containers.append(container)

        else:
            uptodate_containers.append(container)

    return output
