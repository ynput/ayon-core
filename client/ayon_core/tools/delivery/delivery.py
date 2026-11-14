from __future__ import annotations

import os
import copy
import html
import platform
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any, Iterator, Optional

import ayon_api
import clique
from qtpy import QtWidgets, QtCore, QtGui

from ayon_core import resources, style
from ayon_core.lib import (
    Logger,
    format_file_size,
    collect_frames,
    get_datetime_data,
)
from ayon_core.lib.icon_definitions import MaterialSymbolsIcon
from ayon_core.settings import get_project_settings
from ayon_core.pipeline import Anatomy

from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.pipeline.delivery import (
    DeliveryTemplateMatch,
    get_format_dict,
    check_destination_path,
    deliver_single_file,
    filter_delivery_template_names,
    get_delivery_template_profiles,
    get_delivery_tool_settings,
    get_representations_delivery_template_data,
    resolve_delivery_template,
)
from ayon_core.tools.utils import get_qt_icon

# Profile filter keys with labels used to explain why a profile matched
_PROFILE_FILTER_LABELS = (
    ("representation_names", "Representation names"),
    ("extensions", "Extensions"),
    ("product_base_types", "Product base types"),
)
_REPRE_NAME_COLUMN = 0
_REPRE_ICON_COLUMN = 1
# Item data roles of destination paths view
_GROUP_KEY_ROLE = QtCore.Qt.UserRole + 1
_PATH_ROLE = QtCore.Qt.UserRole + 2


@dataclass
class _DestinationGroup:
    """Destination paths of a representation name delivered by a template.

    Attributes:
        repre_name: Representation name.
        template_name: Delivery template used.
        is_override: Template differs from the template picked by user.
        paths: Destination paths, frame sequences collapsed.
        files_count: Number of files to deliver.
        errors: Reasons why some versions can't be delivered.
    """
    repre_name: str
    template_name: str
    is_override: bool
    paths: list[str] = field(default_factory=list)
    files_count: int = 0
    errors: list[str] = field(default_factory=list)


