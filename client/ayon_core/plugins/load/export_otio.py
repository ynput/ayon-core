import logging
import os
from pathlib import Path
from collections import defaultdict

from qtpy import QtWidgets, QtCore, QtGui
from ayon_api import get_representations

from ayon_core.pipeline import load, Anatomy
from ayon_core import resources, style
from ayon_core.lib.transcoding import (
    IMAGE_EXTENSIONS,
    get_oiio_info_for_input,
)
from ayon_core.lib import (
    get_ffprobe_data,
    is_oiio_supported,
)
from ayon_core.pipeline.load import get_representation_path_with_anatomy
from ayon_core.tools.utils import show_message_dialog

OTIO = None
FRAME_SPLITTER = "__frame_splitter__"

def _import_otio():
    global OTIO
    if OTIO is None:
        import opentimelineio
        OTIO = opentimelineio


class ExportOTIO(load.ProductLoaderPlugin):
    """Export selected versions to OpenTimelineIO."""

    is_multiple_contexts_compatible = True
    sequence_splitter = "__sequence_splitter__"

    representations = {"*"}
    product_types = {"*"}
    tool_names = ["library_loader"]

    label = "Export OTIO"
    order = 35
    icon = "save"
    color = "#d8d8d8"

    def load(self, contexts, name=None, namespace=None, options=None):
        _import_otio()
        try:
            dialog = ExportOTIOOptionsDialog(contexts, self.log)
            dialog.exec_()
        except Exception:
            self.log.error("Failed to export OTIO.", exc_info=True)


