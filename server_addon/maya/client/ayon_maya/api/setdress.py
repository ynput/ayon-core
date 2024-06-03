import logging
import json
import os

import contextlib
import copy

import six
import ayon_api

from maya import cmds

from ayon_core.pipeline import (
    schema,
    discover_loader_plugins,
    loaders_from_representation,
    load_container,
    update_container,
    remove_container,
    get_representation_path,
    get_current_project_name,
)
from ayon_maya.api.lib import (
    matrix_equals,
    unique_namespace,
    get_container_transforms,
    DEFAULT_MATRIX
)

log = logging.getLogger("PackageLoader")


def to_namespace(node, namespace):
    """Return node name as if it's inside the namespace.

    Args:
        node (str): Node name
        namespace (str): Namespace

    Returns:
        str: The node in the namespace.

    """
    namespace_prefix = "|{}:".format(namespace)
    node = namespace_prefix.join(node.split("|"))
    return node


@contextlib.contextmanager
def namespaced(namespace, new=True):
    """Work inside namespace during context

    Args:
        new (bool): When enabled this will rename the namespace to a unique
            namespace if the input namespace already exists.

    Yields:
        str: The namespace that is used during the context

    """
    original = cmds.namespaceInfo(cur=True)
    if new:
        namespace = unique_namespace(namespace)
        cmds.namespace(add=namespace)

    try:
        cmds.namespace(set=namespace)
        yield namespace
    finally:
        cmds.namespace(set=original)


@contextlib.contextmanager
def unlocked(nodes):

    # Get node state by Maya's uuid
    nodes = cmds.ls(nodes, long=True)
    uuids = cmds.ls(nodes, uuid=True)
    states = cmds.lockNode(nodes, query=True, lock=True)
    states = {uuid: state for uuid, state in zip(uuids, states)}
    originals = {uuid: node for uuid, node in zip(uuids, nodes)}

    try:
        cmds.lockNode(nodes, lock=False)
        yield
    finally:
        # Reapply original states
        _iteritems = getattr(states, "iteritems", states.items)
        for uuid, state in _iteritems():
            nodes_from_id = cmds.ls(uuid, long=True)
            if nodes_from_id:
                node = nodes_from_id[0]
            else:
                log.debug("Falling back to node name: %s", node)
                node = originals[uuid]
                if not cmds.objExists(node):
                    log.warning("Unable to find: %s", node)
                    continue
            cmds.lockNode(node, lock=state)


def load_package(filepath, name, namespace=None):
    """Load a package that was gathered elsewhere.

    A package is a group of published instances, possibly with additional data
    in a hierarchy.

    """

    if namespace is None:
        # Define a unique namespace for the package
        namespace = os.path.basename(filepath).split(".")[0]
        unique_namespace(namespace)
    assert isinstance(namespace, six.string_types)

    # Load the setdress package data
    with open(filepath, "r") as fp:
        data = json.load(fp)

    # Load the setdress alembic hierarchy
    #   We import this into the namespace in which we'll load the package's
    #   instances into afterwards.
    alembic = filepath.replace(".json", ".abc")
    hierarchy = cmds.file(alembic,
                          reference=True,
                          namespace=namespace,
                          returnNewNodes=True,
                          groupReference=True,
                          groupName="{}:{}".format(namespace, name),
                          typ="Alembic")

    # Get the top root node (the reference group)
    root = "{}:{}".format(namespace, name)

    containers = []
    all_loaders = discover_loader_plugins()
    for representation_id, instances in data.items():

        # Find the compatible loaders
        loaders = loaders_from_representation(
            all_loaders, representation_id
        )

        for instance in instances:
            container = _add(instance=instance,
                             representation_id=representation_id,
                             loaders=loaders,
                             namespace=namespace,
                             root=root)
            containers.append(container)

    # TODO: Do we want to cripple? Or do we want to add a 'parent' parameter?
    # Cripple the original AYON containers so they don't show up in the
    # manager
    # for container in containers:
    #     cmds.setAttr("%s.id" % container,
    #                  "setdress.container",
    #                  type="string")

    # TODO: Lock all loaded nodes
    #   This is to ensure the hierarchy remains unaltered by the artists
    # for node in nodes:
    #      cmds.lockNode(node, lock=True)

    return containers + hierarchy