class DeliveryOptionsDialog(QtWidgets.QDialog):
    """Dialog to select template where to deliver selected representations."""

    def __init__(
        self,
        project_name,
        version_ids,
        list_entity_label=None,
        *,
        log=None,
        parent=None,
    ):
        super().__init__(parent=parent)

        if log is None:
            log = Logger.get_logger(__name__)

        self.setWindowTitle(f"Deliver {len(version_ids)} versions")
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )

        self.setStyleSheet(style.load_stylesheet())

        self.anatomy = Anatomy(project_name)
        self._representations = None
        self.log = log
        self.currently_uploaded = 0

        self._set_representations(project_name, version_ids)
        self._repres_by_name = defaultdict(list)
        for repre in self._representations:
            self._repres_by_name[repre["name"]].append(repre)
        project_settings = get_project_settings(project_name)
        self._template_profiles = get_delivery_template_profiles(
            project_settings
        )
        self._template_data_by_repre_id = (
            get_representations_delivery_template_data(
                project_name,
                {repre["id"] for repre in self._representations},
            )
        )
        self._override_color = style.get_objected_colors(
            "font-overridden"
        ).get_qcolor()
        self._error_color = style.get_objected_colors(
            "delete-btn-bg"
        ).get_qcolor()
        self._override_icon = get_qt_icon(
            MaterialSymbolsIcon(
                "alt_route", color=self._override_color.name()
            )
        )
        self._paths_dirty = True

        dropdown = QtWidgets.QComboBox()
        # All valid delivery templates, template profiles may use templates
        #   that are not offered in the dropdown
        self.templates = self._get_templates(self.anatomy)
        visible_template_names = filter_delivery_template_names(
            self.templates, get_delivery_tool_settings(project_settings)
        )
        for name in visible_template_names:
            dropdown.addItem(name)
        if visible_template_names and platform.system() == "Darwin":
            # fix macos QCombobox Style
            dropdown.setItemDelegate(QtWidgets.QStyledItemDelegate())
            # update combo box length to longest entry
            longest_key = max(visible_template_names, key=len)
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
        list_label_line_edit = QtWidgets.QLineEdit()

        # Collapsible "Advanced options" section, hidden by default
        advanced_toggle = self._create_section_toggle("Advanced options")

        advanced_widget = QtWidgets.QWidget(self)
        advanced_layout = QtWidgets.QFormLayout(advanced_widget)
        advanced_layout.setContentsMargins(10, 5, 5, 5)
        advanced_layout.addRow("Renumber Frame", renumber_frame)
        advanced_layout.addRow("Renumber start frame", first_frame_start)
        advanced_layout.addRow("Root", root_line_edit)
        advanced_layout.addRow("List label", list_label_line_edit)
        # set default value if `list_entity_label` arg is provided
        if list_entity_label:
            list_label_line_edit.setText(list_entity_label)
        advanced_widget.setVisible(False)

        def _on_advanced_toggled(checked):
            advanced_widget.setVisible(checked)
            advanced_toggle.setArrowType(
                QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
            )

        advanced_toggle.toggled.connect(_on_advanced_toggled)

        # Collapsible "Destination paths" section. Paths are computed only
        #   when expanded because it formats a path for every file.
        paths_toggle = self._create_section_toggle("Destination paths")

        # Group row per representation (collapsible), paths as children
        paths_view = QtWidgets.QTreeWidget()
        paths_view.setColumnCount(3)
        paths_view.setHeaderHidden(True)
        paths_view.setUniformRowHeights(True)
        paths_view.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        # Keep both root and filename of destination paths visible
        paths_view.setTextElideMode(QtCore.Qt.ElideMiddle)
        paths_view.setMinimumHeight(150)
        paths_view.setVisible(False)
        paths_header = paths_view.header()
        paths_header.setStretchLastSection(False)
        paths_header.setSectionResizeMode(
            0, QtWidgets.QHeaderView.Stretch)
        paths_header.setSectionResizeMode(
            1, QtWidgets.QHeaderView.ResizeToContents)
        paths_header.setSectionResizeMode(
            2, QtWidgets.QHeaderView.ResizeToContents)

        copy_paths_action = QtWidgets.QAction("Copy paths", paths_view)
        copy_paths_action.setShortcut(QtGui.QKeySequence.Copy)
        copy_paths_action.setShortcutContext(QtCore.Qt.WidgetShortcut)
        copy_paths_action.triggered.connect(self._copy_selected_paths)
        paths_view.addAction(copy_paths_action)
        paths_view.setContextMenuPolicy(QtCore.Qt.ActionsContextMenu)

        paths_timer = QtCore.QTimer(self)
        paths_timer.setSingleShot(True)
        paths_timer.setInterval(250)
        paths_timer.timeout.connect(self._refresh_paths_preview)

        paths_toggle.toggled.connect(self._on_paths_toggled)

        paths_widget = QtWidgets.QWidget(self)
        paths_layout = QtWidgets.QVBoxLayout(paths_widget)
        paths_layout.setContentsMargins(10, 0, 5, 5)
        paths_layout.addWidget(paths_toggle, 0, QtCore.Qt.AlignLeft)
        paths_layout.addWidget(paths_view, 1)

        btn_select_all = QtWidgets.QPushButton("Select All")

        # Representation names with an icon on the right when a template
        #   profile delivers it with another template than the picked one.
        repre_list = QtWidgets.QTreeWidget()
        repre_list.setColumnCount(2)
        repre_list.setHeaderHidden(True)
        repre_list.setRootIsDecorated(False)
        repre_list.setUniformRowHeights(True)
        repre_list.setSelectionMode(
            QtWidgets.QAbstractItemView.ExtendedSelection)
        repre_list.setSelectionBehavior(
            QtWidgets.QAbstractItemView.SelectRows)
        for repre in sorted(self._get_representation_names()):
            repre_list.addTopLevelItem(QtWidgets.QTreeWidgetItem([repre, ""]))
        header = repre_list.header()
        header.setStretchLastSection(False)
        header.setMinimumSectionSize(24)
        header.setSectionResizeMode(
            _REPRE_NAME_COLUMN, QtWidgets.QHeaderView.Stretch)
        header.setSectionResizeMode(
            _REPRE_ICON_COLUMN, QtWidgets.QHeaderView.Fixed)
        header.resizeSection(_REPRE_ICON_COLUMN, 24)

        repre_list.itemSelectionChanged.connect(self._update_selected_label)
        repre_list.itemSelectionChanged.connect(self._invalidate_paths)
        btn_select_all.clicked.connect(repre_list.selectAll)

        repre_widget = QtWidgets.QWidget(self)
        repre_layout = QtWidgets.QVBoxLayout(repre_widget)
        repre_layout.setContentsMargins(10, 5, 5, 10)
        repre_layout.addWidget(btn_select_all)
        repre_layout.addWidget(repre_list)

        selected_label = QtWidgets.QLabel()

        input_widget = QtWidgets.QWidget(self)
        input_layout = QtWidgets.QFormLayout(input_widget)
        input_layout.setContentsMargins(10, 15, 5, 5)

        input_layout.addRow("Selected representations", selected_label)
        input_layout.addRow("Delivery template", dropdown)
        input_layout.addRow("Directory template", template_dir_label)
        input_layout.addRow("File template", template_file_label)
        input_layout.addRow("Representations", repre_widget)
        input_layout.addRow(advanced_toggle)
        input_layout.addRow(advanced_widget)

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
        layout.addWidget(paths_widget, 0)
        # Empty space goes to destination paths when expanded
        layout.addStretch(1)
        stretch_index = layout.count() - 1
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
        self.list_label_line_edit = list_label_line_edit
        self.repre_list = repre_list
        self.paths_toggle = paths_toggle
        self.paths_view = paths_view
        self.paths_timer = paths_timer
        self._main_layout = layout
        self._paths_widget = paths_widget
        self._stretch_index = stretch_index
        self.progress_bar = progress_bar
        self.text_area = text_area
        self.btn_delivery = btn_delivery

        self.selected_repres_count, self.files_selected, self.size_selected = \
            self._get_counts(self._get_selected_repres())

        self._update_selected_label()
        self._update_template_value()

        btn_delivery.clicked.connect(self.deliver)
        dropdown.currentIndexChanged.connect(self._update_template_value)
        root_line_edit.textChanged.connect(self._invalidate_paths)
        list_label_line_edit.textChanged.connect(self._invalidate_paths)
        renumber_frame.toggled.connect(self._invalidate_paths)
        first_frame_start.valueChanged.connect(self._invalidate_paths)

        if not self.dropdown.count():
            self.text_area.setVisible(True)
            error_message = (
                "No Delivery Templates found!\n"
                "Add Template in [project_anatomy/templates/delivery]"
            )
            if self.templates:
                error_message = (
                    "No Delivery Templates to pick!\n"
                    "All templates are filtered out by project settings"
                    " [core/tools/delivery]"
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
        selected_template_name = self.dropdown.currentText()
        format_dict = get_format_dict(self.anatomy, self.root_line_edit.text())
        list_label = self.list_label_line_edit.text()
        renumber_frame = self.renumber_frame.isChecked()
        frame_offset = self.first_frame_start.value()
        filtered_repres = [
            repre
            for repre in self._representations
            if repre["name"] in selected_repres
        ]

        delivered_by_template = defaultdict(list)
        for repre in filtered_repres:
            match = self._resolve_template(repre, selected_template_name)
            template_name = match.template_name
            if template_name not in self.templates:
                msg = "Delivery template is not available in anatomy"
                report_items[msg].append(
                    "{}: {}".format(
                        template_name, self._get_repre_label(repre)
                    )
                )
                continue

            repre_path = get_representation_path_with_anatomy(
                repre, self.anatomy
            )

            template_data = self._get_repre_template_data(
                repre, list_label, datetime_data
            )

            # Use temporary placeholder so we don't need to check destination
            # path per file of the representation
            template_data["publishedFilename"] = "<publishedFilename>"
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

            repre_uploaded = 0
            for src_path, error in self._iter_repre_files(
                repre,
                template_data,
                renumber_frame,
                frame_offset,
                log_frame_fallback=True,
            ):
                if error:
                    report_items[error].append(src_path)
                    self.log.warning("{} <{}>".format(error, src_path))
                    continue

                args[0] = src_path
                new_report_items, uploaded = deliver_single_file(*args)
                report_items.update(new_report_items)
                self._update_progress(uploaded)
                repre_uploaded += uploaded

            if repre_uploaded:
                delivered_by_template[template_name].append(
                    "{} ({} files)".format(
                        self._get_repre_label(repre), repre_uploaded
                    )
                )

        self.text_area.setText(
            self._format_report(report_items, delivered_by_template)
        )
        self.text_area.setVisible(True)

    def _create_section_toggle(self, label: str) -> QtWidgets.QToolButton:
        """Create toggle button of collapsible section."""
        toggle = QtWidgets.QToolButton()
        toggle.setText(label)
        toggle.setCheckable(True)
        toggle.setChecked(False)
        toggle.setToolButtonStyle(QtCore.Qt.ToolButtonTextBesideIcon)
        toggle.setArrowType(QtCore.Qt.RightArrow)
        return toggle

    def _resolve_template(
        self, repre: dict[str, Any], selected_template_name: str
    ) -> DeliveryTemplateMatch:
        """Resolve delivery template for a representation."""
        template_data = self._template_data_by_repre_id.get(repre["id"], {})
        product_data = template_data.get("product") or {}
        return resolve_delivery_template(
            self._template_profiles,
            selected_template_name,
            representation_name=repre["name"],
            extension=repre["context"].get("ext"),
            product_base_type=product_data.get("basetype"),
            logger=self.log,
        )

    def _get_repre_template_data(
        self,
        repre: dict[str, Any],
        list_label: str,
        datetime_data: dict[str, Any],
    ) -> dict[str, Any]:
        """Copy of representation template data with delivery options."""
        template_data = copy.deepcopy(
            self._template_data_by_repre_id[repre["id"]]
        )
        if list_label:
            template_data["list"] = {"label": list_label}
        template_data.update(datetime_data)
        return template_data

    def _iter_repre_files(
        self,
        repre: dict[str, Any],
        template_data: dict[str, Any],
        renumber_frame: bool,
        frame_offset: int,
        log_frame_fallback: bool = False,
    ) -> Iterator[tuple[str, Optional[str]]]:
        """Iterate representation files and fill per-file template data.

        Template data are updated in place with 'publishedFilename' and
        frame (or udim) of the yielded file.

        Yields:
            tuple[str, Optional[str]]: Source path and error message if the
                file can't be delivered.
        """
        # TODO: This will currently incorrectly detect 'resources'
        #  that are published along with the publish, because those should
        #  not adhere to the template directly but are ingested in a
        #  customized way. For example, maya look textures or any publish
        #  that directly adds files into `instance.data["transfers"]`
        src_paths = [
            self.anatomy.fill_root(repre_file["path"])
            for repre_file in repre.get("files") or []
        ]
        sources_and_frames = collect_frames(src_paths)

        frames = set(sources_and_frames.values())
        frames.discard(None)
        first_frame = None
        if frames:
            first_frame = min(frames)

        fallback_logged = not log_frame_fallback
        for src_path, frame in sources_and_frames.items():
            # Support {publishedFilename} token
            template_data["publishedFilename"] = os.path.basename(
                # Replace backslash to forward slashes so basename
                # also resolves to filename only on POSIX
                src_path.replace("\\", "/")
            )
            # Renumber frames
            if renumber_frame and frame is not None:
                # Calculate offset between
                # first frame and current frame
                # - '0' for first frame
                offset = frame_offset - int(first_frame)
                # Add offset to new frame start
                dst_frame = int(frame) + offset
                if dst_frame < 0:
                    yield src_path, (
                        "Renumber frame has a smaller number than"
                        " original frame"
                    )
                    continue
                frame = dst_frame

            if frame is not None:
                used_fallback = self._set_frame_template_data(
                    repre, template_data, frame
                )
                if used_fallback and not fallback_logged:
                    fallback_logged = True
                    self.log.warning(
                        "Representation context has no frame or udim"
                        " data. Supplying sequence frame to '{frame}'"
                        " formatting data."
                    )
            yield src_path, None

    @staticmethod
    def _set_frame_template_data(
        repre: dict[str, Any], template_data: dict[str, Any], frame: Any
    ) -> bool:
        """Set frame (or udim) to template data.

        Returns:
            bool: True if representation context has no frame or udim and
                the frame was supplied to 'frame' as fallback.
        """
        context = repre["context"]
        if context.get("frame"):
            template_data["frame"] = frame
            return False
        if context.get("udim"):
            template_data["udim"] = frame
            return False
        template_data["frame"] = frame
        return True

    def _update_template_icons(self):
        """Mark representations delivered with another template."""
        selected_template_name = self.dropdown.currentText()
        no_icon = QtGui.QIcon()
        for idx in range(self.repre_list.topLevelItemCount()):
            item = self.repre_list.topLevelItem(idx)
            matches = []
            if selected_template_name:
                matches = [
                    self._resolve_template(repre, selected_template_name)
                    for repre in self._repres_by_name[item.text(0)]
                ]

            tooltip = ""
            icon = no_icon
            if any(match.is_override for match in matches):
                icon = self._override_icon
                tooltip = self._get_override_tooltip(matches)
            item.setIcon(_REPRE_ICON_COLUMN, icon)
            item.setToolTip(_REPRE_NAME_COLUMN, tooltip)
            item.setToolTip(_REPRE_ICON_COLUMN, tooltip)

    @staticmethod
    def _get_override_tooltip(matches: list[DeliveryTemplateMatch]) -> str:
        """Explain which template is used instead of the picked one."""
        counts = defaultdict(int)
        unique_matches = {}
        for match in matches:
            key = (match.template_name, match.profile_index)
            counts[key] += 1
            unique_matches.setdefault(key, match)

        lines = []
        for key, match in unique_matches.items():
            if not match.is_override:
                continue
            subject = "Delivered"
            if counts[key] != len(matches):
                subject = (
                    f"{counts[key]} of {len(matches)} versions are delivered"
                )
            lines.append(
                f"{subject} with template '{match.template_name}'"
                f" instead of '{match.selected_template_name}'."
            )
            lines.append(
                f"Set by delivery template profile #{match.profile_index + 1}"
            )
            for filter_key, label in _PROFILE_FILTER_LABELS:
                values = match.profile.get(filter_key)
                if values:
                    lines.append(f"    {label}: {', '.join(values)}")
            lines.append("")
        lines.append("Project Settings > Core > Tools > Delivery")
        return "\n".join(lines)

    def _on_paths_toggled(self, checked: bool):
        self.paths_view.setVisible(checked)
        self.paths_toggle.setArrowType(
            QtCore.Qt.DownArrow if checked else QtCore.Qt.RightArrow
        )
        self._main_layout.setStretchFactor(
            self._paths_widget, 1 if checked else 0
        )
        self._main_layout.setStretch(
            self._stretch_index, 0 if checked else 1
        )
        if checked and self._paths_dirty:
            self._refresh_paths_preview()

    def _invalidate_paths(self, *_args):
        """Mark destination paths outdated, refresh them if expanded."""
        self._paths_dirty = True
        if self.paths_toggle.isChecked():
            # Debounce refresh e.g. while typing root
            self.paths_timer.start()

    def _refresh_paths_preview(self):
        self.paths_timer.stop()
        self._paths_dirty = False

        # Keep groups collapsed by the user collapsed after refresh
        collapsed_keys = set()
        for idx in range(self.paths_view.topLevelItemCount()):
            item = self.paths_view.topLevelItem(idx)
            if not item.isExpanded():
                collapsed_keys.add(item.data(0, _GROUP_KEY_ROLE))
        self.paths_view.clear()

        selected_repre_names = self._get_selected_repres()
        if not selected_repre_names or not self.dropdown.currentText():
            item = QtWidgets.QTreeWidgetItem(
                ["Select representations to see where they will be delivered."]
            )
            item.setFlags(QtCore.Qt.NoItemFlags)
            self.paths_view.addTopLevelItem(item)
            item.setFirstColumnSpanned(True)
            return

        QtWidgets.QApplication.setOverrideCursor(QtCore.Qt.WaitCursor)
        try:
            groups = self._get_destination_groups(selected_repre_names)
        finally:
            QtWidgets.QApplication.restoreOverrideCursor()

        override_brush = QtGui.QBrush(self._override_color)
        error_brush = QtGui.QBrush(self._error_color)
        selected_template_name = self.dropdown.currentText()
        for group in groups:
            key = f"{group.repre_name}|{group.template_name}"
            counts = []
            if group.files_count:
                counts.append(f"{group.files_count} files")
            if group.errors:
                errors_count = len(group.errors)
                counts.append(
                    f"{errors_count} error{'s' if errors_count > 1 else ''}"
                )
            item = QtWidgets.QTreeWidgetItem(
                [group.repre_name, group.template_name, ", ".join(counts)]
            )
            item.setData(0, _GROUP_KEY_ROLE, key)
            font = item.font(0)
            font.setBold(True)
            item.setFont(0, font)
            if group.is_override:
                item.setForeground(1, override_brush)
                item.setToolTip(
                    1,
                    f"Delivered with template '{group.template_name}'"
                    f" instead of '{selected_template_name}'",
                )
            if group.errors:
                item.setForeground(2, error_brush)
            self.paths_view.addTopLevelItem(item)

            for error in group.errors:
                child = QtWidgets.QTreeWidgetItem([error])
                child.setForeground(0, error_brush)
                child.setToolTip(0, error)
                item.addChild(child)
                child.setFirstColumnSpanned(True)

            for path in group.paths:
                child = QtWidgets.QTreeWidgetItem([path])
                child.setToolTip(0, path)
                child.setData(0, _PATH_ROLE, path)
                item.addChild(child)
                child.setFirstColumnSpanned(True)
            item.setExpanded(key not in collapsed_keys)

    def _get_destination_groups(
        self, repre_names: list[str]
    ) -> list[_DestinationGroup]:
        """Destination paths of all files grouped by representation.

        Versions with the same representation name may be delivered with
        different templates, so groups are per name and template.
        """
        selected_template_name = self.dropdown.currentText()
        format_dict = get_format_dict(self.anatomy, self.root_line_edit.text())
        list_label = self.list_label_line_edit.text()
        renumber_frame = self.renumber_frame.isChecked()
        frame_offset = self.first_frame_start.value()
        datetime_data = get_datetime_data()

        groups: dict[tuple[str, str], _DestinationGroup] = {}
        for repre_name in sorted(repre_names):
            for repre in self._repres_by_name[repre_name]:
                match = self._resolve_template(repre, selected_template_name)
                paths, error = self._get_destination_paths(
                    repre,
                    match.template_name,
                    format_dict,
                    list_label,
                    datetime_data,
                    renumber_frame,
                    frame_offset,
                )
                key = (repre_name, match.template_name)
                group = groups.get(key)
                if group is None:
                    group = _DestinationGroup(
                        repre_name=repre_name,
                        template_name=match.template_name,
                        is_override=match.is_override,
                    )
                    groups[key] = group
                group.files_count += len(paths)
                group.paths.extend(self._collapse_paths(paths))
                if error:
                    label = self._get_repre_label(
                        repre, include_repre_name=False
                    )
                    group.errors.append(f"{label}: {error}")

        for group in groups.values():
            group.paths.sort()
        return list(groups.values())

    def _copy_selected_paths(self):
        """Copy selected destination paths, or all paths of a group."""
        paths = []
        for item in self.paths_view.selectedItems():
            items = [item]
            if item.childCount():
                items = [item.child(idx) for idx in range(item.childCount())]
            for path_item in items:
                path = path_item.data(0, _PATH_ROLE)
                if path and path not in paths:
                    paths.append(path)
        if paths:
            QtWidgets.QApplication.clipboard().setText("\n".join(paths))

    def _get_destination_paths(
        self,
        repre: dict[str, Any],
        template_name: str,
        format_dict: dict[str, Any],
        list_label: str,
        datetime_data: dict[str, Any],
        renumber_frame: bool,
        frame_offset: int,
    ) -> tuple[list[str], Optional[str]]:
        """Destination paths of all files of a representation.

        Returns:
            tuple[list[str], Optional[str]]: Destination paths and error
                message if the representation can't be delivered.
        """
        if template_name not in self.templates:
            return [], f"Template '{template_name}' is not available"

        template_data = self._get_repre_template_data(
            repre, list_label, datetime_data
        )
        if format_dict:
            template_data["root"] = format_dict["root"]
        path_template = self.anatomy.get_template_item(
            "delivery", template_name, "path"
        )
        paths = []
        for _src_path, error in self._iter_repre_files(
            repre, template_data, renumber_frame, frame_offset
        ):
            if error:
                return paths, error
            result = path_template.format(template_data)
            if not result.solved:
                missing_keys = ", ".join(sorted(result.missing_keys))
                return [], f"Missing keys: {missing_keys or '-'}"
            # Same path cleanup as 'deliver_single_file'
            path = str(result).replace("..", ".")
            paths.append(os.path.normpath(path.replace("\\", "/")).rstrip())
        return paths, None

    @staticmethod
    def _collapse_paths(paths: list[str]) -> list[str]:
        """Collapse frame sequences, e.g. 'name.####.exr  [1001-1048]'."""
        collections, remainder = clique.assemble(
            paths,
            patterns=[clique.PATTERNS["frames"]],
            assume_padded_when_ambiguous=True,
        )
        output = [
            "{}{}{}  [{}]".format(
                collection.head,
                "#" * (collection.padding or 1),
                collection.tail,
                collection.format("{ranges}"),
            )
            for collection in collections
        ]
        output.extend(remainder)
        return sorted(output)

    def _get_repre_label(
        self, repre: dict[str, Any], include_repre_name: bool = True
    ) -> str:
        """Human readable label of representation for report."""
        template_data = self._template_data_by_repre_id.get(repre["id"], {})
        folder_path = (template_data.get("folder") or {}).get("path", "")
        product_name = (template_data.get("product") or {}).get("name", "")
        version = template_data.get("version")
        version_label = ""
        if isinstance(version, int):
            version_label = f" v{version:03d}"
        label = f"{folder_path}/{product_name}{version_label}"
        if include_repre_name:
            label += f" [{repre['name']}]"
        return label

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

    def _set_representations(self, project_name, version_ids):
        repres = list(ayon_api.get_representations(
            project_name, version_ids=version_ids
        ))

        self._representations = repres

    def _get_counts(self, selected_repres=None):
        """Returns tuple of number of selected files and their size."""
        files_selected = 0
        size_selected = 0
        selected_repres_count = 0
        for repre in self._representations:
            if repre["name"] in selected_repres:
                selected_repres_count += 1
                files = repre.get("files", [])
                if not files:  # for repre without files, cannot divide by 0
                    files_selected += 1
                    size_selected += 0
                else:
                    for repre_file in files:
                        files_selected += 1
                        size_selected += repre_file["size"]

        return selected_repres_count, files_selected, size_selected

    def _prepare_label(self):
        """Provides text with no of selected files and their size."""
        label = "{} ({} files, size {})".format(
            self.selected_repres_count,
            self.files_selected,
            format_file_size(self.size_selected))
        return label

    def _get_selected_repres(self):
        """Returns list of representation names selected in the list."""
        return [
            item.text(_REPRE_NAME_COLUMN)
            for item in self.repre_list.selectedItems()
        ]

    def _update_selected_label(self):
        """Updates label with list of number of selected files."""
        selected_repres = self._get_selected_repres()
        self.selected_repres_count, self.files_selected, self.size_selected = \
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
        self._update_template_icons()
        self._invalidate_paths()

    def _update_progress(self, uploaded):
        """Update progress bar after each repre copied."""
        self.currently_uploaded += uploaded

        ratio = self.currently_uploaded / self.files_selected
        self.progress_bar.setValue(ratio * self.progress_bar.maximum())

    def _format_report(self, report_items, delivered_by_template=None):
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

        for template_name, labels in sorted(
            (delivered_by_template or {}).items()
        ):
            txt += "<h3>Delivered with template '{}'</h3>".format(
                html.escape(template_name)
            )
            for label in labels:
                txt += "{}<br>".format(html.escape(label))

        return txt
