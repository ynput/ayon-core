import sys
import traceback
import re

import ayon_api
from qtpy import QtWidgets, QtCore

from ayon_core import style
from ayon_core.settings import get_current_project_settings
from ayon_core.tools.utils.lib import qt_app_context
from ayon_core.pipeline import (
    get_current_project_name,
    get_current_folder_path,
    get_current_task_name,
)
from ayon_core.pipeline.create import (
    PRODUCT_NAME_ALLOWED_SYMBOLS,
    legacy_create,
    CreatorError,
)

from .model import CreatorsModel
from .widgets import (
    CreateErrorMessageBox,
    VariantLineEdit,
    ProductTypeDescriptionWidget
)
from .constants import (
    ITEM_ID_ROLE,
    SEPARATOR,
    SEPARATORS
)

module = sys.modules[__name__]
module.window = None


class CreatorWindow(QtWidgets.QDialog):
    def __init__(self, parent=None):
        super(CreatorWindow, self).__init__(parent)
        self.setWindowTitle("Instance Creator")
        self.setFocusPolicy(QtCore.Qt.StrongFocus)
        if not parent:
            self.setWindowFlags(
                self.windowFlags() | QtCore.Qt.WindowStaysOnTopHint
            )

        creator_info = ProductTypeDescriptionWidget(self)

        creators_model = CreatorsModel()

        creators_proxy = QtCore.QSortFilterProxyModel()
        creators_proxy.setSourceModel(creators_model)

        creators_view = QtWidgets.QListView(self)
        creators_view.setObjectName("CreatorsView")
        creators_view.setModel(creators_proxy)

        folder_path_input = QtWidgets.QLineEdit(self)
        variant_input = VariantLineEdit(self)
        product_name_input = QtWidgets.QLineEdit(self)
        product_name_input.setEnabled(False)

        variants_btn = QtWidgets.QPushButton()
        variants_btn.setFixedWidth(18)
        variants_menu = QtWidgets.QMenu(variants_btn)
        variants_btn.setMenu(variants_menu)

        name_layout = QtWidgets.QHBoxLayout()
        name_layout.addWidget(variant_input)
        name_layout.addWidget(variants_btn)
        name_layout.setSpacing(3)
        name_layout.setContentsMargins(0, 0, 0, 0)

        body_layout = QtWidgets.QVBoxLayout()
        body_layout.setContentsMargins(0, 0, 0, 0)

        body_layout.addWidget(creator_info, 0)
        body_layout.addWidget(QtWidgets.QLabel("Product type", self), 0)
        body_layout.addWidget(creators_view, 1)
        body_layout.addWidget(QtWidgets.QLabel("Folder path", self), 0)
        body_layout.addWidget(folder_path_input, 0)
        body_layout.addWidget(QtWidgets.QLabel("Product name", self), 0)
        body_layout.addLayout(name_layout, 0)
        body_layout.addWidget(product_name_input, 0)

        useselection_chk = QtWidgets.QCheckBox("Use selection", self)
        useselection_chk.setCheckState(QtCore.Qt.Checked)

        create_btn = QtWidgets.QPushButton("Create", self)
        # Need to store error_msg to prevent garbage collection
        msg_label = QtWidgets.QLabel(self)

        footer_layout = QtWidgets.QVBoxLayout()
        footer_layout.addWidget(create_btn, 0)
        footer_layout.addWidget(msg_label, 0)
        footer_layout.setContentsMargins(0, 0, 0, 0)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addLayout(body_layout, 1)
        layout.addWidget(useselection_chk, 0, QtCore.Qt.AlignLeft)
        layout.addLayout(footer_layout, 0)

        msg_timer = QtCore.QTimer()
        msg_timer.setSingleShot(True)
        msg_timer.setInterval(5000)

        validation_timer = QtCore.QTimer()
        validation_timer.setSingleShot(True)
        validation_timer.setInterval(300)

        msg_timer.timeout.connect(self._on_msg_timer)
        validation_timer.timeout.connect(self._on_validation_timer)

        create_btn.clicked.connect(self._on_create)
        variant_input.returnPressed.connect(self._on_create)
        variant_input.textChanged.connect(self._on_data_changed)
        variant_input.report.connect(self.echo)
        folder_path_input.textChanged.connect(self._on_data_changed)
        creators_view.selectionModel().currentChanged.connect(
            self._on_selection_changed
        )

        # Store valid states and
        self._is_valid = False
        create_btn.setEnabled(self._is_valid)

        self._first_show = True

        # Message dialog when something goes wrong during creation
        self._message_dialog = None

        self._creator_info = creator_info
        self._create_btn = create_btn
        self._useselection_chk = useselection_chk
        self._variant_input = variant_input
        self._product_name_input = product_name_input
        self._folder_path_input = folder_path_input

        self._creators_model = creators_model
        self._creators_proxy = creators_proxy
        self._creators_view = creators_view

        self._variants_btn = variants_btn
        self._variants_menu = variants_menu

        self._msg_label = msg_label

        self._validation_timer = validation_timer
        self._msg_timer = msg_timer

        # Defaults
        self.resize(300, 500)
        variant_input.setFocus()

    def _set_valid_state(self, valid):
        if self._is_valid == valid:
            return
        self._is_valid = valid
        self._create_btn.setEnabled(valid)

    def _build_menu(self, default_names=None):
        """Create optional predefined variants.

        Args:
            default_names(list): all predefined names

        Returns:
             None
        """
        if not default_names:
            default_names = []

        menu = self._variants_menu
        button = self._variants_btn

        # Get and destroy the action group
        group = button.findChild(QtWidgets.QActionGroup)
        if group:
            group.deleteLater()

        state = any(default_names)
        button.setEnabled(state)
        if state is False:
            return

        # Build new action group
        group = QtWidgets.QActionGroup(button)
        for name in default_names:
            if name in SEPARATORS:
                menu.addSeparator()
                continue
            action = group.addAction(name)
            menu.addAction(action)

        group.triggered.connect(self._on_action_clicked)

    def _on_action_clicked(self, action):
        self._variant_input.setText(action.text())

    def _on_data_changed(self, *args):
        # Set invalid state until it's reconfirmed to be valid by the
        # scheduled callback so any form of creation is held back until
        # valid again
        self._set_valid_state(False)

        self._validation_timer.start()

    def _on_validation_timer(self):
        index = self._creators_view.currentIndex()
        item_id = index.data(ITEM_ID_ROLE)
        creator_plugin = self._creators_model.get_creator_by_id(item_id)
        user_input_text = self._variant_input.text()
        folder_path = self._folder_path_input.text()

        # Early exit if no folder path
        if not folder_path:
            self._build_menu()
            self.echo("Folder is required ..")
            self._set_valid_state(False)
            return

        project_name = get_current_project_name()
        folder_entity = None
        if creator_plugin:
            # Get the folder from the database which match with the name
            folder_entity = ayon_api.get_folder_by_path(
                project_name, folder_path, fields={"id"}
            )

        # Get plugin
        if not folder_entity or not creator_plugin:
            self._build_menu()

            if not creator_plugin:
                self.echo("No registered product types ..")
            else:
                self.echo("Folder '{}' not found ..".format(folder_path))
            self._set_valid_state(False)
            return

        folder_id = folder_entity["id"]

        task_name = get_current_task_name()
        task_entity = ayon_api.get_task_by_name(
            project_name, folder_id, task_name
        )

        # Calculate product name with Creator plugin
        product_name = creator_plugin.get_product_name(
            project_name, folder_entity, task_entity, user_input_text
        )
        # Force replacement of prohibited symbols
        # QUESTION should Creator care about this and here should be only
        #   validated with schema regex?

        # Allow curly brackets in product name for dynamic keys
        curly_left = "__cbl__"
        curly_right = "__cbr__"
        tmp_product_name = (
            product_name
            .replace("{", curly_left)
            .replace("}", curly_right)
        )
        # Replace prohibited symbols
        tmp_product_name = re.sub(
            "[^{}]+".format(PRODUCT_NAME_ALLOWED_SYMBOLS),
            "",
            tmp_product_name
        )
        product_name = (
            tmp_product_name
            .replace(curly_left, "{")
            .replace(curly_right, "}")
        )
        self._product_name_input.setText(product_name)

        # Get all products of the current folder
        product_entities = ayon_api.get_products(
            project_name, folder_ids={folder_id}, fields={"name"}
        )
        existing_product_names = {
            product_entity["name"]
            for product_entity in product_entities
        }
        existing_product_names_low = set(
            _name.lower()
            for _name in existing_product_names
        )

        # Defaults to dropdown
        defaults = []
        # Check if Creator plugin has set defaults
        if (
            creator_plugin.defaults
            and isinstance(creator_plugin.defaults, (list, tuple, set))
        ):
            defaults = list(creator_plugin.defaults)

        # Replace
        compare_regex = re.compile(re.sub(
            user_input_text, "(.+)", product_name, flags=re.IGNORECASE
        ))
        variant_hints = set()
        if user_input_text:
            for _name in existing_product_names:
                _result = compare_regex.search(_name)
                if _result:
                    variant_hints |= set(_result.groups())

        if variant_hints:
            if defaults:
                defaults.append(SEPARATOR)
            defaults.extend(variant_hints)
        self._build_menu(defaults)

        # Indicate product existence
        if not user_input_text:
            self._variant_input.as_empty()
        elif product_name.lower() in existing_product_names_low:
            # validate existence of product name with lowered text
            #   - "renderMain" vs. "rensermain" mean same path item for
            #   windows
            self._variant_input.as_exists()
        else:
            self._variant_input.as_new()

        # Update the valid state
        valid = product_name.strip() != ""

        self._set_valid_state(valid)

    def _on_selection_changed(self, old_idx, new_idx):
        index = self._creators_view.currentIndex()
        item_id = index.data(ITEM_ID_ROLE)

        creator_plugin = self._creators_model.get_creator_by_id(item_id)

        self._creator_info.set_item(creator_plugin)

        if creator_plugin is None:
            return

        default = None
        if hasattr(creator_plugin, "get_default_variant"):
            default = creator_plugin.get_default_variant()

        if not default:
            if (
                creator_plugin.defaults
                and isinstance(creator_plugin.defaults, list)
            ):
                default = creator_plugin.defaults[0]
            else:
                default = "Default"

        self._variant_input.setText(default)

        self._on_data_changed()

    def keyPressEvent(self, event):
        """Custom keyPressEvent.

        Override keyPressEvent to do nothing so that Maya's panels won't
        take focus when pressing "SHIFT" whilst mouse is over viewport or
        outliner. This way users don't accidentally perform Maya commands
        whilst trying to name an instance.

        """
        pass

    def showEvent(self, event):
        super(CreatorWindow, self).showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())

    def refresh(self):
        self._folder_path_input.setText(get_current_folder_path())

        self._creators_model.reset()

        product_types_smart_select = (
            get_current_project_settings()
            ["core"]
            ["tools"]
            ["creator"]
            ["product_types_smart_select"]
        )
        current_index = None
        product_type = None
        task_name = get_current_task_name() or None
        lowered_task_name = task_name.lower()
        if task_name:
            for smart_item in product_types_smart_select:
                _low_task_names = {
                    name.lower() for name in smart_item["task_names"]
                }
                for _task_name in _low_task_names:
                    if _task_name in lowered_task_name:
                        product_type = smart_item["name"]
                        break
                if product_type:
                    break

        if product_type:
            indexes = self._creators_model.get_indexes_by_product_type(
                product_type
            )
            if indexes:
                index = indexes[0]
                current_index = self._creators_proxy.mapFromSource(index)

        if current_index is None or not current_index.isValid():
            current_index = self._creators_proxy.index(0, 0)

        self._creators_view.setCurrentIndex(current_index)

    def _on_create(self):
        # Do not allow creation in an invalid state
        if not self._is_valid:
            return

        index = self._creators_view.currentIndex()
        item_id = index.data(ITEM_ID_ROLE)
        creator_plugin = self._creators_model.get_creator_by_id(item_id)
        if creator_plugin is None:
            return

        product_name = self._product_name_input.text()
        folder_path = self._folder_path_input.text()
        use_selection = self._useselection_chk.isChecked()

        variant = self._variant_input.text()

        error_info = None
        try:
            legacy_create(
                creator_plugin,
                product_name,
                folder_path,
                options={"useSelection": use_selection},
                data={"variant": variant}
            )

        except CreatorError as exc:
            self.echo("Creator error: {}".format(str(exc)))
            error_info = (str(exc), None)

        except Exception as exc:
            self.echo("Program error: %s" % str(exc))

            exc_type, exc_value, exc_traceback = sys.exc_info()
            formatted_traceback = "".join(traceback.format_exception(
                exc_type, exc_value, exc_traceback
            ))
            error_info = (str(exc), formatted_traceback)

        if error_info:
            box = CreateErrorMessageBox(
                creator_plugin.product_type,
                product_name,
                folder_path,
                *error_info,
                parent=self
            )
            box.show()
            # Store dialog so is not garbage collected before is shown
            self._message_dialog = box

        else:
            self.echo("Created %s .." % product_name)

    def _on_msg_timer(self):
        self._msg_label.setText("")

    def echo(self, message):
        self._msg_label.setText(str(message))
        self._msg_timer.start()


def show(parent=None):
    """Display product creator GUI

    Arguments:
        debug (bool, optional): Run loader in debug-mode,
            defaults to False
        parent (QtCore.QObject, optional): When provided parent the interface
            to this QObject.

    """

    try:
        module.window.close()
        del(module.window)
    except (AttributeError, RuntimeError):
        pass

    with qt_app_context():
        window = CreatorWindow(parent)
        window.refresh()
        window.show()

        module.window = window

        # Pull window to the front.
        module.window.raise_()
        module.window.activateWindow()
