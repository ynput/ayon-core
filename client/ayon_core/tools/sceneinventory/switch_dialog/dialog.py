import collections
import logging

import ayon_api
from qtpy import QtWidgets, QtCore
import qtawesome

from ayon_core.pipeline.load import (
    discover_loader_plugins,
    switch_container,
    get_repres_contexts,
    loaders_from_repre_context,
    LoaderSwitchNotImplementedError,
    IncompatibleLoaderError,
    LoaderNotFoundError
)

from .widgets import (
    ButtonWithMenu,
    SearchComboBox
)
from .folders_input import FoldersField

log = logging.getLogger("SwitchAssetDialog")


class ValidationState:
    def __init__(self):
        self.folder_ok = True
        self.product_ok = True
        self.repre_ok = True

    @property
    def all_ok(self):
        return (
            self.folder_ok
            and self.product_ok
            and self.repre_ok
        )


class SwitchAssetDialog(QtWidgets.QDialog):
    """Widget to support asset switching"""

    MIN_WIDTH = 550

    switched = QtCore.Signal()

    def __init__(self, controller, project_name, items, parent=None):
        super().__init__(parent)

        current_project_name = controller.get_current_project_name()
        folder_id = None
        if current_project_name == project_name:
            folder_id = controller.get_current_folder_id()

        self.setWindowTitle("Switch selected items ...")

        # Force and keep focus dialog
        self.setModal(True)

        folders_field = FoldersField(controller, self)
        products_combox = SearchComboBox(self)
        repres_combobox = SearchComboBox(self)

        products_combox.set_placeholder("<product>")
        repres_combobox.set_placeholder("<representation>")

        folder_label = QtWidgets.QLabel(self)
        product_label = QtWidgets.QLabel(self)
        repre_label = QtWidgets.QLabel(self)

        current_folder_btn = QtWidgets.QPushButton("Use current folder", self)

        accept_icon = qtawesome.icon("fa.check", color="white")
        accept_btn = ButtonWithMenu(self)
        accept_btn.setIcon(accept_icon)

        main_layout = QtWidgets.QGridLayout(self)
        # Folder column
        main_layout.addWidget(current_folder_btn, 0, 0)
        main_layout.addWidget(folders_field, 1, 0)
        main_layout.addWidget(folder_label, 2, 0)
        # Product column
        main_layout.addWidget(products_combox, 1, 1)
        main_layout.addWidget(product_label, 2, 1)
        # Representation column
        main_layout.addWidget(repres_combobox, 1, 2)
        main_layout.addWidget(repre_label, 2, 2)
        # Btn column
        main_layout.addWidget(accept_btn, 1, 3)
        main_layout.setColumnStretch(0, 1)
        main_layout.setColumnStretch(1, 1)
        main_layout.setColumnStretch(2, 1)
        main_layout.setColumnStretch(3, 0)

        show_timer = QtCore.QTimer()
        show_timer.setInterval(0)
        show_timer.setSingleShot(False)

        show_timer.timeout.connect(self._on_show_timer)
        folders_field.value_changed.connect(
            self._combobox_value_changed
        )
        products_combox.currentIndexChanged.connect(
            self._combobox_value_changed
        )
        repres_combobox.currentIndexChanged.connect(
            self._combobox_value_changed
        )
        accept_btn.clicked.connect(self._on_accept)
        current_folder_btn.clicked.connect(self._on_current_folder)

        self._show_timer = show_timer
        self._show_counter = 0

        self._current_folder_btn = current_folder_btn

        self._folders_field = folders_field
        self._products_combox = products_combox
        self._representations_box = repres_combobox

        self._folder_label = folder_label
        self._product_label = product_label
        self._repre_label = repre_label

        self._accept_btn = accept_btn

        self.setMinimumWidth(self.MIN_WIDTH)

        # Set default focus to accept button so you don't directly type in
        # first asset field, this also allows to see the placeholder value.
        accept_btn.setFocus()

        self._folder_entities_by_id = {}
        self._product_entities_by_id = {}
        self._version_entities_by_id = {}
        self._repre_entities_by_id = {}

        self._missing_folder_ids = set()
        self._missing_product_ids = set()
        self._missing_version_ids = set()
        self._missing_repre_ids = set()
        self._missing_entities = False

        self._inactive_folder_ids = set()
        self._inactive_product_ids = set()
        self._inactive_repre_ids = set()

        self._init_folder_id = None
        self._init_product_name = None
        self._init_repre_name = None

        self._fill_check = False
        self._project_name = project_name
        self._folder_id = folder_id

        self._current_folder_btn.setEnabled(folder_id is not None)

        self._controller = controller

        self._items = items
        self._prepare_content_data()

    def showEvent(self, event):
        super().showEvent(event)
        self._show_timer.start()

    def refresh(self, init_refresh=False):
        """Build the need comboboxes with content"""
        if not self._fill_check and not init_refresh:
            return

        self._fill_check = False

        validation_state = ValidationState()
        self._folders_field.refresh()
        # Set other comboboxes to empty if any document is missing or
        #   any folder of loaded representations is archived.
        self._is_folder_ok(validation_state)
        if validation_state.folder_ok:
            product_values = self._get_product_box_values()
            self._fill_combobox(product_values, "product")
            self._is_product_ok(validation_state)

        if validation_state.folder_ok and validation_state.product_ok:
            repre_values = sorted(self._representations_box_values())
            self._fill_combobox(repre_values, "repre")
            self._is_repre_ok(validation_state)

        # Fill comboboxes with values
        self.set_labels()

        self.apply_validations(validation_state)

        self._build_loaders_menu()

        if init_refresh:
            # pre select context if possible
            self._folders_field.set_selected_item(self._init_folder_id)
            self._products_combox.set_valid_value(self._init_product_name)
            self._representations_box.set_valid_value(self._init_repre_name)

        self._fill_check = True

    def set_labels(self):
        folder_label = self._folders_field.get_selected_folder_label()
        product_label = self._products_combox.get_valid_value()
        repre_label = self._representations_box.get_valid_value()

        default = "*No changes"
        self._folder_label.setText(folder_label or default)
        self._product_label.setText(product_label or default)
        self._repre_label.setText(repre_label or default)

    def apply_validations(self, validation_state):
        error_msg = "*Please select"
        error_sheet = "border: 1px solid red;"

        product_sheet = None
        repre_sheet = None
        accept_state = ""
        if validation_state.folder_ok is False:
            self._folder_label.setText(error_msg)
        elif validation_state.product_ok is False:
            product_sheet = error_sheet
            self._product_label.setText(error_msg)
        elif validation_state.repre_ok is False:
            repre_sheet = error_sheet
            self._repre_label.setText(error_msg)

        if validation_state.all_ok:
            accept_state = "1"

        self._folders_field.set_valid(validation_state.folder_ok)
        self._products_combox.setStyleSheet(product_sheet or "")
        self._representations_box.setStyleSheet(repre_sheet or "")

        self._accept_btn.setEnabled(validation_state.all_ok)
        self._set_style_property(self._accept_btn, "state", accept_state)

    def find_last_versions(self, product_ids):
        project_name = self._project_name
        return ayon_api.get_last_versions(
            project_name,
            product_ids,
            fields={"id", "productId", "version"}
        )

    def _on_show_timer(self):
        if self._show_counter == 2:
            self._show_timer.stop()
            self.refresh(True)
        else:
            self._show_counter += 1

    def _prepare_content_data(self):
        repre_ids = {
            item["representation"]
            for item in self._items
        }

        project_name = self._project_name
        repre_entities = list(ayon_api.get_representations(
            project_name,
            representation_ids=repre_ids,
        ))
        repres_by_id = {r["id"]: r for r in repre_entities}

        content_repre_entities_by_id = {}
        inactive_repre_ids = set()
        missing_repre_ids = set()
        version_ids = set()
        for repre_id in repre_ids:
            repre_entity = repres_by_id.get(repre_id)
            if repre_entity is None:
                missing_repre_ids.add(repre_id)
            elif not repres_by_id[repre_id]["active"]:
                inactive_repre_ids.add(repre_id)
                version_ids.add(repre_entity["versionId"])
            else:
                content_repre_entities_by_id[repre_id] = repre_entity
                version_ids.add(repre_entity["versionId"])

        version_entities = ayon_api.get_versions(
            project_name,
            version_ids=version_ids
        )
        content_version_entities_by_id = {}
        for version_entity in version_entities:
            version_id = version_entity["id"]
            content_version_entities_by_id[version_id] = version_entity

        missing_version_ids = set()
        product_ids = set()
        for version_id in version_ids:
            version_entity = content_version_entities_by_id.get(version_id)
            if version_entity is None:
                missing_version_ids.add(version_id)
            else:
                product_ids.add(version_entity["productId"])

        product_entities = ayon_api.get_products(
            project_name, product_ids=product_ids
        )
        product_entities_by_id = {p["id"]: p for p in product_entities}

        folder_ids = set()
        inactive_product_ids = set()
        missing_product_ids = set()
        content_product_entities_by_id = {}
        for product_id in product_ids:
            product_entity = product_entities_by_id.get(product_id)
            if product_entity is None:
                missing_product_ids.add(product_id)
            else:
                folder_ids.add(product_entity["folderId"])
                content_product_entities_by_id[product_id] = product_entity

        folder_entities = ayon_api.get_folders(
            project_name, folder_ids=folder_ids, active=None
        )
        folder_entities_by_id = {
            folder_entity["id"]: folder_entity
            for folder_entity in folder_entities
        }

        missing_folder_ids = set()
        inactive_folder_ids = set()
        content_folder_entities_by_id = {}
        for folder_id in folder_ids:
            folder_entity = folder_entities_by_id.get(folder_id)
            if folder_entity is None:
                missing_folder_ids.add(folder_id)
            elif not folder_entity["active"]:
                inactive_folder_ids.add(folder_id)
            else:
                content_folder_entities_by_id[folder_id] = folder_entity

        # stash context values, works only for single representation
        init_folder_id = None
        init_product_name = None
        init_repre_name = None
        if len(repre_entities) == 1:
            init_repre_entity = repre_entities[0]
            init_version_entity = content_version_entities_by_id.get(
                init_repre_entity["versionId"])
            init_product_entity = None
            init_folder_entity = None
            if init_version_entity:
                init_product_entity = content_product_entities_by_id.get(
                    init_version_entity["productId"]
                )
            if init_product_entity:
                init_folder_entity = content_folder_entities_by_id.get(
                    init_product_entity["folderId"]
                )
            if init_folder_entity:
                init_repre_name = init_repre_entity["name"]
                init_product_name = init_product_entity["name"]
                init_folder_id = init_folder_entity["id"]

        self._init_folder_id = init_folder_id
        self._init_product_name = init_product_name
        self._init_repre_name = init_repre_name

        self._folder_entities_by_id = content_folder_entities_by_id
        self._product_entities_by_id = content_product_entities_by_id
        self._version_entities_by_id = content_version_entities_by_id
        self._repre_entities_by_id = content_repre_entities_by_id

        self._missing_folder_ids = missing_folder_ids
        self._missing_product_ids = missing_product_ids
        self._missing_version_ids = missing_version_ids
        self._missing_repre_ids = missing_repre_ids
        self._missing_entities = (
            bool(missing_folder_ids)
            or bool(missing_version_ids)
            or bool(missing_product_ids)
            or bool(missing_repre_ids)
        )

        self._inactive_folder_ids = inactive_folder_ids
        self._inactive_product_ids = inactive_product_ids
        self._inactive_repre_ids = inactive_repre_ids

    def _combobox_value_changed(self, *args, **kwargs):
        self.refresh()

    def _build_loaders_menu(self):
        repre_ids = self._get_current_output_repre_ids()
        loaders = self._get_loaders(repre_ids)
        # Get and destroy the action group
        self._accept_btn.clear_actions()

        if not loaders:
            return

        # Build new action group
        group = QtWidgets.QActionGroup(self._accept_btn)

        for loader in loaders:
            # Label
            label = getattr(loader, "label", None)
            if label is None:
                label = loader.__name__

            action = group.addAction(label)
            # action = QtWidgets.QAction(label)
            action.setData(loader)

            # Support font-awesome icons using the `.icon` and `.color`
            # attributes on plug-ins.
            icon = getattr(loader, "icon", None)
            if icon is not None:
                try:
                    key = "fa.{0}".format(icon)
                    color = getattr(loader, "color", "white")
                    action.setIcon(qtawesome.icon(key, color=color))

                except Exception as exc:
                    print("Unable to set icon for loader {}: {}".format(
                        loader, str(exc)
                    ))

            self._accept_btn.add_action(action)

        group.triggered.connect(self._on_action_clicked)

    def _on_action_clicked(self, action):
        loader_plugin = action.data()
        self._trigger_switch(loader_plugin)

    def _get_loaders(self, repre_ids):
        repre_contexts = None
        if repre_ids:
            repre_contexts = get_repres_contexts(repre_ids)

        if not repre_contexts:
            return list()

        available_loaders = []
        for loader_plugin in discover_loader_plugins():
            # Skip loaders without switch method
            if not hasattr(loader_plugin, "switch"):
                continue

            # Skip utility loaders
            if (
                hasattr(loader_plugin, "is_utility")
                and loader_plugin.is_utility
            ):
                continue
            available_loaders.append(loader_plugin)

        loaders = None
        for repre_context in repre_contexts.values():
            _loaders = set(loaders_from_repre_context(
                available_loaders, repre_context
            ))
            if loaders is None:
                loaders = _loaders
            else:
                loaders = _loaders.intersection(loaders)

            if not loaders:
                break

        if loaders is None:
            loaders = []
        else:
            loaders = list(loaders)

        return loaders

    def _fill_combobox(self, values, combobox_type):
        if combobox_type == "product":
            combobox_widget = self._products_combox
        elif combobox_type == "repre":
            combobox_widget = self._representations_box
        else:
            return
        selected_value = combobox_widget.get_valid_value()

        # Fill combobox
        if values is not None:
            combobox_widget.populate(list(sorted(values)))
            if selected_value and selected_value in values:
                index = None
                for idx in range(combobox_widget.count()):
                    if selected_value == str(combobox_widget.itemText(idx)):
                        index = idx
                        break
                if index is not None:
                    combobox_widget.setCurrentIndex(index)

    def _set_style_property(self, widget, name, value):
        cur_value = widget.property(name)
        if cur_value == value:
            return
        widget.setProperty(name, value)
        widget.style().polish(widget)

    def _get_current_output_repre_ids(self):
        # NOTE hero versions are not used because it is expected that
        # hero version has same representations as latests
        selected_folder_id = self._folders_field.get_selected_folder_id()
        selected_product_name = self._products_combox.currentText()
        selected_repre = self._representations_box.currentText()

        # Nothing is selected
        # [ ] [ ] [ ]
        if (
            not selected_folder_id
            and not selected_product_name
            and not selected_repre
        ):
            return list(self._repre_entities_by_id.keys())

        # Everything is selected
        # [x] [x] [x]
        if selected_folder_id and selected_product_name and selected_repre:
            return self._get_current_output_repre_ids_xxx(
                selected_folder_id, selected_product_name, selected_repre
            )

        # [x] [x] [ ]
        # If folder and product is selected
        if selected_folder_id and selected_product_name:
            return self._get_current_output_repre_ids_xxo(
                selected_folder_id, selected_product_name
            )

        # [x] [ ] [x]
        # If folder and repre is selected
        if selected_folder_id and selected_repre:
            return self._get_current_output_repre_ids_xox(
                selected_folder_id, selected_repre
            )

        # [x] [ ] [ ]
        # If folder and product is selected
        if selected_folder_id:
            return self._get_current_output_repre_ids_xoo(selected_folder_id)

        # [ ] [x] [x]
        if selected_product_name and selected_repre:
            return self._get_current_output_repre_ids_oxx(
                selected_product_name, selected_repre
            )

        # [ ] [x] [ ]
        if selected_product_name:
            return self._get_current_output_repre_ids_oxo(
                selected_product_name
            )

        # [ ] [ ] [x]
        return self._get_current_output_repre_ids_oox(selected_repre)

    def _get_current_output_repre_ids_xxx(
        self, folder_id, selected_product_name, selected_repre
    ):
        project_name = self._project_name
        product_entity = ayon_api.get_product_by_name(
            project_name,
            selected_product_name,
            folder_id,
            fields={"id"}
        )

        product_id = product_entity["id"]
        last_versions_by_product_id = self.find_last_versions([product_id])
        version_entity = last_versions_by_product_id.get(product_id)
        if not version_entity:
            return []

        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids={version_entity["id"]},
            representation_names={selected_repre},
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_xxo(self, folder_id, product_name):
        project_name = self._project_name
        product_entity = ayon_api.get_product_by_name(
            project_name,
            product_name,
            folder_id,
            fields={"id"}
        )
        if not product_entity:
            return []

        repre_names = set()
        for repre_entity in self._repre_entities_by_id.values():
            repre_names.add(repre_entity["name"])

        # TODO where to take version ids?
        version_ids = []
        repre_entities = ayon_api.get_representations(
            project_name,
            representation_names=repre_names,
            version_ids=version_ids,
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_xox(self, folder_id, selected_repre):
        product_names = {
            product_entity["name"]
            for product_entity in self._product_entities_by_id.values()
        }

        project_name = self._project_name
        product_entities = ayon_api.get_products(
            project_name,
            folder_ids=[folder_id],
            product_names=product_names,
            fields={"id", "name"}
        )
        product_name_by_id = {
            product_entity["id"]: product_entity["name"]
            for product_entity in product_entities
        }
        product_ids = list(product_name_by_id.keys())
        last_versions_by_product_id = self.find_last_versions(product_ids)
        last_version_id_by_product_name = {}
        for product_id, last_version in last_versions_by_product_id.items():
            product_name = product_name_by_id[product_id]
            last_version_id_by_product_name[product_name] = (
                last_version["id"]
            )

        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=last_version_id_by_product_name.values(),
            representation_names={selected_repre},
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_xoo(self, folder_id):
        project_name = self._project_name
        repres_by_product_name = collections.defaultdict(set)
        for repre_entity in self._repre_entities_by_id.values():
            version_id = repre_entity["versionId"]
            version_entity = self._version_entities_by_id[version_id]
            product_id = version_entity["productId"]
            product_entity = self._product_entities_by_id[product_id]
            product_name = product_entity["name"]
            repres_by_product_name[product_name].add(repre_entity["name"])

        product_entities = list(ayon_api.get_products(
            project_name,
            folder_ids=[folder_id],
            product_names=repres_by_product_name.keys(),
            fields={"id", "name"}
        ))
        product_name_by_id = {
            product_entity["id"]: product_entity["name"]
            for product_entity in product_entities
        }
        product_ids = list(product_name_by_id.keys())
        last_versions_by_product_id = self.find_last_versions(product_ids)
        last_version_id_by_product_name = {}
        for product_id, last_version in last_versions_by_product_id.items():
            product_name = product_name_by_id[product_id]
            last_version_id_by_product_name[product_name] = (
                last_version["id"]
            )

        repre_names_by_version_id = {}
        for product_name, repre_names in repres_by_product_name.items():
            version_id = last_version_id_by_product_name.get(product_name)
            # This should not happen but why to crash?
            if version_id is not None:
                repre_names_by_version_id[version_id] = list(repre_names)

        repre_entities = ayon_api.get_representations(
            project_name,
            names_by_version_ids=repre_names_by_version_id,
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_oxx(
        self, product_name, selected_repre
    ):
        project_name = self._project_name
        product_entities = ayon_api.get_products(
            project_name,
            folder_ids=self._folder_entities_by_id.keys(),
            product_names=[product_name],
            fields={"id"}
        )
        product_ids = {
            product_entity["id"] for product_entity in product_entities
        }
        last_versions_by_product_id = self.find_last_versions(product_ids)
        last_version_ids = {
            last_version["id"]
            for last_version in last_versions_by_product_id.values()
        }

        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=last_version_ids,
            representation_names={selected_repre},
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_oxo(self, product_name):
        project_name = self._project_name
        product_entities = ayon_api.get_products(
            project_name,
            folder_ids=self._folder_entities_by_id.keys(),
            product_names={product_name},
            fields={"id", "folderId"}
        )
        product_entities_by_id = {
            product_entity["id"]: product_entity
            for product_entity in product_entities
        }
        if not product_entities_by_id:
            return list()

        last_versions_by_product_id = self.find_last_versions(
            product_entities_by_id.keys()
        )

        product_id_by_version_id = {}
        for product_id, last_version in last_versions_by_product_id.items():
            version_id = last_version["id"]
            product_id_by_version_id[version_id] = product_id

        if not product_id_by_version_id:
            return list()

        repre_names_by_folder_id = collections.defaultdict(set)
        for repre_entity in self._repre_entities_by_id.values():
            version_id = repre_entity["versionId"]
            version_entity = self._version_entities_by_id[version_id]
            product_id = version_entity["productId"]
            product_entity = self._product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            folder_entity = self._folder_entities_by_id[folder_id]
            folder_id = folder_entity["id"]
            repre_names_by_folder_id[folder_id].add(repre_entity["name"])

        repre_names_by_version_id = {}
        for last_version_id, product_id in product_id_by_version_id.items():
            product_entity = product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            repre_names = repre_names_by_folder_id.get(folder_id)
            if not repre_names:
                continue
            repre_names_by_version_id[last_version_id] = repre_names

        repre_entities = ayon_api.get_representations(
            project_name,
            names_by_version_ids=repre_names_by_version_id,
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_current_output_repre_ids_oox(self, selected_repre):
        project_name = self._project_name
        repre_entities = ayon_api.get_representations(
            project_name,
            representation_names=[selected_repre],
            version_ids=self._version_entities_by_id.keys(),
            fields={"id"}
        )
        return {repre_entity["id"] for repre_entity in repre_entities}

    def _get_product_box_values(self):
        project_name = self._project_name
        selected_folder_id = self._folders_field.get_selected_folder_id()
        if selected_folder_id:
            folder_ids = [selected_folder_id]
        else:
            folder_ids = list(self._folder_entities_by_id.keys())

        product_entities = ayon_api.get_products(
            project_name,
            folder_ids=folder_ids,
            fields={"folderId", "name"}
        )

        product_names_by_parent_id = collections.defaultdict(set)
        for product_entity in product_entities:
            product_names_by_parent_id[product_entity["folderId"]].add(
                product_entity["name"]
            )

        possible_product_names = None
        for product_names in product_names_by_parent_id.values():
            if possible_product_names is None:
                possible_product_names = product_names
            else:
                possible_product_names = possible_product_names.intersection(
                    product_names)

            if not possible_product_names:
                break

        if not possible_product_names:
            return []
        return list(possible_product_names)

    def _representations_box_values(self):
        # NOTE hero versions are not used because it is expected that
        # hero version has same representations as latests
        project_name = self._project_name
        selected_folder_id = self._folders_field.get_selected_folder_id()
        selected_product_name = self._products_combox.currentText()

        # If nothing is selected
        # [ ] [ ] [?]
        if not selected_folder_id and not selected_product_name:
            # Find all representations of selection's products
            possible_repres = ayon_api.get_representations(
                project_name,
                version_ids=self._version_entities_by_id.keys(),
                fields={"versionId", "name"}
            )

            possible_repres_by_parent = collections.defaultdict(set)
            for repre in possible_repres:
                possible_repres_by_parent[repre["versionId"]].add(
                    repre["name"]
                )

            output_repres = None
            for repre_names in possible_repres_by_parent.values():
                if output_repres is None:
                    output_repres = repre_names
                else:
                    output_repres = (output_repres & repre_names)

                if not output_repres:
                    break

            return list(output_repres or list())

        # [x] [x] [?]
        if selected_folder_id and selected_product_name:
            product_entity = ayon_api.get_product_by_name(
                project_name,
                selected_product_name,
                selected_folder_id,
                fields={"id"}
            )

            product_id = product_entity["id"]
            last_versions_by_product_id = self.find_last_versions([product_id])
            version_entity = last_versions_by_product_id.get(product_id)
            repre_entities = ayon_api.get_representations(
                project_name,
                version_ids={version_entity["id"]},
                fields={"name"}
            )
            return {
                repre_entity["name"]
                for repre_entity in repre_entities
            }

        # [x] [ ] [?]
        # If only folder is selected
        if selected_folder_id:
            # Filter products by names from content
            product_names = {
                product_entity["name"]
                for product_entity in self._product_entities_by_id.values()
            }

            product_entities = ayon_api.get_products(
                project_name,
                folder_ids={selected_folder_id},
                product_names=product_names,
                fields={"id"}
            )
            product_ids = {
                product_entity["id"]
                for product_entity in product_entities
            }
            if not product_ids:
                return list()

            last_versions_by_product_id = self.find_last_versions(product_ids)
            product_id_by_version_id = {}
            for product_id, last_version in (
                last_versions_by_product_id.items()
            ):
                version_id = last_version["id"]
                product_id_by_version_id[version_id] = product_id

            if not product_id_by_version_id:
                return list()

            repre_entities = list(ayon_api.get_representations(
                project_name,
                version_ids=product_id_by_version_id.keys(),
                fields={"name", "versionId"}
            ))
            if not repre_entities:
                return list()

            repre_names_by_parent = collections.defaultdict(set)
            for repre_entity in repre_entities:
                repre_names_by_parent[repre_entity["versionId"]].add(
                    repre_entity["name"]
                )

            available_repres = None
            for repre_names in repre_names_by_parent.values():
                if available_repres is None:
                    available_repres = repre_names
                    continue

                available_repres = available_repres.intersection(repre_names)

            return list(available_repres)

        # [ ] [x] [?]
        product_entities = list(ayon_api.get_products(
            project_name,
            folder_ids=self._folder_entities_by_id.keys(),
            product_names=[selected_product_name],
            fields={"id", "folderId"}
        ))
        if not product_entities:
            return list()

        product_entities_by_id = {
            product_entity["id"]: product_entity
            for product_entity in product_entities
        }
        last_versions_by_product_id = self.find_last_versions(
            product_entities_by_id.keys()
        )

        product_id_by_version_id = {}
        for product_id, last_version in last_versions_by_product_id.items():
            version_id = last_version["id"]
            product_id_by_version_id[version_id] = product_id

        if not product_id_by_version_id:
            return list()

        repre_entities = list(
            ayon_api.get_representations(
                project_name,
                version_ids=product_id_by_version_id.keys(),
                fields={"name", "versionId"}
            )
        )
        if not repre_entities:
            return list()

        repre_names_by_folder_id = collections.defaultdict(set)
        for repre_entity in repre_entities:
            product_id = product_id_by_version_id[repre_entity["versionId"]]
            folder_id = product_entities_by_id[product_id]["folderId"]
            repre_names_by_folder_id[folder_id].add(repre_entity["name"])

        available_repres = None
        for repre_names in repre_names_by_folder_id.values():
            if available_repres is None:
                available_repres = repre_names
                continue

            available_repres = available_repres.intersection(repre_names)

        return list(available_repres)

    def _is_folder_ok(self, validation_state):
        selected_folder_id = self._folders_field.get_selected_folder_id()
        if (
            selected_folder_id is None
            and (self._missing_entities or self._inactive_folder_ids)
        ):
            validation_state.folder_ok = False

    def _is_product_ok(self, validation_state):
        selected_folder_id = self._folders_field.get_selected_folder_id()
        selected_product_name = self._products_combox.get_valid_value()

        # [?] [x] [?]
        # If product is selected then must be ok
        if selected_product_name is not None:
            return

        # [ ] [ ] [?]
        if selected_folder_id is None:
            # If there were archived products and folder is not selected
            if self._inactive_product_ids:
                validation_state.product_ok = False
            return

        # [x] [ ] [?]
        project_name = self._project_name
        product_entities = ayon_api.get_products(
            project_name, folder_ids=[selected_folder_id], fields={"name"}
        )

        product_names = set(
            product_entity["name"]
            for product_entity in product_entities
        )

        for product_entity in self._product_entities_by_id.values():
            if product_entity["name"] not in product_names:
                validation_state.product_ok = False
                break

    def _is_repre_ok(self, validation_state):
        selected_folder_id = self._folders_field.get_selected_folder_id()
        selected_product_name = self._products_combox.get_valid_value()
        selected_repre = self._representations_box.get_valid_value()

        # [?] [?] [x]
        # If product is selected then must be ok
        if selected_repre is not None:
            return

        # [ ] [ ] [ ]
        if selected_folder_id is None and selected_product_name is None:
            if (
                self._inactive_repre_ids
                or self._missing_version_ids
                or self._missing_repre_ids
            ):
                validation_state.repre_ok = False
            return

        # [x] [x] [ ]
        project_name = self._project_name
        if (
            selected_folder_id is not None
            and selected_product_name is not None
        ):
            product_entity = ayon_api.get_product_by_name(
                project_name,
                selected_product_name,
                selected_folder_id,
                fields={"id"}
            )
            product_id = product_entity["id"]
            last_versions_by_product_id = self.find_last_versions([product_id])
            last_version = last_versions_by_product_id.get(product_id)
            if not last_version:
                validation_state.repre_ok = False
                return

            repre_entities = ayon_api.get_representations(
                project_name,
                version_ids={last_version["id"]},
                fields={"name"}
            )

            repre_names = set(
                repre_entity["name"]
                for repre_entity in repre_entities
            )
            for repre_entity in self._repre_entities_by_id.values():
                if repre_entity["name"] not in repre_names:
                    validation_state.repre_ok = False
                    break
            return

        # [x] [ ] [ ]
        if selected_folder_id is not None:
            product_entities = list(ayon_api.get_products(
                project_name,
                folder_ids={selected_folder_id},
                fields={"id", "name"}
            ))

            product_name_by_id = {}
            product_ids = set()
            for product_entity in product_entities:
                product_id = product_entity["id"]
                product_ids.add(product_id)
                product_name_by_id[product_id] = product_entity["name"]

            last_versions_by_product_id = self.find_last_versions(product_ids)

            product_id_by_version_id = {}
            for product_id, last_version in (
                last_versions_by_product_id.items()
            ):
                version_id = last_version["id"]
                product_id_by_version_id[version_id] = product_id

            repre_entities = ayon_api.get_representations(
                project_name,
                version_ids=product_id_by_version_id.keys(),
                fields={"name", "versionId"}
            )
            repres_by_product_name = collections.defaultdict(set)
            for repre_entity in repre_entities:
                version_id = repre_entity["versionId"]
                product_id = product_id_by_version_id[version_id]
                product_name = product_name_by_id[product_id]
                repres_by_product_name[product_name].add(repre_entity["name"])

            for repre_entity in self._repre_entities_by_id.values():
                version_id = repre_entity["versionId"]
                version_entity = self._version_entities_by_id[version_id]
                product_id = version_entity["productId"]
                product_entity = self._product_entities_by_id[product_id]
                repre_names = repres_by_product_name[product_entity["name"]]
                if repre_entity["name"] not in repre_names:
                    validation_state.repre_ok = False
                    break
            return

        # [ ] [x] [ ]
        # Product entities
        product_entities = ayon_api.get_products(
            project_name,
            folder_ids=self._folder_entities_by_id.keys(),
            product_names={selected_product_name},
            fields={"id", "name", "folderId"}
        )
        product_entities_by_id = {}
        for product_entity in product_entities:
            product_entities_by_id[product_entity["id"]] = product_entity

        last_versions_by_product_id = self.find_last_versions(
            product_entities_by_id.keys()
        )
        product_id_by_version_id = {}
        for product_id, last_version in last_versions_by_product_id.items():
            version_id = last_version["id"]
            product_id_by_version_id[version_id] = product_id

        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=product_id_by_version_id.keys(),
            fields={"name", "versionId"}
        )
        repres_by_folder_id = collections.defaultdict(set)
        for repre_entity in repre_entities:
            product_id = product_id_by_version_id[repre_entity["versionId"]]
            folder_id = product_entities_by_id[product_id]["folderId"]
            repres_by_folder_id[folder_id].add(repre_entity["name"])

        for repre_entity in self._repre_entities_by_id.values():
            version_id = repre_entity["versionId"]
            version_entity = self._version_entities_by_id[version_id]
            product_id = version_entity["productId"]
            product_entity = self._product_entities_by_id[product_id]
            folder_id = product_entity["folderId"]
            repre_names = repres_by_folder_id[folder_id]
            if repre_entity["name"] not in repre_names:
                validation_state.repre_ok = False
                break

    def _on_current_folder(self):
        # Set initial folder as current.
        folder_id = self._controller.get_current_folder_id()
        if not folder_id:
            return

        selected_folder_id = self._folders_field.get_selected_folder_id()
        if folder_id == selected_folder_id:
            return

        self._folders_field.set_selected_item(folder_id)
        self._combobox_value_changed()

    def _on_accept(self):
        self._trigger_switch()

    def _trigger_switch(self, loader=None):
        # Use None when not a valid value or when placeholder value
        selected_folder_id = self._folders_field.get_selected_folder_id()
        selected_product_name = self._products_combox.get_valid_value()
        selected_representation = self._representations_box.get_valid_value()

        project_name = self._project_name
        if selected_folder_id:
            folder_ids = {selected_folder_id}
        else:
            folder_ids = set(self._folder_entities_by_id.keys())

        product_names = None
        if selected_product_name:
            product_names = [selected_product_name]

        product_entities = list(ayon_api.get_products(
            project_name,
            product_names=product_names,
            folder_ids=folder_ids
        ))
        product_ids = set()
        product_entities_by_parent_and_name = collections.defaultdict(dict)
        for product_entity in product_entities:
            product_ids.add(product_entity["id"])
            folder_id = product_entity["folderId"]
            name = product_entity["name"]
            product_entities_by_parent_and_name[folder_id][name] = (
                product_entity
            )

        # versions
        _version_entities = ayon_api.get_versions(
            project_name, product_ids=product_ids
        )
        version_entities = list(reversed(
            sorted(_version_entities, key=lambda item: item["version"])
        ))

        version_ids = set()
        version_entities_by_product_id = collections.defaultdict(dict)
        hero_version_entities_by_product_id = {}
        for version_entity in version_entities:
            version_ids.add(version_entity["id"])
            product_id = version_entity["productId"]
            version = version_entity["version"]
            if version < 0:
                hero_version_entities_by_product_id[product_id] = (
                    version_entity
                )
                continue
            version_entities_by_product_id[product_id][version] = (
                version_entity
            )

        repre_entities = ayon_api.get_representations(
            project_name, version_ids=version_ids
        )
        repre_entities_by_name_version_id = collections.defaultdict(dict)
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            name = repre_entity["name"]
            repre_entities_by_name_version_id[version_id][name] = repre_entity

        for container in self._items:
            self._switch_container(
                container,
                loader,
                selected_folder_id,
                selected_product_name,
                selected_representation,
                product_entities_by_parent_and_name,
                version_entities_by_product_id,
                hero_version_entities_by_product_id,
                repre_entities_by_name_version_id,
            )

        self.switched.emit()

        self.close()

    def _switch_container(
        self,
        container,
        loader,
        selected_folder_id,
        selected_product_name,
        selected_representation,
        product_entities_by_parent_and_name,
        version_entities_by_product_id,
        hero_version_entities_by_product_id,
        repre_entities_by_name_version_id,
    ):
        container_repre_id = container["representation"]
        container_repre = self._repre_entities_by_id[container_repre_id]
        container_repre_name = container_repre["name"]
        container_version_id = container_repre["versionId"]

        container_version = self._version_entities_by_id[container_version_id]

        container_product_id = container_version["productId"]
        container_product = self._product_entities_by_id[container_product_id]
        container_product_name = container_product["name"]

        container_folder_id = container_product["folderId"]

        if selected_folder_id:
            folder_id = selected_folder_id
        else:
            folder_id = container_folder_id

        products_by_name = product_entities_by_parent_and_name[folder_id]
        if selected_product_name:
            product_entity = products_by_name[selected_product_name]
        else:
            product_entity = products_by_name[container_product["name"]]

        repre_entity = None
        product_id = product_entity["id"]
        if container_version["version"] < 0:
            hero_version = hero_version_entities_by_product_id.get(
                product_id
            )
            if hero_version:
                _repres = repre_entities_by_name_version_id.get(
                    hero_version["id"]
                )
                if selected_representation:
                    repre_entity = _repres.get(selected_representation)
                else:
                    repre_entity = _repres.get(container_repre_name)

        if not repre_entity:
            version_entities_by_version = (
                version_entities_by_product_id[product_id]
            )
            # If folder or product are selected for switching, we use latest
            # version else we try to keep the current container version.
            version = None
            if (
                selected_folder_id in (None, container_folder_id)
                and selected_product_name in (None, container_product_name)
            ):
                version = container_version.get("version")

            version_entity = None
            if version is not None:
                version_entity = version_entities_by_version.get(version)

            if version_entity is None:
                version_name = max(version_entities_by_version)
                version_entity = version_entities_by_version[version_name]

            version_id = version_entity["id"]
            repres_by_name = repre_entities_by_name_version_id[version_id]
            if selected_representation:
                repre_entity = repres_by_name[selected_representation]
            else:
                repre_entity = repres_by_name[container_repre_name]

        error = None
        try:
            switch_container(container, repre_entity, loader)
        except (
            LoaderSwitchNotImplementedError,
            IncompatibleLoaderError,
            LoaderNotFoundError,
        ) as exc:
            error = str(exc)
        except Exception:
            error = (
                "Switch asset failed. "
                "Search console log for more details."
            )
        if error is not None:
            log.warning((
                "Couldn't switch asset."
                "See traceback for more information."
            ), exc_info=True)
            dialog = QtWidgets.QMessageBox(self)
            dialog.setWindowTitle("Switch asset failed")
            dialog.setText(error)
            dialog.exec_()