class ExportOTIOOptionsDialog(QtWidgets.QDialog):
    """Dialog to select template where to deliver selected representations."""

    def __init__(self, contexts, log=None, parent=None):
        # Not all hosts have OpenTimelineIO available.
        self.log = log

        super().__init__(parent=parent)

        self.setWindowTitle("AYON - Export OTIO")
        icon = QtGui.QIcon(resources.get_ayon_icon_filepath())
        self.setWindowIcon(icon)

        self.setWindowFlags(
            QtCore.Qt.WindowStaysOnTopHint
            | QtCore.Qt.WindowCloseButtonHint
            | QtCore.Qt.WindowMinimizeButtonHint
        )

        project_name = contexts[0]["project"]["name"]
        versions_by_id = {
            context["version"]["id"]: context["version"]
            for context in contexts
        }
        repre_entities = list(get_representations(
            project_name, version_ids=set(versions_by_id)
        ))
        version_by_representation_id = {
            repre_entity["id"]: versions_by_id[repre_entity["versionId"]]
            for repre_entity in repre_entities
        }
        version_path_by_id = {}
        representations_by_version_id = {}
        for context in contexts:
            version_id = context["version"]["id"]
            if version_id in version_path_by_id:
                continue
            representations_by_version_id[version_id] = []
            version_path_by_id[version_id] = "/".join([
                context["folder"]["path"],
                context["product"]["name"],
                context["version"]["name"]
            ])

        for repre_entity in repre_entities:
            representations_by_version_id[repre_entity["versionId"]].append(
                repre_entity
            )

        all_representation_names = list(sorted({
            repo_entity["name"]
            for repo_entity in repre_entities
        }))

        input_widget = QtWidgets.QWidget(self)
        input_layout = QtWidgets.QGridLayout(input_widget)
        input_layout.setContentsMargins(8, 8, 8, 8)

        row = 0
        repres_label = QtWidgets.QLabel("Representations:", input_widget)
        input_layout.addWidget(repres_label, row, 0)
        repre_name_buttons = []
        for idx, name in enumerate(all_representation_names):
            repre_name_btn = QtWidgets.QPushButton(name, input_widget)
            input_layout.addWidget(
                repre_name_btn, row, idx + 1,
                alignment=QtCore.Qt.AlignCenter
            )
            repre_name_btn.clicked.connect(self._toggle_all)
            repre_name_buttons.append(repre_name_btn)

        row += 1

        representation_widgets = defaultdict(list)
        items = representations_by_version_id.items()
        for version_id, representations in items:
            version_path = version_path_by_id[version_id]
            label_widget = QtWidgets.QLabel(version_path, input_widget)
            input_layout.addWidget(label_widget, row, 0)

            repres_by_name = {
                repre_entity["name"]: repre_entity
                for repre_entity in representations
            }
            radio_group = QtWidgets.QButtonGroup(input_widget)
            for idx, name in enumerate(all_representation_names):
                if name in repres_by_name:
                    widget = QtWidgets.QRadioButton(input_widget)
                    radio_group.addButton(widget)
                    representation_widgets[name].append(
                        {
                            "widget": widget,
                            "representation": repres_by_name[name]
                        }
                    )
                else:
                    widget = QtWidgets.QLabel("x", input_widget)

                input_layout.addWidget(
                    widget, row, idx + 1, 1, 1,
                    alignment=QtCore.Qt.AlignCenter
                )

            row += 1

        export_widget = QtWidgets.QWidget(self)

        options_widget = QtWidgets.QWidget(export_widget)

        uri_label = QtWidgets.QLabel("URI paths:", options_widget)
        uri_path_format = QtWidgets.QCheckBox(options_widget)
        uri_path_format.setToolTip(
            "Use URI paths (file:///) instead of absolute paths. "
            "This is useful when the OTIO file will be used on Foundry Hiero."
        )

        button_output_path = QtWidgets.QPushButton(
            "Output Path:", options_widget
        )
        button_output_path.setToolTip(
            "Click to select the output path for the OTIO file."
        )

        line_edit_output_path = QtWidgets.QLineEdit(
            (Path.home() / f"{project_name}.otio").as_posix(),
            options_widget
        )

        options_layout = QtWidgets.QHBoxLayout(options_widget)
        options_layout.setContentsMargins(0, 0, 0, 0)
        options_layout.addWidget(uri_label)
        options_layout.addWidget(uri_path_format)
        options_layout.addWidget(button_output_path)
        options_layout.addWidget(line_edit_output_path)

        button_export = QtWidgets.QPushButton("Export", export_widget)

        export_layout = QtWidgets.QVBoxLayout(export_widget)
        export_layout.setContentsMargins(0, 0, 0, 0)
        export_layout.addWidget(options_widget, 0)
        export_layout.addWidget(button_export, 0)

        main_layout = QtWidgets.QVBoxLayout(self)
        main_layout.setContentsMargins(8, 8, 8, 8)
        main_layout.addWidget(input_widget, 0)
        main_layout.addStretch(1)
        # TODO add line spacer?
        main_layout.addSpacing(30)
        main_layout.addWidget(export_widget, 0)

        button_export.clicked.connect(self._on_export_click)
        button_output_path.clicked.connect(self._set_output_path)

        self._project_name = project_name
        self._version_path_by_id = version_path_by_id
        self._version_by_representation_id = version_by_representation_id
        self._representation_widgets = representation_widgets
        self._repre_name_buttons = repre_name_buttons

        self._uri_path_format = uri_path_format
        self._button_output_path = button_output_path
        self._line_edit_output_path = line_edit_output_path
        self._button_export = button_export

        self._first_show = True

    def showEvent(self, event):
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            self.setStyleSheet(style.load_stylesheet())

    def _toggle_all(self):
        representation_name = self.sender().text()
        for item in self._representation_widgets[representation_name]:
            item["widget"].setChecked(True)

    def _set_output_path(self):
        file_path, _ = QtWidgets.QFileDialog.getSaveFileName(
            None, "Save OTIO file.", "", "OTIO Files (*.otio)"
        )
        if file_path:
            self._line_edit_output_path.setText(file_path)

    def _on_export_click(self):
        output_path = self._line_edit_output_path.text()
        # Validate output path is not empty.
        if not output_path:
            show_message_dialog(
                "Missing output path",
                (
                    "Output path is empty. Please enter a path to export the "
                    "OTIO file to."
                ),
                level="critical",
                parent=self
            )
            return

        # Validate output path ends with .otio.
        if not output_path.endswith(".otio"):
            show_message_dialog(
                "Wrong extension.",
                (
                    "Output path needs to end with \".otio\"."
                ),
                level="critical",
                parent=self
            )
            return

        representations = []
        for name, items in self._representation_widgets.items():
            for item in items:
                if item["widget"].isChecked():
                    representations.append(item["representation"])

        anatomy = Anatomy(self._project_name)
        clips_data = {}
        for representation in representations:
            version = self._version_by_representation_id[
                representation["id"]
            ]
            name = (
                f'{self._version_path_by_id[version["id"]]}'
                f'/{representation["name"]}'
            ).replace("/", "_")

            clips_data[name] = {
                "representation": representation,
                "anatomy": anatomy,
                "frames": (
                    version["attrib"]["frameEnd"]
                    - version["attrib"]["frameStart"]
                ),
                "framerate": version["attrib"]["fps"],
            }

        self.export_otio(clips_data, output_path)

        # Feedback about success.
        show_message_dialog(
            "Success!",
            "Export was successful.",
            level="info",
            parent=self
        )

        self.close()

    def create_clip(self, name, clip_data, timeline_framerate):
        representation = clip_data["representation"]
        anatomy = clip_data["anatomy"]
        frames = clip_data["frames"]
        framerate = clip_data["framerate"]

        # Get path to representation with correct frame number
        repre_path = get_representation_path_with_anatomy(
            representation, anatomy)

        media_start_frame = clip_start_frame = 0
        media_framerate = framerate
        if file_metadata := get_image_info_metadata(
            repre_path, ["timecode", "duration", "framerate"], self.log
        ):
            # get media framerate and convert to float with 3 decimal places
            media_framerate = file_metadata["framerate"]
            media_framerate = float(f"{media_framerate:.4f}")
            framerate = float(f"{timeline_framerate:.4f}")

            media_start_frame = self.get_timecode_start_frame(
                media_framerate, file_metadata
            )
            clip_start_frame = self.get_timecode_start_frame(
                timeline_framerate, file_metadata
            )

            if "duration" in file_metadata:
                frames = int(float(file_metadata["duration"]) * framerate)

        repre_path = Path(repre_path)

        first_frame = representation["context"].get("frame")
        if first_frame is None:
            media_range = OTIO.opentime.TimeRange(
                start_time=OTIO.opentime.RationalTime(
                    media_start_frame, media_framerate
                ),
                duration=OTIO.opentime.RationalTime(
                    frames, media_framerate),
            )
            clip_range = OTIO.opentime.TimeRange(
                start_time=OTIO.opentime.RationalTime(
                    clip_start_frame, timeline_framerate
                ),
                duration=OTIO.opentime.RationalTime(
                    frames, timeline_framerate),
            )

            # Use 'repre_path' as single file
            media_reference = OTIO.schema.ExternalReference(
                available_range=media_range,
                target_url=self.convert_to_uri_or_posix(repre_path),
            )
        else:
            # This is sequence
            repre_files = [
                file["path"].format(root=anatomy.roots)
                for file in representation["files"]
            ]
            # Change frame in representation context to get path with frame
            #   splitter.
            representation["context"]["frame"] = FRAME_SPLITTER
            frame_repre_path = get_representation_path_with_anatomy(
                representation, anatomy
            )
            frame_repre_path = Path(frame_repre_path)
            repre_dir, repre_filename = (
                frame_repre_path.parent, frame_repre_path.name)
            # Get sequence prefix and suffix
            file_prefix, file_suffix = repre_filename.split(FRAME_SPLITTER)
            # Get frame number from path as string to get frame padding
            frame_str = str(repre_path)[len(file_prefix):][:len(file_suffix)]
            frame_padding = len(frame_str)

            media_range = OTIO.opentime.TimeRange(
                start_time=OTIO.opentime.RationalTime(
                    media_start_frame, media_framerate
                ),
                duration=OTIO.opentime.RationalTime(
                    len(repre_files), media_framerate
                ),
            )
            clip_range = OTIO.opentime.TimeRange(
                start_time=OTIO.opentime.RationalTime(
                    clip_start_frame, timeline_framerate
                ),
                duration=OTIO.opentime.RationalTime(
                    len(repre_files), timeline_framerate
                ),
            )

            media_reference = OTIO.schema.ImageSequenceReference(
                available_range=media_range,
                start_frame=int(first_frame),
                frame_step=1,
                rate=framerate,
                target_url_base=f"{self.convert_to_uri_or_posix(repre_dir)}/",
                name_prefix=file_prefix,
                name_suffix=file_suffix,
                frame_zero_padding=frame_padding,
            )

        return OTIO.schema.Clip(
            name=name, media_reference=media_reference, source_range=clip_range
        )

    def convert_to_uri_or_posix(self, path: Path) -> str:
        """Convert path to URI or Posix path.

        Args:
            path (Path): Path to convert.

        Returns:
            str: Path as URI or Posix path.
        """
        if self._uri_path_format.isChecked():
            return path.as_uri()

        return path.as_posix()

    def get_timecode_start_frame(self, framerate, file_metadata):
        # use otio to convert timecode into frame number
        timecode_start_frame = OTIO.opentime.from_timecode(
            file_metadata["timecode"], framerate)
        return timecode_start_frame.to_frames()

    def export_otio(self, clips_data, output_path):
        # first find the highest framerate and set it as default framerate
        #   for the timeline
        timeline_framerate = 0
        for clip_data in clips_data.values():
            framerate = clip_data["framerate"]
            if framerate > timeline_framerate:
                timeline_framerate = framerate

        # reduce decimal places to 3 - otio does not like more
        timeline_framerate = float(f"{timeline_framerate:.4f}")

        # create clips from the representations
        clips = [
            self.create_clip(name, clip_data, timeline_framerate)
            for name, clip_data in clips_data.items()
        ]
        timeline = OTIO.schema.timeline_from_clips(clips)

        # set the timeline framerate to the highest framerate
        timeline.global_start_time = OTIO.opentime.RationalTime(
            0, timeline_framerate)

        OTIO.adapters.write_to_file(timeline, output_path)


