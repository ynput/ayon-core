"""Helper functions for load HDA"""

import os
import contextlib
import uuid
from typing import List

import ayon_api
from ayon_api import (
    get_project,
    get_representation_by_id,
    get_versions,
    get_folder_by_path,
    get_product_by_name,
    get_version_by_name,
    get_representation_by_name
)
from ayon_core.pipeline.load import (
    get_representation_context,
    get_representation_path_from_context
)
from ayon_core.pipeline.context_tools import (
    get_current_project_name,
    get_current_folder_path
)
from ayon_core.tools.utils import SimpleFoldersWidget
from ayon_core.style import load_stylesheet

from ayon_houdini.api import lib

from qtpy import QtCore, QtWidgets
import hou


def is_valid_uuid(value) -> bool:
    """Return whether value is a valid UUID"""
    try:
        uuid.UUID(value)
    except ValueError:
        return False
    return True


@contextlib.contextmanager
def _unlocked_parm(parm):
    """Unlock parm during context; will always lock after"""
    try:
        parm.lock(False)
        yield
    finally:
        parm.lock(True)


def get_available_versions(node):
    """Return the versions list for node.

    The versions are sorted with the latest version first and oldest lower
    version last.

    Args:
        node (hou.Node): Node to query selected products' versions for.

    Returns:
        list[int]: Version numbers for the product
    """

    project_name = node.evalParm("project_name") or get_current_project_name()
    folder_path = node.evalParm("folder_path")
    product_name = node.evalParm("product_name")

    if not all([
        project_name, folder_path, product_name
    ]):
        return []

    folder_entity = get_folder_by_path(
        project_name,
        folder_path,
        fields={"id"})
    if not folder_entity:
        return []
    product_entity = get_product_by_name(
        project_name,
        product_name=product_name,
        folder_id=folder_entity["id"],
        fields={"id"})
    if not product_entity:
        return []

    # TODO: Support hero versions
    versions = get_versions(
        project_name,
        product_ids={product_entity["id"]},
        fields={"version"},
        hero=False)
    version_names = [version["version"] for version in versions]
    version_names.reverse()
    return version_names


def update_info(node, context):
    """Update project, folder, product, version, representation name parms.

     Arguments:
         node (hou.Node): Node to update
         context (dict): Context of representation

     """
    # TODO: Avoid 'duplicate' taking over the expression if originally
    #       it was $OS and by duplicating, e.g. the `folder` does not exist
    #       anymore since it is now `hero1` instead of `hero`
    # TODO: Support hero versions
    version = str(context["version"]["version"])

    # We only set the values if the value does not match the currently
    # evaluated result of the other parms, so that if the project name
    # value was dynamically set by the user with an expression or alike
    # then if it still matches the value of the current representation id
    # we preserve it. In essence, only update the value if the current
    # *evaluated* value of the parm differs.
    parms = {
        "project_name": context["project"]["name"],
        "folder_path": context["folder"]["path"],
        "product_name": context["product"]["name"],
        "version": version,
        "representation_name": context["representation"]["name"],
    }
    parms = {key: value for key, value in parms.items()
             if node.evalParm(key) != value}
    parms["load_message"] = ""  # clear any warnings/errors

    # Note that these never trigger any parm callbacks since we do not
    # trigger the `parm.pressButton` and programmatically setting values
    # in Houdini does not trigger callbacks automatically
    node.setParms(parms)


def _get_thumbnail(project_name: str, version_id: str, thumbnail_dir: str):
    folder = hou.text.expandString(thumbnail_dir)
    path = os.path.join(folder, "{}_thumbnail.jpg".format(version_id))
    expanded_path = hou.text.expandString(path)
    if os.path.isfile(expanded_path):
        return path

    # Try and create a thumbnail cache file
    data = ayon_api.get_thumbnail(project_name,
                                  entity_type="version",
                                  entity_id=version_id)
    if data:
        thumbnail_dir_expanded = hou.text.expandString(thumbnail_dir)
        os.makedirs(thumbnail_dir_expanded, exist_ok=True)
        with open(expanded_path, "wb") as f:
            f.write(data.content)
        return path