def _add(instance, representation_id, loaders, namespace, root="|"):
    """Add an item from the package

    Args:
        instance (dict):
        representation_id (str):
        loaders (list):
        namespace (str):

    Returns:
        str: The created AYON container.

    """

    # Process within the namespace
    with namespaced(namespace, new=False) as namespace:

        # Get the used loader
        Loader = next((x for x in loaders if
                       x.__name__ == instance['loader']),
                      None)

        if Loader is None:
            log.warning("Loader is missing: %s. Skipping %s",
                        instance['loader'], instance)
            raise RuntimeError("Loader is missing.")

        container = load_container(
            Loader,
            representation_id,
            namespace=instance['namespace']
        )

        # Get the root from the loaded container
        loaded_root = get_container_transforms({"objectName": container},
                                               root=True)

        # Apply matrix to root node (if any matrix edits)
        matrix = instance.get("matrix", None)
        if matrix:
            cmds.xform(loaded_root, objectSpace=True, matrix=matrix)

        # Parent into the setdress hierarchy
        # Namespace is missing from parent node(s), add namespace
        # manually
        parent = root + to_namespace(instance["parent"], namespace)
        cmds.parent(loaded_root, parent, relative=True)

        return container


# Store root nodes based on representation and namespace
def _instances_by_namespace(data):
    """Rebuild instance data so we can look it up by namespace.

    Note that the `representation` is added into the instance's
    data with a `representation` key.

    Args:
        data (dict): scene build data

    Returns:
        dict

    """
    result = {}
    # Add new assets
    for representation_id, instances in data.items():

        # Ensure we leave the source data unaltered
        instances = copy.deepcopy(instances)
        for instance in instances:
            instance['representation'] = representation_id
            result[instance['namespace']] = instance

    return result


def get_contained_containers(container):
    """Get the AYON containers in this container

    Args:
        container (dict): The container dict.

    Returns:
        list: A list of member container dictionaries.

    """

    from .pipeline import parse_container

    # Get AYON containers in this package setdress container
    containers = []
    members = cmds.sets(container['objectName'], query=True)
    for node in cmds.ls(members, type="objectSet"):
        try:
            member_container = parse_container(node)
            containers.append(member_container)
        except schema.ValidationError:
            pass

    return containers


def update_package_version(container, version):
    """
    Update package by version number

    Args:
        container (dict): container data of the container node
        version (int): the new version number of the package

    Returns:
        None

    """

    # Versioning (from `core.maya.pipeline`)
    project_name = get_current_project_name()
    repre_id = container["representation"]
    current_representation = ayon_api.get_representation_by_id(
        project_name, repre_id
    )

    assert current_representation is not None, "This is a bug"

    (
        version_entity,
        product_entity,
        folder_entity,
        project_entity
    ) = ayon_api.get_representation_parents(project_name, repre_id)

    if version == -1:
        new_version = ayon_api.get_last_version_by_product_id(
            project_name, product_entity["id"]
        )
    else:
        new_version = ayon_api.get_version_by_name(
            project_name, version, product_entity["id"]
        )

    if new_version is None:
        raise ValueError("Version not found: {}".format(version))

    # Get the new representation (new file)
    new_representation = ayon_api.get_representation_by_name(
        project_name, current_representation["name"], new_version["id"]
    )
    # TODO there is 'get_representation_context' to get the context which
    #   could be possible to use here
    new_context = {
        "project": project_entity,
        "folder": folder_entity,
        "product": product_entity,
        "version": version_entity,
        "representation": new_representation,
    }
    update_package(container, new_context)