def get_image_info_metadata(
    path_to_file,
    keys=None,
    logger=None,
):
    """Get flattened metadata from image file

    With combined approach via FFMPEG and OIIOTool.

    At first it will try to detect if the image input is supported by
    OpenImageIO. If it is then it gets the metadata from the image using
    OpenImageIO. If it is not supported by OpenImageIO then it will try to
    get the metadata using FFprobe.

    Args:
        path_to_file (str): Path to image file.
        keys (list[str]): List of keys that should be returned. If None then
            all keys are returned. Keys are expected all lowercase.
            Additional keys are:
            - "framerate" - will be created from "r_frame_rate" or
                "framespersecond" and evaluated to float value.
        logger (logging.Logger): Logger used for logging.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    def _ffprobe_metadata_conversion(metadata):
        """Convert ffprobe metadata unified format."""
        output = {}
        for key, val in metadata.items():
            if key in ("tags", "disposition"):
                output.update(val)
            else:
                output[key] = val
        return output

    def _get_video_metadata_from_ffprobe(ffprobe_stream):
        """Extract video metadata from ffprobe stream.

        Args:
            ffprobe_stream (dict): Stream data obtained from ffprobe.

        Returns:
            dict: Video metadata extracted from the ffprobe stream.
        """
        video_stream = None
        for stream in ffprobe_stream["streams"]:
            if stream["codec_type"] == "video":
                video_stream = stream
                break
        metadata_stream = _ffprobe_metadata_conversion(video_stream)
        return metadata_stream

    metadata_stream = None
    ext = os.path.splitext(path_to_file)[-1].lower()
    if ext not in IMAGE_EXTENSIONS:
        logger.info(
            (
                'File extension "{}" is not supported by OpenImageIO.'
                " Trying to get metadata using FFprobe."
            ).format(ext)
        )
        ffprobe_stream = get_ffprobe_data(path_to_file, logger)
        if "streams" in ffprobe_stream and len(ffprobe_stream["streams"]) > 0:
            metadata_stream = _get_video_metadata_from_ffprobe(ffprobe_stream)

    if not metadata_stream and is_oiio_supported():
        oiio_stream = get_oiio_info_for_input(path_to_file, logger=logger)
        if "attribs" in (oiio_stream or {}):
            metadata_stream = {}
            for key, val in oiio_stream["attribs"].items():
                if "smpte:" in key.lower():
                    key = key.replace("smpte:", "")
                metadata_stream[key.lower()] = val
            for key, val in oiio_stream.items():
                if key == "attribs":
                    continue
                metadata_stream[key] = val
    else:
        logger.info(
            (
                "OpenImageIO is not supported on this system."
                " Trying to get metadata using FFprobe."
            )
        )
        ffprobe_stream = get_ffprobe_data(path_to_file, logger)
        if "streams" in ffprobe_stream and len(ffprobe_stream["streams"]) > 0:
            metadata_stream = _get_video_metadata_from_ffprobe(ffprobe_stream)

    if not metadata_stream:
        logger.warning("Failed to get metadata from image file.")
        return {}

    if keys is None:
        return metadata_stream

    # create framerate key from available ffmpeg:r_frame_rate
    # or oiiotool:framespersecond and evaluate its string expression
    # value into flaot value
    if (
        "r_frame_rate" in metadata_stream
        or "framespersecond" in metadata_stream
    ):
        rate_info = metadata_stream.get("r_frame_rate")
        if rate_info is None:
            rate_info = metadata_stream.get("framespersecond")

        # calculate framerate from string expression
        if "/" in str(rate_info):
            time, frame = str(rate_info).split("/")
            rate_info = float(time) / float(frame)

        try:
            metadata_stream["framerate"] = float(str(rate_info))
        except Exception as e:
            logger.warning(
                "Failed to evaluate '{}' value to framerate. Error: {}".format(
                    rate_info, e
                )
            )

    # aggregate all required metadata from prepared metadata stream
    output = {}
    for key in keys:
        for k, v in metadata_stream.items():
            if key == k:
                output[key] = v
                break
            if isinstance(v, dict) and key in v:
                output[key] = v[key]
                break

    return output