def set_representation(node, representation_id: str):
    file_parm = node.parm("file")
    if not representation_id:
        # Clear filepath and thumbnail
        with _unlocked_parm(file_parm):
            file_parm.set("")
        set_node_thumbnail(node, None)
        return

    project_name = (
        node.evalParm("project_name")
        or get_current_project_name()
    )

    # Ignore invalid representation ids silently
    # TODO remove - added for backwards compatibility with OpenPype scenes
    if not is_valid_uuid(representation_id):
        return

    repre_entity = get_representation_by_id(project_name, representation_id)
    if not repre_entity:
        return

    context = get_representation_context(project_name, repre_entity)
    update_info(node, context)
    path = get_representation_path_from_context(context)
    # Load fails on UNC paths with backslashes and also
    # fails to resolve @sourcename var with backslashed
    # paths correctly. So we force forward slashes
    path = path.replace("\\", "/")
    with _unlocked_parm(file_parm):
        file_parm.set(path)

    if node.evalParm("show_thumbnail"):
        # Update thumbnail
        # TODO: Cache thumbnail path as well
        version_id = repre_entity["versionId"]
        thumbnail_dir = node.evalParm("thumbnail_cache_dir")
        thumbnail_path = _get_thumbnail(
            project_name, version_id, thumbnail_dir
        )
        set_node_thumbnail(node, thumbnail_path)


def set_node_thumbnail(node, thumbnail: str):
    """Update node thumbnail to thumbnail"""
    if thumbnail is None:
        lib.set_node_thumbnail(node, None)

    rect = compute_thumbnail_rect(node)
    lib.set_node_thumbnail(node, thumbnail, rect)


def compute_thumbnail_rect(node):
    """Compute thumbnail bounding rect based on thumbnail parms"""
    offset_x = node.evalParm("thumbnail_offsetx")
    offset_y = node.evalParm("thumbnail_offsety")
    width = node.evalParm("thumbnail_size")
    # todo: compute height from aspect of actual image file.
    aspect = 0.5625  # for now assume 16:9
    height = width * aspect

    center = 0.5
    half_width = (width * .5)

    return hou.BoundingRect(
        offset_x + center - half_width,
        offset_y,
        offset_x + center + half_width,
        offset_y + height
    )


def on_thumbnail_show_changed(node):
    """Callback on thumbnail show parm changed"""
    if node.evalParm("show_thumbnail"):
        # For now, update all
        on_representation_id_changed(node)
    else:
        lib.remove_all_thumbnails(node)


def on_thumbnail_size_changed(node):
    """Callback on thumbnail offset or size parms changed"""
    thumbnail = lib.get_node_thumbnail(node)
    if thumbnail:
        rect = compute_thumbnail_rect(node)
        thumbnail.setRect(rect)
        lib.set_node_thumbnail(node, thumbnail)


def on_representation_id_changed(node):
    """Callback on representation id changed

    Args:
        node (hou.Node): Node to update.
    """
    repre_id = node.evalParm("representation")
    set_representation(node, repre_id)


def on_representation_parms_changed(node):
    """
    Usually used as callback to the project, folder, product, version and
    representation parms which on change - would result in a different
    representation id to be resolved.

    Args:
        node (hou.Node): Node to update.
    """
    project_name = node.evalParm("project_name") or get_current_project_name()
    representation_id = get_representation_id(
        project_name=project_name,
        folder_path=node.evalParm("folder_path"),
        product_name=node.evalParm("product_name"),
        version=node.evalParm("version"),
        representation_name=node.evalParm("representation_name"),
        load_message_parm=node.parm("load_message")
    )
    if representation_id is None:
        representation_id = ""
    else:
        representation_id = str(representation_id)

    if node.evalParm("representation") != representation_id:
        node.parm("representation").set(representation_id)
        node.parm("representation").pressButton()  # trigger callback