def update_package(set_container, context):
    """Update any matrix changes in the scene based on the new data

    Args:
        set_container (dict): container data from `ls()`
        context (dict): the representation document from the database

    Returns:
        None

    """

    # Load the original package data
    project_name = context["project"]["name"]
    repre_entity = context["representation"]
    current_representation = ayon_api.get_representation_by_id(
        project_name, set_container["representation"]
    )

    current_file = get_representation_path(current_representation)
    assert current_file.endswith(".json")
    with open(current_file, "r") as fp:
        current_data = json.load(fp)

    # Load the new package data
    new_file = get_representation_path(repre_entity)
    assert new_file.endswith(".json")
    with open(new_file, "r") as fp:
        new_data = json.load(fp)

    # Update scene content
    containers = get_contained_containers(set_container)
    update_scene(set_container, containers, current_data, new_data, new_file)

    # TODO: This should be handled by the pipeline itself
    cmds.setAttr(set_container['objectName'] + ".representation",
                 context["representation"]["id"], type="string")


def update_scene(set_container, containers, current_data, new_data, new_file):
    """Updates the hierarchy, assets and their matrix

    Updates the following within the scene:
        * Setdress hierarchy alembic
        * Matrix
        * Parenting
        * Representations

    It removes any assets which are not present in the new build data

    Args:
        set_container (dict): the setdress container of the scene
        containers (list): the list of containers under the setdress container
        current_data (dict): the current build data of the setdress
        new_data (dict): the new build data of the setdres

    Returns:
        processed_containers (list): all new and updated containers

    """

    set_namespace = set_container['namespace']
    project_name = get_current_project_name()

    # Update the setdress hierarchy alembic
    set_root = get_container_transforms(set_container, root=True)
    set_hierarchy_root = cmds.listRelatives(set_root, fullPath=True)[0]
    set_hierarchy_reference = cmds.referenceQuery(set_hierarchy_root,
                                                  referenceNode=True)
    new_alembic = new_file.replace(".json", ".abc")
    assert os.path.exists(new_alembic), "%s does not exist." % new_alembic
    with unlocked(cmds.listRelatives(set_root, ad=True, fullPath=True)):
        cmds.file(new_alembic,
                  loadReference=set_hierarchy_reference,
                  type="Alembic")

    identity = DEFAULT_MATRIX[:]

    processed_namespaces = set()
    processed_containers = list()

    new_lookup = _instances_by_namespace(new_data)
    old_lookup = _instances_by_namespace(current_data)
    repre_ids = set()
    containers_for_repre_compare = []
    for container in containers:
        container_ns = container['namespace']

        # Consider it processed here, even it it fails we want to store that
        # the namespace was already available.
        processed_namespaces.add(container_ns)
        processed_containers.append(container['objectName'])

        if container_ns not in new_lookup:
            # Remove this container because it's not in the new data
            log.warning("Removing content: %s", container_ns)
            remove_container(container)
            continue

        root = get_container_transforms(container, root=True)
        if not root:
            log.error("Can't find root for %s", container['objectName'])
            continue

        old_instance = old_lookup.get(container_ns, {})
        new_instance = new_lookup[container_ns]

        # Update the matrix
        # check matrix against old_data matrix to find local overrides
        current_matrix = cmds.xform(root,
                                    query=True,
                                    matrix=True,
                                    objectSpace=True)

        original_matrix = old_instance.get("matrix", identity)
        has_matrix_override = not matrix_equals(current_matrix,
                                                original_matrix)

        if has_matrix_override:
            log.warning("Matrix override preserved on %s", container_ns)
        else:
            new_matrix = new_instance.get("matrix", identity)
            cmds.xform(root, matrix=new_matrix, objectSpace=True)

        # Update the parenting
        if old_instance.get("parent", None) != new_instance["parent"]:

            parent = to_namespace(new_instance['parent'], set_namespace)
            if not cmds.objExists(parent):
                log.error("Can't find parent %s", parent)
                continue

            # Set the new parent
            cmds.lockNode(root, lock=False)
            root = cmds.parent(root, parent, relative=True)
            cmds.lockNode(root, lock=True)

        # Update the representation
        representation_current = container['representation']
        representation_old = old_instance['representation']
        representation_new = new_instance['representation']
        has_representation_override = (representation_current !=
                                       representation_old)

        if representation_new == representation_current:
            continue

        if has_representation_override:
            log.warning("Your scene had local representation "
                        "overrides within the set. New "
                        "representations not loaded for %s.",
                        container_ns)
            continue

        # We check it against the current 'loader' in the scene instead
        # of the original data of the package that was loaded because
        # an Artist might have made scene local overrides
        if new_instance['loader'] != container['loader']:
            log.warning("Loader is switched - local edits will be "
                        "lost. Removing: %s",
                        container_ns)

            # Remove this from the "has been processed" list so it's
            # considered as new element and added afterwards.
            processed_containers.pop()
            processed_namespaces.remove(container_ns)
            remove_container(container)
            continue

        # Check whether the conversion can be done by the Loader.
        # They *must* use the same folder, product and Loader for
        # `update_container` to make sense.
        repre_ids.add(representation_current)
        repre_ids.add(representation_new)

        containers_for_repre_compare.append(
            (container, representation_current, representation_new)
        )

    repre_entities_by_id = {
        repre_entity["id"]: repre_entity
        for repre_entity in ayon_api.get_representations(
            project_name, representation_ids=repre_ids
        )
    }
    repre_parents_by_id = ayon_api.get_representations_parents(
        project_name, repre_ids
    )
    for (
        container,
        repre_current_id,
        repre_new_id
    ) in containers_for_repre_compare:
        current_repre = repre_entities_by_id[repre_current_id]
        current_parents = repre_parents_by_id[repre_current_id]
        new_repre = repre_entities_by_id[repre_new_id]
        new_parents = repre_parents_by_id[repre_new_id]

        is_valid = compare_representations(
            current_repre, current_parents, new_repre, new_parents
        )
        if not is_valid:
            log.error("Skipping: %s. See log for details.",
                      container["namespace"])
            continue

        new_version = new_parents.version["version"]
        update_container(container, version=new_version)

    # Add new assets
    all_loaders = discover_loader_plugins()
    for representation_id, instances in new_data.items():

        # Find the compatible loaders
        loaders = loaders_from_representation(
            all_loaders, representation_id
        )
        for instance in instances:

            # Already processed in update functionality
            if instance['namespace'] in processed_namespaces:
                continue

            container = _add(instance=instance,
                             representation_id=representation_id,
                             loaders=loaders,
                             namespace=set_container['namespace'],
                             root=set_root)

            # Add to the setdress container
            cmds.sets(container,
                      addElement=set_container['objectName'])

            processed_containers.append(container)

    return processed_containers


def compare_representations(
    current_repre, current_parents, new_repre, new_parents
):
    """Check if the old representation given can be updated

    Due to limitations of the `update_container` function we cannot allow
    differences in the following data:

    * Representation name (extension)
    * Folder id
    * Product id

    If any of those data values differs, the function will raise an
    RuntimeError

    Args:
        current_repre (dict[str, Any]): Current representation entity.
        current_parents (RepresentationParents): Current
            representation parents.
        new_repre (dict[str, Any]): New representation entity.
        new_parents (RepresentationParents): New representation parents.

    Returns:
        bool: False if the representation is not invalid else True

    """
    if current_repre["name"] != new_repre["name"]:
        log.error("Cannot switch extensions")
        return False

    # TODO add better validation e.g. based on parent ids
    if current_parents.folder["id"] != new_parents.folder["id"]:
        log.error("Changing folders between updates is not supported.")
        return False

    if current_parents.product["id"] != new_parents.product["id"]:
        log.error("Changing products between updates is not supported.")
        return False

    return True
