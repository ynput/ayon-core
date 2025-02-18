import platform
from collections import defaultdict

import ayon_api
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import resources, style
from ayon_core.lib import (
    format_file_size,
    collect_frames,
    get_datetime_data,
)
from ayon_core.pipeline import load, Anatomy
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.delivery import (
    get_format_dict,
    check_destination_path,
    deliver_single_file,
    get_representations_delivery_template_data,
)


class Delivery(load.ProductLoaderPlugin):
    """Export selected versions to folder structure from Template"""

    is_multiple_contexts_compatible = True
    sequence_splitter = "__sequence_splitter__"

    representations = {"*"}
    product_types = {"*"}
    tool_names = ["library_loader"]

    label = "Deliver Versions"
    order = 35
    icon = "upload"
    color = "#d8d8d8"

    def message(self, text):
        msgBox = QtWidgets.QMessageBox()
        msgBox.setText(text)
        msgBox.setStyleSheet(style.load_stylesheet())
        msgBox.setWindowFlags(
            msgBox.windowFlags() | QtCore.Qt.FramelessWindowHint
        )
        msgBox.exec_()

    def load(self, contexts, name=None, namespace=None, options=None):
        try:
            dialog = DeliveryOptionsDialog(contexts, self.log)
            dialog.exec_()
        except Exception:
            self.log.error("Failed to deliver versions.", exc_info=True)