def get_representation_id(
        project_name,
        folder_path,
        product_name,
        version,
        representation_name,
        load_message_parm,
):
    """Get representation id.

    Args:
        project_name (str): Project name
        folder_path (str): Folder name
        product_name (str): Product name
        version (str): Version name as string
        representation_name (str): Representation name
        load_message_parm (hou.Parm): A string message parm to report
            any error messages to.

    Returns:
        Optional[str]: Representation id or None if not found.

    """

    if not all([
        project_name, folder_path, product_name, version, representation_name
    ]):
        labels = {
            "project": project_name,
            "folder": folder_path,
            "product": product_name,
            "version": version,
            "representation": representation_name
        }
        missing = ", ".join(key for key, value in labels.items() if not value)
        load_message_parm.set(f"Load info incomplete. Found empty: {missing}")
        return

    try:
        version = int(version.strip())
    except ValueError:
        load_message_parm.set(f"Invalid version format: '{version}'\n"
                              "Make sure to set a valid version number.")
        return

    folder_entity = get_folder_by_path(project_name,
                                       folder_path=folder_path,
                                       fields={"id"})
    if not folder_entity:
        # This may be due to the project not existing - so let's validate
        # that first
        if not get_project(project_name):
            load_message_parm.set(f"Project not found: '{project_name}'")
            return
        load_message_parm.set(f"Folder not found: '{folder_path}'")
        return

    product_entity = get_product_by_name(
        project_name,
        product_name=product_name,
        folder_id=folder_entity["id"],
        fields={"id"})
    if not product_entity:
        load_message_parm.set(f"Product not found: '{product_name}'")
        return
    version_entity = get_version_by_name(
        project_name,
        version,
        product_id=product_entity["id"],
        fields={"id"})
    if not version_entity:
        load_message_parm.set(f"Version not found: '{version}'")
        return
    representation_entity = get_representation_by_name(
        project_name,
        representation_name,
        version_id=version_entity["id"],
        fields={"id"})
    if not representation_entity:
        load_message_parm.set(
            f"Representation not found: '{representation_name}'.")
        return
    return representation_entity["id"]


def setup_flag_changed_callback(node):
    """Register flag changed callback (for thumbnail brightness)"""
    node.addEventCallback(
        (hou.nodeEventType.FlagChanged,),
        on_flag_changed
    )


def on_flag_changed(node, **kwargs):
    """On node flag changed callback.

    Updates the brightness of attached thumbnails
    """
    # Showing thumbnail is disabled so can return early since
    # there should be no thumbnail to update.
    if not node.evalParm('show_thumbnail'):
        return

    # Update node thumbnails brightness with the
    # bypass state of the node.
    parent = node.parent()
    images = lib.get_background_images(parent)
    if not images:
        return

    brightness = 0.3 if node.isBypassed() else 1.0
    has_changes = False
    node_path = node.path()
    for image in images:
        if image.relativeToPath() == node_path:
            image.setBrightness(brightness)
            has_changes = True

    if has_changes:
        lib.set_background_images(parent, images)


def keep_background_images_linked(node, old_name):
    """Reconnect background images to node from old name.

     Used as callback on node name changes to keep thumbnails linked."""
    from ayon_houdini.api.lib import (
        get_background_images,
        set_background_images
    )

    parent = node.parent()
    images = get_background_images(parent)
    if not images:
        return

    changes = False
    old_path = f"{node.parent().path()}/{old_name}"
    for image in images:
        if image.relativeToPath() == old_path:
            image.setRelativeToPath(node.path())
            changes = True

    if changes:
        set_background_images(parent, images)


