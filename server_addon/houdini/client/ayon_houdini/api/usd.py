"""Houdini-specific USD Library functions."""

import contextlib
import logging

import ayon_api
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import style
from ayon_core.pipeline import get_current_project_name
from ayon_core.tools.utils import (
    PlaceholderLineEdit,
    RefreshButton,
    SimpleFoldersWidget,
)

from pxr import Sdf


log = logging.getLogger(__name__)


class SelectFolderDialog(QtWidgets.QWidget):
    """Frameless folders dialog to select folder with double click.

    Args:
        parm: Parameter where selected folder path is set.
    """

    def __init__(self, parm):
        self.setWindowTitle("Pick Folder")
        self.setWindowFlags(QtCore.Qt.FramelessWindowHint | QtCore.Qt.Popup)

        header_widget = QtWidgets.QWidget(self)

        filter_input = PlaceholderLineEdit(header_widget)
        filter_input.setPlaceholderText("Filter folders..")

        refresh_btn = RefreshButton(self)

        header_layout = QtWidgets.QHBoxLayout(header_widget)
        header_layout.setContentsMargins(0, 0, 0, 0)
        header_layout.addWidget(filter_input)
        header_layout.addWidget(refresh_btn)

        for widget in (
            refresh_btn,
            filter_input,
        ):
            size_policy = widget.sizePolicy()
            size_policy.setVerticalPolicy(
                QtWidgets.QSizePolicy.MinimumExpanding)
            widget.setSizePolicy(size_policy)

        folders_widget = SimpleFoldersWidget(self)
        folders_widget.set_project_name(get_current_project_name())

        layout = QtWidgets.QHBoxLayout(self)
        layout.addWidget(header_widget, 0)
        layout.addWidget(folders_widget, 1)

        folders_widget.double_clicked.connect(self._set_parameter)
        filter_input.textChanged.connect(self._on_filter_change)
        refresh_btn.clicked.connect(self._on_refresh_clicked)

        self._folders_widget = folders_widget
        self._parm = parm

    def _on_refresh_clicked(self):
        self._folders_widget.refresh()

    def _on_filter_change(self, text):
        self._folders_widget.set_name_filter(text)

    def _set_parameter(self):
        folder_path = self._folders_widget.get_selected_folder_path()
        self._parm.set(folder_path)
        self.close()

    def _on_show(self):
        pos = QtGui.QCursor.pos()
        # Select the current folder if there is any
        select_id = None
        folder_path = self._parm.eval()
        if folder_path:
            project_name = get_current_project_name()
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path, fields={"id"}
            )
            if folder_entity:
                select_id = folder_entity["id"]

        # Set stylesheet
        self.setStyleSheet(style.load_stylesheet())
        # Refresh folders (is threaded)
        self._folders_widget.refresh()
        # Select folder - must be done after refresh
        if select_id is not None:
            self._folders_widget.set_selected_folder(select_id)

        # Show cursor (top right of window) near cursor
        self.resize(250, 400)
        self.move(self.mapFromGlobal(pos) - QtCore.QPoint(self.width(), 0))

    def showEvent(self, event):
        super(SelectFolderDialog, self).showEvent(event)
        self._on_show()


def pick_folder(node):
    """Show a user interface to select an Folder in the project

    When double clicking an folder it will set the Folder value in the
    'folderPath' parameter.

    """

    parm = node.parm("folderPath")
    if not parm:
        log.error("Node has no 'folderPath' parameter: %s", node)
        return

    # Construct a frameless popup so it automatically
    # closes when clicked outside of it.
    global tool
    tool = SelectFolderDialog(parm)
    tool.show()


def add_usd_output_processor(ropnode, processor):
    """Add USD Output Processor to USD Rop node.

    Args:
        ropnode (hou.RopNode): The USD Rop node.
        processor (str): The output processor name. This is the basename of
            the python file that contains the Houdini USD Output Processor.

    """

    import loputils

    loputils.handleOutputProcessorAdd(
        {
            "node": ropnode,
            "parm": ropnode.parm("outputprocessors"),
            "script_value": processor,
        }
    )