class DeliveryOptionsDialog(QtWidgets.QDialog):
    """Dialog to select template where to deliver selected representations."""

    def __init__(self, contexts, log=None, parent=None):
        super(DeliveryOptionsDialog, self).__init__(parent=parent)

        self.setWindowTitle("AYON - Deliver versions")
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setStyleSheet(style.load_stylesheet())

        project_name = contexts[0]["project"]["name"]
        self.anatomy = Anatomy(project_name)
        self._representations = None
        self.log = log
        self.currently_uploaded = 0

        self._set_representations(project_name, contexts)

        dropdown = QtWidgets.QComboBox()
        self.templates = self._get_templates(self.anatomy)
        for name, _ in self.templates.items():
            dropdown.addItem(name)
        if self.templates and platform.system() == "Darwin":
            # fix macos QCombobox Style
            dropdown.setItemDelegate(QtWidgets.QStyledItemDelegate())
            # update combo box length to longest entry
            longest_key = max(self.templates.keys(), key=len)
            dropdown.setMinimumContentsLength(len(longest_key))

        template_dir_label = QtWidgets.QLabel()
        template_dir_label.setCursor(QtGui.QCursor(QtCore.Qt.IBeamCursor))
        template_dir_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse)

        template_file_label = QtWidgets.QLabel()
        template_file_label.setCursor(QtGui.QCursor(QtCore.Qt.IBeamCursor))
        template_file_label.setTextInteractionFlags(
            QtCore.Qt.TextSelectableByMouse)

        renumber_frame = QtWidgets.QCheckBox()

        first_frame_start = QtWidgets.QSpinBox()
        max_int = (1 << 32) // 2
        first_frame_start.setRange(0, max_int - 1)

        root_line_edit = QtWidgets.QLineEdit()

        repre_checkboxes_layout = QtWidgets.QFormLayout()
        repre_checkboxes_layout.setContentsMargins(10, 5, 5, 10)

        self._representation_checkboxes = {}
        for repre in self._get_representation_names():
            checkbox = QtWidgets.QCheckBox()
            checkbox.setChecked(False)
            self._representation_checkboxes[repre] = checkbox

            checkbox.stateChanged.connect(self._update_selected_label)
            repre_checkboxes_layout.addRow(repre, checkbox)

        selected_label = QtWidgets.QLabel()

        input_widget = QtWidgets.QWidget(self)
        input_layout = QtWidgets.QFormLayout(input_widget)
        input_layout.setContentsMargins(10, 15, 5, 5)

        input_layout.addRow("Selected representations", selected_label)
        input_layout.addRow("Delivery template", dropdown)
        input_layout.addRow("Directory template", template_dir_label)
        input_layout.addRow("File template", template_file_label)
        input_layout.addRow("Renumber Frame", renumber_frame)
        input_layout.addRow("Renumber start frame", first_frame_start)
        input_layout.addRow("Root", root_line_edit)
        input_layout.addRow("Representations", repre_checkboxes_layout)

        btn_delivery = QtWidgets.QPushButton("Deliver")
        btn_delivery.setEnabled(False)

        progress_bar = QtWidgets.QProgressBar(self)
        progress_bar.setMinimum = 0
        progress_bar.setMaximum = 100
        progress_bar.setVisible(False)

        text_area = QtWidgets.QTextEdit()
        text_area.setReadOnly(True)
        text_area.setVisible(False)
        text_area.setMinimumHeight(100)

        layout = QtWidgets.QVBoxLayout(self)

        layout.addWidget(input_widget)
        layout.addStretch(1)
        layout.addWidget(btn_delivery)
        layout.addWidget(progress_bar)
        layout.addWidget(text_area)

        self.selected_label = selected_label
        self.template_dir_label = template_dir_label
        self.template_file_label = template_file_label
        self.dropdown = dropdown
        self.first_frame_start = first_frame_start
        self.renumber_frame = renumber_frame
        self.root_line_edit = root_line_edit
        self.progress_bar = progress_bar
        self.text_area = text_area
        self.btn_delivery = btn_delivery

        self.files_selected, self.size_selected = \
            self._get_counts(self._get_selected_repres())

        self._update_selected_label()
        self._update_template_value()

        btn_delivery.clicked.connect(self.deliver)
        dropdown.currentIndexChanged.connect(self._update_template_value)

        if not self.dropdown.count():
            self.text_area.setVisible(True)
            error_message = (
                "No Delivery Templates found!\n"
                "Add Template in [project_anatomy/templates/delivery]"
            )
            self.text_area.setText(error_message)
            self.log.error(error_message.replace("\n", " "))

    def deliver(self):
        """Main method to loop through all selected representations"""
        self.progress_bar.setVisible(True)
        self.btn_delivery.setEnabled(False)
        QtWidgets.QApplication.processEvents()

        report_items = defaultdict(list)

        selected_repres = self._get_selected_repres()

        datetime_data = get_datetime_data()
        template_name = self.dropdown.currentText()
        format_dict = get_format_dict(self.anatomy, self.root_line_edit.text())
        renumber_frame = self.renumber_frame.isChecked()
        frame_offset = self.first_frame_start.value()
        filtered_repres = []
        repre_ids = set()
        for repre in self._representations:
            if repre["name"] in selected_repres:
                filtered_repres.append(repre)
                repre_ids.add(repre["id"])

        template_data_by_repre_id = (
            get_representations_delivery_template_data(
                self.anatomy.project_name, repre_ids
            )
        )
        for repre in filtered_repres:
            repre_path = get_representation_path_with_anatomy(
                repre, self.anatomy
            )

            template_data = template_data_by_repre_id[repre["id"]]
            new_report_items = check_destination_path(
                repre["id"],
                self.anatomy,
                template_data,
                datetime_data,
                template_name
            )

            report_items.update(new_report_items)
            if new_report_items:
                continue

            args = [
                repre_path,
                repre,
                self.anatomy,
                template_name,
                template_data,
                format_dict,
                report_items,
                self.log
            ]

            # TODO: This will currently incorrectly detect 'resources'
            #  that are published along with the publish, because those should
            #  not adhere to the template directly but are ingested in a
            #  customized way. For example, maya look textures or any publish
            #  that directly adds files into `instance.data["transfers"]`
            src_paths = []
            for repre_file in repre["files"]:
                src_path = self.anatomy.fill_root(repre_file["path"])
                src_paths.append(src_path)
            sources_and_frames = collect_frames(src_paths)

            frames = set(sources_and_frames.values())
            frames.discard(None)
            first_frame = None
            if frames:
                first_frame = min(frames)

            for src_path, frame in sources_and_frames.items():
                args[0] = src_path
                # Renumber frames
                if renumber_frame and frame is not None:
                    # Calculate offset between
                    # first frame and current frame
                    # - '0' for first frame
                    offset = frame_offset - int(first_frame)
                    # Add offset to new frame start
                    dst_frame = int(frame) + offset
                    if dst_frame < 0:
                        msg = "Renumber frame has a smaller number than original frame"     # noqa
                        report_items[msg].append(src_path)
                        self.log.warning("{} <{}>".format(
                            msg, dst_frame))
                        continue
                    frame = dst_frame

                if frame is not None:
                    if repre["context"].get("frame"):
                        template_data["frame"] = frame
                    elif repre["context"].get("udim"):
                        template_data["udim"] = frame
                    else:
                        # Fallback
                        self.log.warning(
                            "Representation context has no frame or udim"
                            " data. Supplying sequence frame to '{frame}'"
                            " formatting data."
                        )
                        template_data["frame"] = frame
                new_report_items, uploaded = deliver_single_file(*args)
                report_items.update(new_report_items)
                self._update_progress(uploaded)

        self.text_area.setText(self._format_report(report_items))
        self.text_area.setVisible(True)

    def _get_representation_names(self):
        """Get set of representation names for checkbox filtering."""
        return set([repre["name"] for repre in self._representations])

    def _get_templates(self, anatomy):
        """Adds list of delivery templates from Anatomy to dropdown."""
        templates = {}
        for template_name, value in anatomy.templates["delivery"].items():
            directory_template = value["directory"]
            if not directory_template.startswith("{root"):
                self.log.warning(
                    "Skipping template '%s' because directory template does "
                    "not start with `{root` in value: %s",
                    template_name, directory_template
                )
                continue

            templates[template_name] = value

        return templates

    def _set_representations(self, project_name, contexts):
        version_ids = {context["version"]["id"] for context in contexts}

        repres = list(ayon_api.get_representations(
            project_name, version_ids=version_ids
        ))

        self._representations = repres

    def _get_counts(self, selected_repres=None):
        """Returns tuple of number of selected files and their size."""
        files_selected = 0
        size_selected = 0
        for repre in self._representations:
            if repre["name"] in selected_repres:
                files = repre.get("files", [])
                if not files:  # for repre without files, cannot divide by 0
                    files_selected += 1
                    size_selected += 0
                else:
                    for repre_file in files:
                        files_selected += 1
                        size_selected += repre_file["size"]

        return files_selected, size_selected

    def _prepare_label(self):
        """Provides text with no of selected files and their size."""
        label = "{} files, size {}".format(
            self.files_selected,
            format_file_size(self.size_selected))
        return label

    def _get_selected_repres(self):
        """Returns list of representation names filtered from checkboxes."""
        selected_repres = []
        for repre_name, checkbox in self._representation_checkboxes.items():
            if checkbox.isChecked():
                selected_repres.append(repre_name)

        return selected_repres

    def _update_selected_label(self):
        """Updates label with list of number of selected files."""
        selected_repres = self._get_selected_repres()
        self.files_selected, self.size_selected = \
            self._get_counts(selected_repres)
        self.selected_label.setText(self._prepare_label())
        # update delivery button state if any templates found
        if self.dropdown.count():
            self.btn_delivery.setEnabled(bool(selected_repres))

    def _update_template_value(self, _index=None):
        """Sets template value to label after selection in dropdown."""
        name = self.dropdown.currentText()
        template_value = self.templates.get(name)
        if template_value:
            self.template_dir_label.setText(template_value["directory"])
            self.template_file_label.setText(template_value["file"])
            self.btn_delivery.setEnabled(bool(self._get_selected_repres()))

    def _update_progress(self, uploaded):
        """Update progress bar after each repre copied."""
        self.currently_uploaded += uploaded

        ratio = self.currently_uploaded / self.files_selected
        self.progress_bar.setValue(ratio * self.progress_bar.maximum())

    def _format_report(self, report_items):
        """Format final result and error details as html."""
        msg = "Delivery finished"
        if not report_items:
            msg += " successfully"
        else:
            msg += " with errors"
        txt = "<h2>{}</h2>".format(msg)
        for header, data in report_items.items():
            txt += "<h3>{}</h3>".format(header)
            for item in data:
                txt += "{}<br>".format(item)

        return txt