class SelectFolderPathDialog(QtWidgets.QDialog):
    """Simple dialog to allow a user to select project and asset."""

    def __init__(self, parent=None):
        super(SelectFolderPathDialog, self).__init__(parent)
        self.setWindowTitle("Set project and folder path")
        self.setStyleSheet(load_stylesheet())

        project_widget = QtWidgets.QComboBox()
        project_widget.addItems(self.get_projects())

        filter_widget = QtWidgets.QLineEdit()
        filter_widget.setPlaceholderText("Folder name filter...")

        folder_widget = SimpleFoldersWidget(parent=self)

        accept_button = QtWidgets.QPushButton("Accept")

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.addWidget(project_widget, 0)
        main_layout.addWidget(filter_widget, 0)
        main_layout.addWidget(folder_widget, 1)
        main_layout.addWidget(accept_button, 0)

        self.project_widget = project_widget
        self.folder_widget = folder_widget

        project_widget.currentTextChanged.connect(self.on_project_changed)
        filter_widget.textChanged.connect(folder_widget.set_name_filter)
        folder_widget.double_clicked.connect(self.accept)
        accept_button.clicked.connect(self.accept)

    def get_selected_folder_path(self) -> str:
        return self.folder_widget.get_selected_folder_path()

    def get_selected_project_name(self) -> str:
        return self.project_widget.currentText()

    def get_projects(self) -> List[str]:
        projects = ayon_api.get_projects(fields=["name"])
        return [p["name"] for p in projects]

    def on_project_changed(self, project_name: str):
        self.folder_widget.set_project_name(project_name)

    def set_project_name(self, project_name: str):
        self.project_widget.setCurrentText(project_name)

        if self.project_widget.currentText() != project_name:
            # Project does not exist
            return

        # Force the set of widget because even though a callback exist on the
        # project widget it may have been initialized to that value and hence
        # detect no change.
        self.folder_widget.set_project_name(project_name)


def select_folder_path(node):
    """Show dialog to select folder path.

    When triggered it opens a dialog that shows the available
    folder paths within a given project.

    Note:
        This function should be refactored.
        It currently shows the available
          folder paths within the current project only.

    Args:
        node (hou.OpNode): The HDA node.
    """
    main_window = lib.get_main_window()

    project_name = node.evalParm("project_name")
    folder_path = node.evalParm("folder_path")

    dialog = SelectFolderPathDialog(parent=main_window)
    dialog.set_project_name(project_name)
    if folder_path:
        # We add a small delay to the setting of the selected folder
        # because the folder widget's set project logic itself also runs
        # with a bit of a delay, and unfortunately otherwise the project
        # has not been selected yet and thus selection does not work.
        def _select_folder_path():
            dialog.folder_widget.set_selected_folder_path(folder_path)
        QtCore.QTimer.singleShot(100, _select_folder_path)

    dialog.setStyleSheet(load_stylesheet())

    result = dialog.exec_()
    if result != QtWidgets.QDialog.Accepted:
        return

    # Set project
    selected_project_name = dialog.get_selected_project_name()
    if selected_project_name == get_current_project_name():
        selected_project_name = '$AYON_PROJECT_NAME'

    project_parm = node.parm("project_name")
    project_parm.set(selected_project_name)
    project_parm.pressButton()  # allow any callbacks to trigger

    # Set folder path
    selected_folder_path = dialog.get_selected_folder_path()
    if not selected_folder_path:
        # Do nothing if user accepted with nothing selected
        return

    if selected_folder_path == get_current_folder_path():
        selected_folder_path = '$AYON_FOLDER_PATH'

    folder_parm = node.parm("folder_path")
    folder_parm.set(selected_folder_path)
    folder_parm.pressButton()  # allow any callbacks to trigger


def get_available_products(node):
    """Return products menu items
    It gets a list of available products of the specified product types
      within the specified folder path with in the specified project.
    Users can specify those in the HDA parameters.

    Args:
        node (hou.OpNode): The HDA node.

    Returns:
        list[str]: Product names for Products menu.
    """
    project_name = node.evalParm("project_name")
    folder_path = node.evalParm("folder_path")
    product_type = node.evalParm("product_type")

    folder_entity = ayon_api.get_folder_by_path(project_name,
                                                folder_path,
                                                fields={"id"})
    if not folder_entity:
        return []

    products = ayon_api.get_products(
        project_name,
        folder_ids=[folder_entity["id"]],
        product_types=[product_type]
    )

    return [product["name"] for product in products]


def set_to_latest_version(node):
    """Callback on product name change

    Refresh version parameter value by setting its value to
    the latest version of the selected product.

    Args:
        node (hou.OpNode): The HDA node.
    """

    versions = get_available_versions(node)
    if versions:
        node.parm("version").set(str(versions[0]))
