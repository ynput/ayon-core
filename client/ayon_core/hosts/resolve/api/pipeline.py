"""
Basic avalon integration
"""
import os
import contextlib
from collections import OrderedDict

from pyblish import api as pyblish

from ayon_core.lib import Logger
from ayon_core.pipeline import (
    schema,
    register_loader_plugin_path,
    register_creator_plugin_path,
    AVALON_CONTAINER_ID,
)
from ayon_core.host import (
    HostBase,
    IWorkfileHost,
    ILoadHost,
    IPublishHost
)

from . import lib
from .utils import get_resolve_module
from .workio import (
    open_file,
    save_file,
    file_extensions,
    has_unsaved_changes,
    work_root,
    current_file
)

log = Logger.get_logger(__name__)

HOST_DIR = os.path.dirname(os.path.abspath(os.path.dirname(__file__)))
PLUGINS_DIR = os.path.join(HOST_DIR, "plugins")
PUBLISH_PATH = os.path.join(PLUGINS_DIR, "publish")
LOAD_PATH = os.path.join(PLUGINS_DIR, "load")
CREATE_PATH = os.path.join(PLUGINS_DIR, "create")

AVALON_CONTAINERS = ":AVALON_CONTAINERS"


class ResolveHost(HostBase, IWorkfileHost, ILoadHost, IPublishHost):
    name = "resolve"

    def install(self):
        """Install resolve-specific functionality of avalon-core.

        This is where you install menus and register families, data
        and loaders into resolve.

        It is called automatically when installing via `api.install(resolve)`.

        See the Maya equivalent for inspiration on how to implement this.

        """

        log.info("ayon_core.hosts.resolve installed")

        pyblish.register_host(self.name)
        pyblish.register_plugin_path(PUBLISH_PATH)
        print("Registering DaVinci Resolve plug-ins..")

        register_loader_plugin_path(LOAD_PATH)
        register_creator_plugin_path(CREATE_PATH)

        # register callback for switching publishable
        pyblish.register_callback("instanceToggled",
                                  on_pyblish_instance_toggled)

        get_resolve_module()

    def open_workfile(self, filepath):
        return open_file(filepath)

    def save_workfile(self, filepath=None):
        return save_file(filepath)

    def work_root(self, session):
        return work_root(session)

    def get_current_workfile(self):
        return current_file()

    def workfile_has_unsaved_changes(self):
        return has_unsaved_changes()

    def get_workfile_extensions(self):
        return file_extensions()

    def get_containers(self):
        return ls()

    def get_context_data(self):
        return {}

    def update_context_data(self, data, changes):
        pass


def containerise(timeline_item,
                 name,
                 namespace,
                 context,
                 loader=None,
                 data=None):
    """Bundle Resolve's object into an assembly and imprint it with metadata

    Containerization enables a tracking of version, author and origin
    for loaded assets.

    Arguments:
        timeline_item (resolve.TimelineItem): The object to containerise
        name (str): Name of resulting assembly
        namespace (str): Namespace under which to host container
        context (dict): Asset information
        loader (str, optional): Name of node used to produce this container.

    Returns:
        timeline_item (resolve.TimelineItem): containerized object

    """

    data_imprint = OrderedDict({
        "schema": "openpype:container-2.0",
        "id": AVALON_CONTAINER_ID,
        "name": str(name),
        "namespace": str(namespace),
        "loader": str(loader),
        "representation": str(context["representation"]["_id"]),
    })

    if data:
        data_imprint.update(data)

    lib.set_timeline_item_ayon_tag(timeline_item, data_imprint)

    return timeline_item


def ls():
    """List available containers.

    This function is used by the Container Manager in Nuke. You'll
    need to implement a for-loop that then *yields* one Container at
    a time.

    See the `container.json` schema for details on how it should look,
    and the Maya equivalent, which is in `avalon.maya.pipeline`
    """

    # get all track items from current timeline
    all_timeline_items = lib.get_current_timeline_items(filter=False)

    for timeline_item_data in all_timeline_items:
        timeline_item = timeline_item_data["clip"]["item"]
        container = parse_container(timeline_item)
        if container:
            yield container


def parse_container(timeline_item, validate=True):
    """Return container data from timeline_item's marker data.

    Args:
        timeline_item (resolve.TimelineItem): A containerized track item.
        validate (bool)[optional]: validating with avalon scheme

    Returns:
        dict: The container schema data for input containerized track item.

    """
    # convert tag metadata to normal keys names
    data = lib.get_timeline_item_ayon_tag(timeline_item)

    if validate and data and data.get("schema"):
        schema.validate(data)

    if not isinstance(data, dict):
        return

    # If not all required data return the empty container
    required = ['schema', 'id', 'name',
                'namespace', 'loader', 'representation']

    if not all(key in data for key in required):
        return

    container = {key: data[key] for key in required}

    container["objectName"] = timeline_item.GetName()

    # Store reference to the node object
    container["_timeline_item"] = timeline_item

    return container


def update_container(timeline_item, data=None):
    """Update container data to input timeline_item's ayon marker data.

    Args:
        timeline_item (resolve.TimelineItem): A containerized track item.
        data (dict)[optional]: dictionary with data to be updated

    Returns:
        bool: True if container was updated correctly

    """
    data = data or {}

    container = lib.get_timeline_item_ayon_tag(timeline_item)

    for _key, _value in container.items():
        try:
            container[_key] = data[_key]
        except KeyError:
            pass

    log.info("Updating container: `{}`".format(timeline_item))
    return bool(lib.set_timeline_item_ayon_tag(timeline_item, container))


@contextlib.contextmanager
def maintained_selection():
    """Maintain selection during context

    Example:
        >>> with maintained_selection():
        ...     node['selected'].setValue(True)
        >>> print(node['selected'].value())
        False
    """
    try:
        # do the operation
        yield
    finally:
        pass


def reset_selection():
    """Deselect all selected nodes
    """
    pass


def on_pyblish_instance_toggled(instance, old_value, new_value):
    """Toggle node passthrough states on instance toggles."""

    log.info("instance toggle: {}, old_value: {}, new_value:{} ".format(
        instance, old_value, new_value))

    from ayon_core.hosts.resolve.api import (
        set_publish_attribute
    )

    # Whether instances should be passthrough based on new value
    timeline_item = instance.data["item"]
    set_publish_attribute(timeline_item, new_value)