def remove_usd_output_processor(ropnode, processor):
    """Removes USD Output Processor from USD Rop node.

    Args:
        ropnode (hou.RopNode): The USD Rop node.
        processor (str): The output processor name. This is the basename of
            the python file that contains the Houdini USD Output Processor.

    """
    import loputils

    parm = ropnode.parm(processor + "_remove")
    if not parm:
        raise RuntimeError(
            "Output Processor %s does not "
            "exist on %s" % (processor, ropnode.name())
        )

    loputils.handleOutputProcessorRemove({"node": ropnode, "parm": parm})


@contextlib.contextmanager
def outputprocessors(ropnode, processors=tuple(), disable_all_others=True):
    """Context manager to temporarily add Output Processors to USD ROP node.

    Args:
        ropnode (hou.RopNode): The USD Rop node.
        processors (tuple or list): The processors to add.
        disable_all_others (bool, Optional): Whether to disable all
            output processors currently on the ROP node that are not in the
            `processors` list passed to this function.

    """
    # TODO: Add support for forcing the correct Order of the processors

    original = []
    prefix = "enableoutputprocessor_"
    processor_parms = ropnode.globParms(prefix + "*")
    for parm in processor_parms:
        original.append((parm, parm.eval()))

    if disable_all_others:
        for parm in processor_parms:
            parm.set(False)

    added = []
    for processor in processors:

        parm = ropnode.parm(prefix + processor)
        if parm:
            # If processor already exists, just enable it
            parm.set(True)

        else:
            # Else add the new processor
            add_usd_output_processor(ropnode, processor)
            added.append(processor)

    try:
        yield
    finally:

        # Remove newly added processors
        for processor in added:
            remove_usd_output_processor(ropnode, processor)

        # Revert to original values
        for parm, value in original:
            if parm:
                parm.set(value)


def get_usd_rop_loppath(node):

    # Get sop path
    node_type = node.type().name()
    if node_type == "usd":
        return node.parm("loppath").evalAsNode()

    elif node_type in {"usd_rop", "usdrender_rop"}:
        # Inside Solaris e.g. /stage (not in ROP context)
        # When incoming connection is present it takes it directly
        inputs = node.inputs()
        if inputs:
            return inputs[0]
        else:
            return node.parm("loppath").evalAsNode()


def get_layer_save_path(layer):
    """Get custom HoudiniLayerInfo->HoudiniSavePath from SdfLayer.

    Args:
        layer (pxr.Sdf.Layer): The Layer to retrieve the save pah data from.

    Returns:
        str or None: Path to save to when data exists.

    """
    hou_layer_info = layer.rootPrims.get("HoudiniLayerInfo")
    if not hou_layer_info:
        return

    save_path = hou_layer_info.customData.get("HoudiniSavePath", None)
    if save_path:
        # Unfortunately this doesn't actually resolve the full absolute path
        return layer.ComputeAbsolutePath(save_path)


def get_referenced_layers(layer):
    """Return SdfLayers for all external references of the current layer

    Args:
        layer (pxr.Sdf.Layer): The Layer to retrieve the save pah data from.

    Returns:
        list: List of pxr.Sdf.Layer that are external references to this layer

    """

    layers = []
    for layer_id in layer.GetExternalReferences():
        layer = Sdf.Layer.Find(layer_id)
        if not layer:
            # A file may not be in memory and is
            # referenced from disk. As such it cannot
            # be found. We will ignore those layers.
            continue

        layers.append(layer)

    return layers


def iter_layer_recursive(layer):
    """Recursively iterate all 'external' referenced layers"""

    layers = get_referenced_layers(layer)
    traversed = set(layers)  # Avoid recursion to itself (if even possible)
    traverse = list(layers)
    for layer in traverse:

        # Include children layers (recursion)
        children_layers = get_referenced_layers(layer)
        children_layers = [x for x in children_layers if x not in traversed]
        traverse.extend(children_layers)
        traversed.update(children_layers)

        yield layer


def get_configured_save_layers(usd_rop):

    lop_node = get_usd_rop_loppath(usd_rop)
    stage = lop_node.stage(apply_viewport_overrides=False)
    if not stage:
        raise RuntimeError(
            "No valid USD stage for ROP node: " "%s" % usd_rop.path()
        )

    root_layer = stage.GetRootLayer()

    save_layers = []
    for layer in iter_layer_recursive(root_layer):
        save_path = get_layer_save_path(layer)
        if save_path is not None:
            save_layers.append(layer)

    return save_layers
