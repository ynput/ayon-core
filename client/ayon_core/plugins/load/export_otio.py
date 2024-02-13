from collections import defaultdict

from qtpy import QtWidgets, QtCore, QtGui

from ayon_core.client import (
    get_representations,
    get_version_by_id
)
from ayon_core.pipeline import load, Anatomy
from ayon_core import resources, style
from ayon_core.pipeline.editorial import export_otio
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.lib import run_subprocess


class ExportOTIO(load.SubsetLoaderPlugin):
    """Export selected versions to OpenTimelineIO."""

    is_multiple_contexts_compatible = True
    sequence_splitter = "__sequence_splitter__"

    representations = ["*"]
    families = ["*"]
    tool_names = ["library_loader"]

    label = "Export OTIO"
    order = 35
    icon = "save"
    color = "#d8d8d8"

    def load(self, contexts, name=None, namespace=None, options=None):
        try:
            dialog = ExportOTIOOptionsDialog(contexts, self.log)
            dialog.exec_()
        except Exception:
            self.log.error("Failed to export OTIO.", exc_info=True)


class ExportOTIOOptionsDialog(QtWidgets.QDialog):
    """Dialog to select template where to deliver selected representations."""

    def __init__(self, contexts, log=None, parent=None):
        super(ExportOTIOOptionsDialog, self).__init__(parent=parent)

        self.setWindowTitle("AYON - Export OTIO")
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setStyleSheet(style.load_stylesheet())

        input_widget = QtWidgets.QWidget(self)
        input_layout = QtWidgets.QGridLayout(input_widget)

        self._project_name = contexts[0]["project"]["name"]

        representations_by_version_id = defaultdict(list)
        self._version_by_representation_id = {}
        all_representation_names = set()
        self._version_path_by_id = {}
        for context in contexts:
            version_id = context["version"]["_id"]
            version = get_version_by_id(self._project_name, version_id)
            representations = list(get_representations(
                self._project_name, version_ids=[version_id]
            ))
            representations_by_version_id[version_id] = representations

            for representation in representations:
                all_representation_names.add(representation["name"])
                id = representation["_id"]
                self._version_by_representation_id[id] = version

            self._version_path_by_id[version_id] = "{}/{}/{}/v{:03d}".format(
                representations[0]["context"]["hierarchy"],
                representations[0]["context"]["asset"],
                representations[0]["context"]["subset"],
                representations[0]["context"]["version"]
            )

        all_representation_names = sorted(all_representation_names)

        input_layout.addWidget(QtWidgets.QLabel("Representations:"), 0, 0)
        toggle_all_checkboxes = {}
        for count, name in enumerate(all_representation_names):
            checkbox = QtWidgets.QCheckBox(name)
            input_layout.addWidget(
                checkbox,
                0,
                count + 1,
                alignment=QtCore.Qt.AlignCenter
            )
            toggle_all_checkboxes[name] = checkbox
            checkbox.stateChanged.connect(self.toggle_all)

        self._representation_checkboxes = defaultdict(list)
        row = 1
        items = representations_by_version_id.items()
        for version_id, representations in items:
            version_path = self._version_path_by_id[version_id]
            input_layout.addWidget(QtWidgets.QLabel(version_path), row, 0)

            representations_by_name = {x["name"]: x for x in representations}
            for count, name in enumerate(all_representation_names):
                checkbox = QtWidgets.QCheckBox()
                checkbox.setChecked(False)
                if name in representations_by_name.keys():
                    self._representation_checkboxes[name].append(
                        {
                            "checkbox": checkbox,
                            "representation": representations_by_name[name]
                        }
                    )
                else:
                    checkbox.setEnabled(False)

                input_layout.addWidget(
                    checkbox, row, count + 1, alignment=QtCore.Qt.AlignCenter
                )

            row += 1

        export_widget = QtWidgets.QWidget()
        export_layout = QtWidgets.QVBoxLayout(export_widget)

        widget = QtWidgets.QWidget()
        layout = QtWidgets.QHBoxLayout(widget)
        layout.addWidget(QtWidgets.QLabel("Output Path:"))
        self.lineedit_output_path = QtWidgets.QLineEdit()
        layout.addWidget(self.lineedit_output_path)
        export_layout.addWidget(widget)

        self.checkbox_inspect_otio_view = QtWidgets.QCheckBox(
            "Inspect with OTIO view"
        )
        export_layout.addWidget(self.checkbox_inspect_otio_view)

        self.btn_export = QtWidgets.QPushButton("Export")
        export_layout.addWidget(self.btn_export)

        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(input_widget)
        layout.addWidget(export_widget)

        self.btn_export.clicked.connect(self.export)

    def toggle_all(self, state):
        representation_name = self.sender().text()
        state = self.sender().checkState()
        for item in self._representation_checkboxes[representation_name]:
            item["checkbox"].setCheckState(state)

    def export(self):
        representations = []
        for name, items in self._representation_checkboxes.items():
            for item in items:
                check_state = item["checkbox"].checkState()
                if check_state == QtCore.Qt.CheckState.Checked:
                    representations.append(item["representation"])

        anatomy = Anatomy(self._project_name)
        clips_data = {}
        for representation in representations:
            version = self._version_by_representation_id[representation["_id"]]
            name = self._version_path_by_id[version["_id"]]
            clips_data[name] = {
                "path": get_representation_path_with_anatomy(
                    representation, anatomy
                ),
                "frames": (
                    version["data"]["frameEnd"] -
                    version["data"]["frameStart"]
                ),
                "framerate": version["data"]["fps"]
            }

        output_path = self.lineedit_output_path.text()
        export_otio(clips_data, output_path)

        check_state = self.checkbox_inspect_otio_view.checkState()
        if check_state == QtCore.Qt.CheckState.Checked:
            run_subprocess(["otioview", output_path])
