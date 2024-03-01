from pathlib import Path
from qtpy import QtWidgets, QtCore, QtGui

from ayon_api import get_folders_hierarchy
from ayon_core import (
    resources,
    style
)
from ayon_core.pipeline import get_current_project_name
from ayon_core.settings import get_project_settings
from ayon_core.tools.utils import (
    show_message_dialog,
    PlaceholderLineEdit,
    SquareButton,
)
from ayon_core.tools.ayon_utils.widgets import (
    SimpleFoldersWidget,
)
from ayon_core.hosts.unreal.api.pipeline import (
    generate_sequence,
    set_sequence_hierarchy,
)

import unreal


class ConfirmButton(SquareButton):
    def __init__(self, parent=None):
        super(ConfirmButton, self).__init__(parent)
        self.setText("Confirm")


class FolderSelector(QtWidgets.QWidget):
    """Widget for selecting a folder from the project hierarchy."""

    confirm_btn = None

    def __init__(self, controller=None, parent=None, project=None):
        if not project:
            raise ValueError("Project name not provided.")

        super(FolderSelector, self).__init__(parent)

        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)
        self.setWindowTitle("Folder Selector")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        self.setAttribute(QtCore.Qt.WA_DeleteOnClose, False)

        self.setStyleSheet(style.load_stylesheet())

        # Allow minimize
        self.setWindowFlags(
            QtCore.Qt.Window
            | QtCore.Qt.CustomizeWindowHint
            | QtCore.Qt.WindowTitleHint
            | QtCore.Qt.WindowMinimizeButtonHint
            | QtCore.Qt.WindowCloseButtonHint
        )

        content_body = QtWidgets.QWidget(self)

        # Folders
        folders_wrapper = QtWidgets.QWidget(content_body)

        folders_filter_text = PlaceholderLineEdit(folders_wrapper)
        folders_filter_text.setPlaceholderText("Filter folders...")

        folders_widget = SimpleFoldersWidget(
            controller=None, parent=folders_wrapper)
        folders_widget.set_project_name(project_name=project)

        folders_wrapper_layout = QtWidgets.QVBoxLayout(folders_wrapper)
        folders_wrapper_layout.setContentsMargins(0, 0, 0, 0)
        folders_wrapper_layout.addWidget(folders_filter_text, 0)
        folders_wrapper_layout.addWidget(folders_widget, 1)

        # Footer
        footer_widget = QtWidgets.QWidget(content_body)

        self.confirm_btn = ConfirmButton(footer_widget)

        footer_layout = QtWidgets.QHBoxLayout(footer_widget)
        footer_layout.setContentsMargins(0, 0, 0, 0)
        footer_layout.addWidget(self.confirm_btn, 0)

        # Main layout
        content_layout = QtWidgets.QVBoxLayout(content_body)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.addWidget(folders_wrapper, 1)
        content_layout.addWidget(footer_widget, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(content_body, 1)

        folders_filter_text.textChanged.connect(
            self._on_filter_text_changed)

        self._controller = controller

        self._confirm_btn = self.confirm_btn
        self._folders_widget = folders_widget

        self.resize(300, 400)

        self.show()
        self.raise_()
        self.activateWindow()

    def _on_filter_text_changed(self, text):
        self._folders_widget.set_name_filter(text)

    def get_selected_folder(self):
        return self._folders_widget.get_selected_folder_path()


def get_default_sequence_path(settings):
    """Get default render folder from blender settings."""

    sequence_path = settings['unreal']['sequence_path']
    sequence_path = sequence_path.rstrip("/")

    return f"/Game/{sequence_path}"


def _create_level(path, name, master_level):
    # Create the level
    level_path = f"{path}/{name}_map"
    level_package = f"{level_path}.{name}_map"
    unreal.EditorLevelLibrary.new_level(level_path)

    # Add the level to the master level as sublevel
    unreal.EditorLevelLibrary.load_level(master_level)
    unreal.EditorLevelUtils.add_level_to_world(
        unreal.EditorLevelLibrary.get_editor_world(),
        level_package,
        unreal.LevelStreamingDynamic
    )
    unreal.EditorLevelLibrary.save_all_dirty_levels()

    return level_package


def _create_sequence(
    element, sequence_path, master_level,
    parent_path="", parents_sequence=[], parents_frame_range=[]
):
    """
    Create sequences from the hierarchy element.

    Args:
        element (dict): The hierarchy element.
        sequence_path (str): The sequence path.
        master_level (str): The master level package.
        parent_path (str): The parent path.
        parents_sequence (list): The list of parent sequences.
        parents_frame_range (list): The list of parent frame ranges.
    """
    name = element["name"]
    path = f"{parent_path}/{name}"
    hierarchy_dir = f"{sequence_path}{path}"
    children = element["children"]

    # Create sequence for the current element
    sequence, frame_range = generate_sequence(name, hierarchy_dir)

    sequences = parents_sequence.copy() + [sequence]
    frame_ranges = parents_frame_range.copy() + [frame_range]

    if children:
        # Traverse the children and create sequences recursively
        for child in children:
            _create_sequence(
                child, sequence_path, master_level, parent_path=path,
                parents_sequence=sequences, parents_frame_range=frame_ranges)
    else:
        level = _create_level(hierarchy_dir, name, master_level)

        # Create the sequence hierarchy. Add each child to its parent
        for i in range(len(parents_sequence) - 1):
            set_sequence_hierarchy(
                parents_sequence[i], parents_sequence[i + 1],
                parents_frame_range[i][1],
                parents_frame_range[i + 1][0], parents_frame_range[i + 1][1],
                [level])

        # Add the newly created sequence to its parent
        set_sequence_hierarchy(
            parents_sequence[-1], sequence,
            parents_frame_range[-1][1],
            frame_range[0], frame_range[1],
            [level])


def _find_in_hierarchy(hierarchy, path):
    """
    Find the hierarchy element from the path.

    Args:
        hierarchy (list): The hierarchy list.
        path (str): The path to find.
    """
    elements = path.split("/")
    current_element = elements[0]

    for element in hierarchy:
        if element["name"] == current_element:
            if len(elements) == 1:
                return element

            remaining_path = "/".join(elements[1:])
            return _find_in_hierarchy(element["children"], remaining_path)

    return None


def _on_confirm_clicked(selected_root, sequence_path, project):
    sequence_root_name = selected_root.lstrip("/")

    sequence_root = f"{sequence_path}/{sequence_root_name}"
    asset_content = unreal.EditorAssetLibrary.list_assets(
        sequence_root, recursive=False, include_folder=True)

    if asset_content:
        msg = (
            "The sequence folder is not empty. Please delete the contents "
            "before building the sequence hierarchy.")
        show_message_dialog(
            parent=None,
            title="Sequence Folder not empty",
            message=msg,
            level="critical")

        return

    hierarchy = get_folders_hierarchy(project_name=project)["hierarchy"]

    # Find the sequence root element in the hierarchy
    hierarchy_element = _find_in_hierarchy(hierarchy, sequence_root_name)

    # Raise an error if the sequence root element is not found
    if not hierarchy_element:
        raise ValueError(f"Could not find {sequence_root_name} in hierarchy")

    # Create the master level
    master_level_name = sequence_root_name.split("/")[-1]
    master_level_path = f"{sequence_root}/{master_level_name}_map"
    master_level_package = f"{master_level_path}.{master_level_name}_map"
    unreal.EditorLevelLibrary.new_level(master_level_path)

    # Start creating sequences from the root element
    _create_sequence(
        hierarchy_element, Path(sequence_root).parent.as_posix(),
        master_level_package)

    # List all the assets in the sequence path and save them
    asset_content = unreal.EditorAssetLibrary.list_assets(
        sequence_root, recursive=True, include_folder=False
    )

    for a in asset_content:
        unreal.EditorAssetLibrary.save_asset(a)

    # Load the master level
    unreal.EditorLevelLibrary.load_level(master_level_package)


def build_sequence_hierarchy():
    """
    Builds the sequence hierarchy by creating sequences from the root element.

    Raises:
        ValueError: If the sequence root element is not found in the hierarchy.
    """
    print("Building sequence hierarchy...")

    project = get_current_project_name()

    settings = get_project_settings(project)
    sequence_path = get_default_sequence_path(settings)

    folder_selector = FolderSelector(project=project)

    folder_selector.confirm_btn.clicked.connect(
        lambda: _on_confirm_clicked(
            folder_selector.get_selected_folder(), sequence_path, project)
    )
