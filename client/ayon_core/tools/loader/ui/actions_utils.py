import os
import re
import sys
import tempfile
import threading
import time
import uuid
from typing import Any, Callable, Dict, Optional, Union

from qtpy import QtWidgets, QtGui, QtCore
import qtawesome

from ayon_core.lib import Logger
from ayon_core.lib.attribute_definitions import AbstractAttrDef
from ayon_core.tools.utils import DeselectableTreeView

from ayon_core.tools.loader.drag_drop import (
    encode_loader_drag_payload,
    loader_payload_to_bytes,
    decode_loader_drag_payload_from_mime,
    LOADER_PAYLOAD_MIME_TYPE,
    LOADER_PAYLOAD_TEMP_PREFIX,
)
from ayon_core.tools.attribute_defs import AttributeDefinitionsDialog
from ayon_core.tools.utils.widgets import (
    OptionalMenu,
    OptionalAction,
    OptionDialog,
)
from ayon_core.tools.utils import get_qt_icon
from ayon_core.tools.loader.abstract import ActionItem

from .loader_native_diag import qt_cpp_object_alive

_log = Logger.get_logger(__name__)


def _format_payload_summary(project_name, entity_type, entity_ids, action_items):
    """Build a one-line payload summary for debug logs."""
    entity_list = list(entity_ids) if entity_ids else []
    id_previews = [str(eid)[:8] + ("..." if len(str(eid)) > 8 else "") for eid in entity_list[:2]]
    action_ids = [getattr(a, "identifier", str(a)) for a in (action_items or [])]
    return (
        f"project_name={project_name} entity_type={entity_type} entity_ids={len(entity_list)} "
        f"ids={id_previews} actions={len(action_items or [])} {action_ids}"
    )


def _format_payload_summary_from_dict(payload):
    """Build a one-line payload summary from decoded payload dict."""
    if not payload or not isinstance(payload, dict):
        return "payload=invalid"
    entity_ids = payload.get("entity_ids") or []
    actions = payload.get("actions") or []
    id_previews = [str(eid)[:8] + ("..." if len(str(eid)) > 8 else "") for eid in entity_ids[:2]]
    action_ids = [a.get("identifier", "") for a in actions]
    return (
        f"project_name={payload.get('project_name', '')} entity_type={payload.get('entity_type', '')} "
        f"entity_ids={len(entity_ids)} ids={id_previews} actions={len(actions)} {action_ids}"
    )


def _delete_payload_temp_file(path: Optional[str]) -> None:
    """Delete temp file used for OS DnD payload bridge. Ignores errors."""
    if not path:
        return
    try:
        if os.path.isfile(path):
            os.remove(path)
    except OSError:
        pass


def _delete_payload_temp_file_after_drag(path: Optional[str]) -> None:
    """Deferred cleanup after cross-process drag; log for timing regressions."""
    if _log:
        _log.debug(
            "loader drag marker deferred delete firing: path=%s exists=%s",
            path,
            os.path.isfile(path) if path else False,
        )
    _delete_payload_temp_file(path)


def _set_file_urls_on_mime_data(mime_data: QtCore.QMimeData, paths: list) -> None:
    """Set file URLs on mime data for cross-platform drag (text/uri-list).
    On Windows, sets Preferred DropEffect to 5 (copy) so Explorer copies instead of moves.
    """
    if not paths:
        return
    urls = [QtCore.QUrl.fromLocalFile(p) for p in paths]
    mime_data.setUrls(urls)
    if sys.platform == "win32":
        mime_data.setData(
            "Preferred DropEffect",
            QtCore.QByteArray((5).to_bytes(4, "little")),
        )


def _loader_drag_start_distance() -> int:
    return max(3, QtWidgets.QApplication.startDragDistance() // 2)


loader_drag_start_distance = _loader_drag_start_distance


def _controller_for_drag_precache(view: QtWidgets.QWidget) -> Any:
    """Resolve LoaderController for precache (list parent chain vs tree header)."""
    p = view.parentWidget()
    if p is None:
        return None
    ctrl = getattr(p, "_controller", None)
    if ctrl is not None:
        return ctrl
    gp = p.parentWidget()
    if gp is not None:
        return getattr(gp, "controller", None)
    return None


def _maybe_arm_drag_precache(view: QtWidgets.QWidget) -> None:
    if getattr(view, "_drag_precache_armed", False):
        return
    precache = getattr(view, "_drag_precache", None)
    cb = getattr(view, "_drag_data_callback", None)
    if precache is None or not callable(cb):
        return
    try:
        result = cb()
        if result:
            pn, eids, et = result
            if pn and eids:
                ctrl = _controller_for_drag_precache(view)
                if ctrl is not None:
                    precache.pre_build(ctrl, pn, set(eids), et)
                    view._drag_precache_armed = True  # noqa: SLF001
    except Exception:
        pass


# Bounded wait for DragPayloadPrecache before synchronous MIME rebuild (ms).
_DRAG_PRECACHE_WAIT_MS = 250


def _primary_screen_device_pixel_ratio() -> float:
    screen = QtWidgets.QApplication.primaryScreen()
    if screen is None:
        return 1.0
    return float(screen.devicePixelRatio()) or 1.0


def _make_composite_drag_pixmap(
    thumbnail: Optional[QtGui.QPixmap],
    product_label: str,
    version_label: str,
    count: int,
    dpr: float,
) -> QtGui.QPixmap:
    """Composite drag pixmap: optional thumbnail on top, wrapped labels below.

    When ``thumbnail`` is None or null, only title and version text are drawn
    (no placeholder image region).
    """
    lw = 110
    margin = 4
    inner_w = lw - 2 * margin
    show_thumb = thumbnail is not None and not thumbnail.isNull()
    thumb_h = (
        max(24, int(round(inner_w * 9.0 / 16.0))) if show_thumb else 0
    )
    gap_below_thumb = 3 if show_thumb else 0
    gap_title_version = 2

    base_font = QtGui.QFont()
    title_font = QtGui.QFont(base_font)
    title_font.setBold(True)
    _tp = base_font.pixelSize()
    if _tp <= 0:
        _tp = max(9, int(round(base_font.pointSizeF() * 96.0 / 72.0)))
    title_font.setPixelSize(max(6, int(round(_tp * 0.52))))

    sub_font = QtGui.QFont(title_font)
    sub_font.setBold(False)
    sub_font.setPixelSize(max(5, int(round(_tp * 0.46))))

    fm_t = QtGui.QFontMetrics(title_font)
    fm_s = QtGui.QFontMetrics(sub_font)
    wrap_flags = (
        int(QtCore.Qt.TextFlag.TextWordWrap)
        | int(QtCore.Qt.AlignmentFlag.AlignLeft)
        | int(QtCore.Qt.AlignmentFlag.AlignTop)
    )

    title_max_h = fm_t.lineSpacing() * 5
    ver_max_h = fm_s.lineSpacing() * 3

    t_txt = product_label or ""
    br_t = fm_t.boundingRect(
        QtCore.QRect(0, 0, inner_w, title_max_h),
        wrap_flags,
        t_txt,
    )
    title_h = max(fm_t.height(), min(br_t.height(), title_max_h))

    v_txt = version_label or ""
    br_v = fm_s.boundingRect(
        QtCore.QRect(0, 0, inner_w, ver_max_h),
        wrap_flags,
        v_txt,
    )
    ver_h = max(fm_s.height() if v_txt else 0, min(br_v.height(), ver_max_h))

    text_block_h = title_h + (gap_title_version + ver_h if v_txt else 0)
    if show_thumb:
        lh = margin + thumb_h + gap_below_thumb + text_block_h + margin
        lh = max(lh, margin + thumb_h + margin + fm_t.height())
    else:
        lh = margin + text_block_h + margin
        lh = max(lh, margin + fm_t.height() + margin)

    dpr = max(1.0, float(dpr))
    pix_w = int(round(lw * dpr))
    pix_h = int(round(lh * dpr))
    out = QtGui.QPixmap(pix_w, pix_h)
    out.fill(QtGui.QColor(0, 0, 0, 0))
    out.setDevicePixelRatio(dpr)

    painter = QtGui.QPainter(out)
    painter.setRenderHint(QtGui.QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QtGui.QPainter.RenderHint.TextAntialiasing)

    card_rect = QtCore.QRectF(0.5, 0.5, lw - 1.0, lh - 1.0)
    painter.setBrush(QtGui.QColor(34, 38, 46, 250))
    painter.setPen(QtGui.QPen(QtGui.QColor(72, 78, 88)))
    painter.drawRoundedRect(card_rect, 3.0, 3.0)

    if show_thumb:
        thumb_rect = QtCore.QRect(margin, margin, inner_w, thumb_h)
        thumb_round = QtGui.QPainterPath()
        thumb_round.addRoundedRect(QtCore.QRectF(thumb_rect), 2.0, 2.0)
        painter.setClipPath(thumb_round)

        scaled = thumbnail.scaled(
            thumb_rect.size(),
            QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
            QtCore.Qt.TransformationMode.SmoothTransformation,
        )
        dx = thumb_rect.x() + (thumb_rect.width() - scaled.width()) // 2
        dy = thumb_rect.y() + (thumb_rect.height() - scaled.height()) // 2
        painter.drawPixmap(dx, dy, scaled)
        painter.setClipping(False)

    y_text = margin + (thumb_h + gap_below_thumb if show_thumb else 0)
    title_draw = QtCore.QRect(margin, y_text, inner_w, title_h)
    painter.setFont(title_font)
    painter.setPen(QtGui.QColor(235, 238, 245))
    painter.drawText(title_draw, wrap_flags, t_txt)

    if v_txt:
        painter.setFont(sub_font)
        painter.setPen(QtGui.QColor(180, 186, 198))
        ver_draw = QtCore.QRect(
            margin,
            y_text + title_h + gap_title_version,
            inner_w,
            ver_h,
        )
        painter.drawText(ver_draw, wrap_flags, v_txt)

    if count > 1:
        badge_txt = f"+{count}"
        bf = QtGui.QFont(base_font)
        bf.setBold(True)
        bf.setPointSize(max(7, bf.pointSize() - 2))
        painter.setFont(bf)
        bfm = painter.fontMetrics()
        pad_x, pad_y = 3, 2
        br_w = bfm.horizontalAdvance(badge_txt) + 2 * pad_x
        br_h = bfm.height() + 2 * pad_y
        br = QtCore.QRectF(lw - margin - br_w, margin, br_w, br_h)
        painter.setBrush(QtGui.QColor(80, 140, 220, 230))
        painter.setPen(QtCore.Qt.PenStyle.NoPen)
        painter.drawRoundedRect(br, 2.0, 2.0)
        painter.setPen(QtGui.QColor(255, 255, 255))
        painter.drawText(br, QtCore.Qt.AlignmentFlag.AlignCenter, badge_txt)

    painter.end()
    return out


RawDragResult = tuple[str, Union[set[str], Any], str]


def _write_loader_drag_marker_file(
    payload: Dict[str, Any],
    file_paths: list[str],
) -> Optional[str]:
    """Write ``ayon_loader_*.json`` under the OS temp dir; return path or None."""
    temp_path: Optional[str] = None
    try:
        fd, temp_path = tempfile.mkstemp(
            suffix=".json",
            prefix=LOADER_PAYLOAD_TEMP_PREFIX,
            dir=tempfile.gettempdir(),
        )
        with os.fdopen(fd, "wb") as f:
            marker_disk: Dict[str, Any] = dict(payload)
            marker_disk["file_paths"] = list(file_paths)
            f.write(loader_payload_to_bytes(marker_disk))
        if _log:
            _log.debug(
                "loader drag marker written: path=%s file_paths_n=%d",
                temp_path,
                len(file_paths),
            )
    except Exception as e:
        if _log:
            _log.debug(
                "_write_loader_drag_marker_file: temp json failed %s",
                e,
                exc_info=True,
            )
        if temp_path and os.path.isfile(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass
        return None
    return temp_path


class DragPayloadPrecache:
    """Pre-build drag MIME payload data in a background thread on selection."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._cv = threading.Condition(self._lock)
        self._key: Optional[tuple[str, frozenset[str], str]] = None
        self._data: Optional[Dict[str, Any]] = None

    def pre_build(
        self,
        controller: Any,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> None:
        if not project_name or not entity_ids:
            return
        key = (project_name, frozenset(entity_ids), entity_type)
        with self._cv:
            if self._key == key and self._data is not None:
                return
            self._key = key
            self._data = None
        threading.Thread(
            target=self._run,
            args=(controller, project_name, entity_ids, entity_type, key),
            daemon=True,
        ).start()

    def get(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
    ) -> Optional[Dict[str, Any]]:
        key = (project_name, frozenset(entity_ids), entity_type)
        with self._lock:
            if self._key == key:
                return self._data
        return None

    def wait(
        self,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
        timeout_ms: int,
    ) -> None:
        """Block until precache fills for ``key`` or timeout (pumps Qt events)."""
        key = (project_name, frozenset(entity_ids), entity_type)
        deadline = time.monotonic() + max(0, timeout_ms) / 1000.0
        app = QtWidgets.QApplication.instance()
        while time.monotonic() < deadline:
            with self._cv:
                if self._key != key:
                    return
                if self._data is not None:
                    return
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    break
                self._cv.wait(timeout=min(0.05, remaining))
            if app:
                try:
                    _pe = (
                        QtCore.QEventLoop.ProcessEventsFlag.ExcludeUserInputEvents
                    )
                except AttributeError:
                    _pe = QtCore.QEventLoop.ExcludeUserInputEvents  # type: ignore[attr-defined]
                app.processEvents(_pe)

    def _run(
        self,
        controller: Any,
        project_name: str,
        entity_ids: set[str],
        entity_type: str,
        key: tuple[str, frozenset[str], str],
    ) -> None:
        data = _build_drag_payload_data(
            controller, project_name, entity_ids, entity_type
        )
        if data is not None:
            thumb_by_vid: Dict[str, Optional[str]] = {}
            if entity_type == "version":
                try:
                    paths = controller.get_thumbnail_paths(
                        project_name, "version", set(entity_ids)
                    )
                    thumb_by_vid = {
                        str(k): v for k, v in (paths or {}).items()
                    }
                except Exception as exc:
                    if _log:
                        _log.debug(
                            "DragPayloadPrecache: thumbnail paths %s",
                            exc,
                            exc_info=True,
                        )
            data["thumbnail_paths_by_version_id"] = thumb_by_vid
            payload = data.get("payload") or {}
            file_paths = list(data.get("file_paths") or [])
            marker_path = _write_loader_drag_marker_file(payload, file_paths)
            data["marker_temp_path"] = marker_path
        with self._cv:
            if self._key == key:
                self._data = data
            self._cv.notify_all()


def _build_drag_payload_data(
    controller: Any,
    project_name: str,
    entity_ids: set[str],
    entity_type: str,
) -> Optional[Dict[str, Any]]:
    """Build serializable drag payload + paths; no Qt objects."""
    in_host = getattr(controller, "_host", None) is not None

    try:
        if entity_type == "version":
            primary_by_vid, candidates_by_vid = (
                controller.resolve_drag_drop_representation_selection(
                    project_name, set(entity_ids)
                )
            )
            action_items, eff_type, flat_ids, extras = (
                controller.collect_drag_drop_actions_for_version_resolution(
                    project_name,
                    set(entity_ids),
                    primary_by_vid,
                    candidates_by_vid,
                )
            )
            default_map = {
                k: list(v)
                for k, v in (candidates_by_vid or {}).items()
                if v
            }
            payload = encode_loader_drag_payload(
                project_name,
                eff_type,
                flat_ids,
                action_items,
                default_repre_ids_by_version_id=default_map or None,
                needs_rep_choice=bool(extras.get("needs_rep_choice")),
                actions_by_repre_id=extras.get("actions_by_repre_id"),
                repre_names_by_id=extras.get("repre_names_by_id"),
            )
        else:
            action_items = (
                controller.get_drag_drop_action_items(
                    project_name, set(entity_ids), entity_type
                )
                or []
            )
            flat_ids = list(entity_ids)
            eff_type = entity_type
            payload = encode_loader_drag_payload(
                project_name, eff_type, flat_ids, action_items
            )

        file_paths: list[str] = []
        try:
            paths = controller.get_drag_drop_file_paths(
                project_name, set(flat_ids), eff_type
            )
            file_paths = list(paths) if paths else []
        except Exception as e:
            if _log:
                _log.debug(
                    "_build_drag_payload_data: file paths %s",
                    e,
                    exc_info=True,
                )

        return {
            "payload": payload,
            "flat_ids": flat_ids,
            "eff_type": eff_type,
            "action_items": action_items,
            "file_paths": file_paths,
            "in_host": in_host,
        }
    except Exception as e:
        if _log:
            _log.debug("_build_drag_payload_data failed %s", e, exc_info=True)
        return None


def _mime_qt_from_drag_payload_data(
    data: Dict[str, Any],
) -> tuple[Optional[QtCore.QMimeData], Optional[str]]:
    """Build QMimeData + optional temp json path from _build_drag_payload_data result."""
    payload = data["payload"]
    file_paths = data.get("file_paths") or []
    in_host = bool(data.get("in_host"))

    mime_data = QtCore.QMimeData()
    mime_data.setData(
        LOADER_PAYLOAD_MIME_TYPE,
        QtCore.QByteArray(loader_payload_to_bytes(payload)),
    )

    if file_paths:
        try:
            _set_file_urls_on_mime_data(mime_data, file_paths)
        except Exception as e:
            if _log:
                _log.debug(
                    "_mime_qt_from_drag_payload_data: file urls %s",
                    e,
                    exc_info=True,
                )

    # Cross-process hosts resolve the marker from custom MIME, legacy URL list,
    # or temp-dir scan (Harmony, Unity, Photoshop CEP). Prefer a path written
    # by DragPayloadPrecache on a worker thread; otherwise write temp JSON
    # under the OS temp dir. Do **not** append the marker to ``setUrls``:
    # native Photoshop treats every file URL as Place input and errors on
    # ``.json``.
    temp_path: Optional[str] = data.get("marker_temp_path")
    if temp_path and os.path.isfile(temp_path):
        if _log:
            _log.debug(
                "loader drag marker from precache: path=%s file_paths_n=%d "
                "in_host=%s",
                temp_path,
                len(file_paths),
                in_host,
            )
    else:
        temp_path = None
        try:
            fd, temp_path = tempfile.mkstemp(
                suffix=".json",
                prefix=LOADER_PAYLOAD_TEMP_PREFIX,
                dir=tempfile.gettempdir(),
            )
            with os.fdopen(fd, "wb") as f:
                marker_disk: Dict[str, Any] = dict(payload)
                marker_disk["file_paths"] = list(file_paths)
                f.write(loader_payload_to_bytes(marker_disk))
            if _log:
                _log.debug(
                    "loader drag marker written: path=%s "
                    "file_paths_n=%d in_host=%s",
                    temp_path,
                    len(file_paths),
                    in_host,
                )
        except Exception as e:
            if _log:
                _log.debug(
                    "_mime_qt_from_drag_payload_data: temp json failed %s",
                    e,
                    exc_info=True,
                )
            if temp_path and os.path.isfile(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            temp_path = None

    return mime_data, temp_path


def _drag_pixmap_for_view(view: QtWidgets.QWidget, raw_result: RawDragResult) -> QtGui.QPixmap:
    _, entity_ids, entity_type = raw_result
    ids_set = set(entity_ids) if not isinstance(entity_ids, set) else entity_ids
    count = len(ids_set)
    thumb_path: Optional[str] = None
    product_label = ""
    version_label = ""
    ctx_cb = getattr(view, "_drag_pixmap_context_callback", None)
    if callable(ctx_cb):
        try:
            ctx = ctx_cb() or {}
        except Exception:
            ctx = {}
        if isinstance(ctx, dict):
            thumb_path = ctx.get("thumbnail_path")
            product_label = str(ctx.get("product_label") or "")
            version_label = str(ctx.get("version_label") or "")
            count = int(ctx.get("count", count))

    if getattr(view, "_loader_drag_placeholder_pixmap", False):
        thumb_path = None

    # Match full-width 16:9 slot inside _make_composite_drag_pixmap (lw=110, margin=4).
    thumb_logical = QtCore.QSize(102, 58)

    thumb_pix: Optional[QtGui.QPixmap] = None
    if thumb_path and os.path.isfile(thumb_path):
        pm = QtGui.QPixmap(thumb_path)
        if not pm.isNull():
            thumb_pix = pm.scaled(
                thumb_logical,
                QtCore.Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                QtCore.Qt.TransformationMode.SmoothTransformation,
            )
    dpr = _primary_screen_device_pixel_ratio()
    return _make_composite_drag_pixmap(
        thumb_pix, product_label, version_label, count, dpr
    )


def _mime_payload_from_selection(
    view: QtWidgets.QWidget,
    project_name: str,
    entity_ids: set[str],
    entity_type: str,
    pre_cached: Optional[Dict[str, Any]] = None,
) -> tuple[Optional[QtCore.QMimeData], Optional[str], list[ActionItem], list[str], str]:
    """Build MIME data for loader drag; returns mime, temp_path, actions, flat_ids, eff_type."""
    controller = getattr(view.parent(), "_controller", None)
    if not controller:
        return None, None, [], [], entity_type

    built: Optional[Dict[str, Any]] = pre_cached
    if built is None:
        # Precache miss: build synchronously so Explorer/desktop get file URLs
        # on the first drag (thin MIME omitted paths until precache finished).
        built = _build_drag_payload_data(
            controller, project_name, entity_ids, entity_type
        )
    if built is None:
        return None, None, [], [], entity_type

    action_items = built["action_items"]
    flat_ids = built["flat_ids"]
    eff_type = built["eff_type"]

    mime_data, temp_path = _mime_qt_from_drag_payload_data(built)
    if mime_data is None:
        return None, None, [], [], entity_type

    return mime_data, temp_path, action_items, flat_ids, eff_type


def _build_drag_mime_data_core(
    view: QtWidgets.QWidget,
) -> tuple[Optional[QtCore.QMimeData], tuple[()], Optional[str], Optional[RawDragResult]]:
    """Returns (mime_data, (), temp_path, raw_result) on success."""
    view._last_drag_summary = None  # noqa: SLF001
    cb = getattr(view, "_drag_data_callback", None)
    if not cb:
        if _log:
            _log.debug("_build_drag_mime_data: reason=no_callback")
        return None, (), None, None
    try:
        result = cb()
    except Exception as e:
        if _log:
            _log.debug("_build_drag_mime_data: callback raised %s", e, exc_info=True)
        return None, (), None, None
    if not result:
        if _log:
            _log.debug("_build_drag_mime_data: reason=callback_returned_none")
        return None, (), None, None
    try:
        project_name, entity_ids, entity_type = result
    except (ValueError, TypeError) as e:
        if _log:
            _log.debug("_build_drag_mime_data: unpack failed %s", e)
        return None, (), None, None
    if not entity_ids:
        if _log:
            _log.debug("_build_drag_mime_data: reason=no_entity_ids")
        return None, (), None, None

    ids_set = set(entity_ids)
    raw_tuple: RawDragResult = (project_name, ids_set, entity_type)
    precache = getattr(view, "_drag_precache", None)
    pre_cached = None
    precache_miss = False
    if precache is not None:
        pre_cached = precache.get(project_name, ids_set, entity_type)
        if pre_cached is None:
            precache_miss = True
            precache.wait(
                project_name, ids_set, entity_type, _DRAG_PRECACHE_WAIT_MS
            )
            pre_cached = precache.get(project_name, ids_set, entity_type)

    if precache_miss:
        view.viewport().setCursor(
            QtGui.QCursor(QtCore.Qt.CursorShape.WaitCursor)
        )
    try:
        setattr(view, "_loader_drag_placeholder_pixmap", precache_miss)
        mime_data, temp_path, action_items, flat_ids, eff_type = (
            _mime_payload_from_selection(
                view, project_name, ids_set, entity_type, pre_cached=pre_cached
            )
        )
    finally:
        if precache_miss:
            view.viewport().unsetCursor()

    if mime_data is None:
        if hasattr(view, "_loader_drag_placeholder_pixmap"):
            delattr(view, "_loader_drag_placeholder_pixmap")
        return None, (), None, None

    summary = _format_payload_summary(
        project_name, eff_type, flat_ids, action_items
    )
    if _log:
        _log.debug("_build_drag_mime_data: %s", summary)
    view._last_drag_summary = summary  # noqa: SLF001
    return mime_data, (), temp_path, raw_tuple


def _tree_row_indexes_intersecting_rect(
    tree: QtWidgets.QTreeView, rect: QtCore.QRect
) -> list[QtCore.QModelIndex]:
    out: list[QtCore.QModelIndex] = []
    model = tree.model()
    if model is None:
        return out

    def walk(parent: QtCore.QModelIndex) -> None:
        rows = model.rowCount(parent)
        for row in range(rows):
            ix = model.index(row, 0, parent)
            vr = tree.visualRect(ix)
            if vr.intersects(rect):
                out.append(ix)
            if model.hasChildren(ix):
                walk(ix)

    walk(QtCore.QModelIndex())
    return out


def _run_loader_drag(
    view: QtWidgets.QWidget,
    mime_data: QtCore.QMimeData,
    temp_path: Optional[str],
    raw_result: RawDragResult,
) -> None:
    begin_guard = getattr(view, "begin_source_drag_guard", None)
    if callable(begin_guard):
        begin_guard()
    try:
        drag = QtGui.QDrag(view)
        drag.setMimeData(mime_data)
        drag.setPixmap(_drag_pixmap_for_view(view, raw_result))
        drag.setHotSpot(QtCore.QPoint(10, 10))
        drag.exec_(QtCore.Qt.DropAction.CopyAction)
    finally:
        end_when = getattr(view, "end_source_drag_guard_when_left_released", None)
        if callable(end_when):
            end_when()
        if qt_cpp_object_alive(view) and hasattr(
            view, "_loader_drag_placeholder_pixmap"
        ):
            delattr(view, "_loader_drag_placeholder_pixmap")
    # Cross-process drops (e.g. Photoshop Place) finish Qt's drag before the
    # host reads the temp JSON; delete after a bounded delay so embedded scans
    # can find ayon_loader_*.json. Host success paths may delete earlier.
    # 60s: Plc + smart-object retries + JSX marker scan can exceed 5s easily.
    if temp_path:
        QtCore.QTimer.singleShot(
            60000, lambda p=temp_path: _delete_payload_temp_file_after_drag(p)
        )


def run_loader_drag_for_card(card: QtWidgets.QWidget) -> None:
    """Start loader ``QDrag`` from a grid card; MIME uses ``list_view`` selection."""
    grid = getattr(card, "_grid", None)
    lv = getattr(grid, "list_view", None) if grid is not None else None
    if lv is None:
        return
    try:
        mime_data, _, temp_path, raw_result = _build_drag_mime_data_core(lv)
    except Exception:
        mime_data, temp_path, raw_result = None, None, None
    if mime_data is None or raw_result is None:
        return
    lv.begin_source_drag_guard()
    try:
        drag = QtGui.QDrag(card)
        drag.setMimeData(mime_data)
        drag.setPixmap(_drag_pixmap_for_view(lv, raw_result))
        drag.setHotSpot(QtCore.QPoint(10, 10))
        drag.exec_(QtCore.Qt.DropAction.CopyAction)
    finally:
        lv.end_source_drag_guard_when_left_released()
        if qt_cpp_object_alive(lv) and hasattr(
            lv, "_loader_drag_placeholder_pixmap"
        ):
            delattr(lv, "_loader_drag_placeholder_pixmap")
    if temp_path:
        QtCore.QTimer.singleShot(
            60000, lambda p=temp_path: _delete_payload_temp_file_after_drag(p)
        )


def _remime_from_decoded_payload(
    view: QtWidgets.QWidget, payload: dict[str, Any]
) -> tuple[Optional[QtCore.QMimeData], Optional[str], Optional[RawDragResult]]:
    project_name = str(payload.get("project_name") or "")
    entity_ids = set(payload.get("entity_ids") or [])
    entity_type = str(payload.get("entity_type") or "version")
    if not entity_ids:
        return None, None, None
    mime_data, temp_path, _, _, _ = _mime_payload_from_selection(
        view, project_name, entity_ids, entity_type
    )
    if mime_data is None:
        return None, None, None
    raw: RawDragResult = (project_name, entity_ids, entity_type)
    return mime_data, temp_path, raw


class LoaderDragTreeView(DeselectableTreeView):
    """Tree view that supports dragging loader action payload."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self._drag_data_callback = None
        self._drag_pixmap_context_callback = None
        self._drag_precache: Optional[DragPayloadPrecache] = None
        self._drag_start_pos = None
        self._last_drag_summary = None
        self._rubber_origin: Optional[QtCore.QPoint] = None
        self._rubber_band: Optional[QtWidgets.QRubberBand] = None
        self._drag_precache_armed = False

    def set_drag_data_callback(
        self, callback: Optional[Callable[[], Optional[tuple]]]
    ):
        self._drag_data_callback = callback

    def set_drag_pixmap_context_callback(
        self, callback: Optional[Callable[[], Optional[dict[str, Any]]]]
    ):
        self._drag_pixmap_context_callback = callback

    def set_drag_precache(self, cache: Optional[DragPayloadPrecache]) -> None:
        self._drag_precache = cache

    def _clear_drag_cursor(self) -> None:
        self.viewport().unsetCursor()

    def _cleanup_rubber_band(self) -> None:
        if self._rubber_band is not None:
            self._rubber_band.hide()
            self._rubber_band.deleteLater()
            self._rubber_band = None

    def mousePressEvent(self, event):
        self._drag_precache_armed = False
        self._rubber_origin = None
        self._cleanup_rubber_band()
        self._clear_drag_cursor()
        index = self.indexAt(event.pos())
        model = self.model()
        if index.isValid() and model:
            # Match ProductsModel.flags: draggable on row except version column.
            drag_arm = bool(
                model.flags(index) & QtCore.Qt.ItemIsDragEnabled
            )
            if drag_arm:
                self._drag_start_pos = event.pos()
                self.viewport().setCursor(
                    QtGui.QCursor(QtCore.Qt.CursorShape.ClosedHandCursor)
                )
            else:
                self._drag_start_pos = None
                if event.button() == QtCore.Qt.MouseButton.LeftButton:
                    self._rubber_origin = QtCore.QPoint(event.pos())
        else:
            if not index.isValid():
                self.clearSelection()
                self.setCurrentIndex(QtCore.QModelIndex())
            self._drag_start_pos = None
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self._rubber_origin = QtCore.QPoint(event.pos())
        QtWidgets.QTreeView.mousePressEvent(self, event)

    def mouseMoveEvent(self, event):
        if (
            self._drag_start_pos is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
            and self._drag_data_callback
        ):
            dist = (event.pos() - self._drag_start_pos).manhattanLength()
            half_d = max(2, _loader_drag_start_distance() // 2)
            if dist >= half_d:
                _maybe_arm_drag_precache(self)
            if dist >= _loader_drag_start_distance():
                self._cleanup_rubber_band()
                self._rubber_origin = None
                self._drag_start_pos = None
                self._clear_drag_cursor()
                mime_data, _, temp_path, raw_result = _build_drag_mime_data_core(
                    self
                )
                if mime_data is not None and raw_result is not None:
                    if _log and getattr(self, "_last_drag_summary", None):
                        _log.debug(
                            "mouseMoveEvent: fallback drag %s",
                            self._last_drag_summary,
                        )
                    _run_loader_drag(self, mime_data, temp_path, raw_result)
                    return

        if (
            self._rubber_origin is not None
            and event.buttons() & QtCore.Qt.MouseButton.LeftButton
        ):
            dist = (event.pos() - self._rubber_origin).manhattanLength()
            if dist >= 4:
                if self._rubber_band is None:
                    self._rubber_band = QtWidgets.QRubberBand(
                        QtWidgets.QRubberBand.Shape.Rectangle,
                        self.viewport(),
                    )
                self._rubber_band.setGeometry(
                    QtCore.QRect(self._rubber_origin, event.pos()).normalized()
                )
                self._rubber_band.show()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_start_pos = None
        self._drag_precache_armed = False
        self._clear_drag_cursor()
        if self._rubber_band is not None:
            rect = self._rubber_band.geometry()
            self._cleanup_rubber_band()
            self._rubber_origin = None
            sel = self.selectionModel()
            if rect.width() >= 1 and rect.height() >= 1 and sel is not None:
                indexes = _tree_row_indexes_intersecting_rect(self, rect)
                rows_flag = QtCore.QItemSelectionModel.SelectionFlag.Rows
                if event.modifiers() & QtCore.Qt.KeyboardModifier.ControlModifier:
                    for ix in indexes:
                        sel.select(
                            ix,
                            QtCore.QItemSelectionModel.SelectionFlag.Select
                            | rows_flag,
                        )
                else:
                    sel.clearSelection()
                    for ix in indexes:
                        sel.select(
                            ix,
                            QtCore.QItemSelectionModel.SelectionFlag.Select
                            | rows_flag,
                        )
            QtWidgets.QTreeView.mouseReleaseEvent(self, event)
            return

        self._rubber_origin = None
        self._cleanup_rubber_band()
        super().mouseReleaseEvent(event)

    def _build_drag_mime_data(self):
        mime_data, _, temp_path, _ = _build_drag_mime_data_core(self)
        return mime_data, (), temp_path

    def startDrag(self, supportedActions):
        if _log:
            _log.debug(
                "startDrag: entry supportedActions=%s",
                supportedActions,
            )
        try:
            mime_data, _, temp_path, raw_result = _build_drag_mime_data_core(self)
        except Exception as e:
            if _log:
                _log.debug(
                    "startDrag: _build_drag_mime_data_core raised %s",
                    e,
                    exc_info=True,
                )
            mime_data, temp_path, raw_result = None, None, None
        if _log:
            _log.debug(
                "startDrag: mime_data built=%s, fallback to super=%s",
                mime_data is not None,
                mime_data is None,
            )
        if mime_data is not None and raw_result is not None:
            if _log and getattr(self, "_last_drag_summary", None):
                _log.debug(
                    "startDrag: executing drag with custom mime_data %s",
                    self._last_drag_summary,
                )
            _run_loader_drag(self, mime_data, temp_path, raw_result)
            if _log:
                _log.debug("startDrag: drag finished")
            return
        model = self.model()
        sel = self.selectionModel()
        if model and sel:
            indexes = sel.selectedIndexes()
            model_mime = model.mimeData(indexes) if indexes else None
            if model_mime is not None and model_mime.hasFormat(
                LOADER_PAYLOAD_MIME_TYPE
            ):
                payload = decode_loader_drag_payload_from_mime(model_mime)
                if payload:
                    if _log:
                        _log.debug(
                            "startDrag: model mimeData %s",
                            _format_payload_summary_from_dict(payload),
                        )
                    mime_b, temp_b, raw_b = _remime_from_decoded_payload(
                        self, payload
                    )
                    if mime_b is not None and raw_b is not None:
                        _run_loader_drag(self, mime_b, temp_b, raw_b)
                        return
        if _log:
            _log.debug(
                "startDrag: no payload (product row only?); fallback to super"
            )
        super().startDrag(supportedActions)


class LoaderDragListView(QtWidgets.QListView):
    """IconMode list: marquee on empty viewport; grid drags originate from cards."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setDragEnabled(True)
        self.setDragDropMode(QtWidgets.QAbstractItemView.DragOnly)
        self._drag_data_callback = None
        self._drag_pixmap_context_callback = None
        self._drag_precache: Optional[DragPayloadPrecache] = None
        self._last_drag_summary = None
        self._drag_precache_armed = False
        self._source_drag_active_until_release = False
        self._source_drag_left_up_confirmations = 0

    def source_drag_guard_active(self) -> bool:
        return bool(self._source_drag_active_until_release)

    def begin_source_drag_guard(self) -> None:
        if self._source_drag_active_until_release:
            return
        self._source_drag_active_until_release = True
        self._source_drag_left_up_confirmations = 0
        gw = getattr(self, "_products_grid_owner", None)
        if gw is not None:
            gw.register_active_source_drag_list_view(self)

    def end_source_drag_guard(self) -> None:
        if not self._source_drag_active_until_release:
            return
        self._source_drag_active_until_release = False
        self._source_drag_left_up_confirmations = 0
        gw = getattr(self, "_products_grid_owner", None)
        if gw is not None:
            gw.clear_active_source_drag_list_view(self)

    def end_source_drag_guard_when_left_released(self) -> None:
        if not self._source_drag_active_until_release:
            return
        app = QtWidgets.QApplication.instance()
        left_down = (
            app is not None
            and (app.mouseButtons() & QtCore.Qt.MouseButton.LeftButton)
        )
        if left_down:
            self._source_drag_left_up_confirmations = 0
            QtCore.QTimer.singleShot(
                16, self.end_source_drag_guard_when_left_released
            )
            return
        self._source_drag_left_up_confirmations += 1
        if self._source_drag_left_up_confirmations < 3:
            QtCore.QTimer.singleShot(
                16, self.end_source_drag_guard_when_left_released
            )
            return
        self._source_drag_left_up_confirmations = 0
        self.end_source_drag_guard()

    def set_drag_data_callback(
        self, callback: Optional[Callable[[], Optional[tuple]]]
    ):
        self._drag_data_callback = callback

    def set_drag_pixmap_context_callback(
        self, callback: Optional[Callable[[], Optional[dict[str, Any]]]]
    ):
        self._drag_pixmap_context_callback = callback

    def set_drag_precache(self, cache: Optional[DragPayloadPrecache]) -> None:
        self._drag_precache = cache

    def mousePressEvent(self, event):
        if self.source_drag_guard_active():
            event.accept()
            return
        gw = getattr(self, "_products_grid_owner", None)
        if gw is not None and getattr(
            gw, "_active_source_drag_list_view", None
        ) is not None:
            event.accept()
            return
        if event.button() == QtCore.Qt.MouseButton.LeftButton:
            self._drag_precache_armed = False
            index = self.indexAt(event.pos())
            if not index.isValid():
                self.clearSelection()
                self.setCurrentIndex(QtCore.QModelIndex())
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self.source_drag_guard_active():
            event.accept()
            return
        gw = getattr(self, "_products_grid_owner", None)
        if gw is not None and getattr(
            gw, "_active_source_drag_list_view", None
        ) is not None:
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        self._drag_precache_armed = False
        if self.source_drag_guard_active():
            if event.button() == QtCore.Qt.MouseButton.LeftButton:
                self.end_source_drag_guard()
            event.accept()
            return
        gw = getattr(self, "_products_grid_owner", None)
        guard_lv = (
            getattr(gw, "_active_source_drag_list_view", None)
            if gw is not None
            else None
        )
        if guard_lv is not None:
            if (
                event.button() == QtCore.Qt.MouseButton.LeftButton
                and hasattr(guard_lv, "end_source_drag_guard")
            ):
                guard_lv.end_source_drag_guard()
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def _build_drag_mime_data(self):
        mime_data, _, temp_path, _ = _build_drag_mime_data_core(self)
        return mime_data, (), temp_path

    def startDrag(self, supportedActions):
        if self.source_drag_guard_active():
            return
        if _log:
            _log.debug(
                "startDrag: entry supportedActions=%s",
                supportedActions,
            )
        try:
            mime_data, _, temp_path, raw_result = _build_drag_mime_data_core(self)
        except Exception as e:
            if _log:
                _log.debug(
                    "startDrag: _build_drag_mime_data_core raised %s",
                    e,
                    exc_info=True,
                )
            mime_data, temp_path, raw_result = None, None, None
        if _log:
            _log.debug(
                "startDrag: mime_data built=%s, fallback to super=%s",
                mime_data is not None,
                mime_data is None,
            )
        if mime_data is not None and raw_result is not None:
            if _log and getattr(self, "_last_drag_summary", None):
                _log.debug(
                    "startDrag: executing drag with custom mime_data %s",
                    self._last_drag_summary,
                )
            _run_loader_drag(self, mime_data, temp_path, raw_result)
            return
        model = self.model()
        sel = self.selectionModel()
        if model and sel:
            indexes = sel.selectedIndexes()
            model_mime = model.mimeData(indexes) if indexes else None
            if model_mime is not None and model_mime.hasFormat(
                LOADER_PAYLOAD_MIME_TYPE
            ):
                payload = decode_loader_drag_payload_from_mime(model_mime)
                if payload:
                    if _log:
                        _log.debug(
                            "startDrag: model mimeData %s",
                            _format_payload_summary_from_dict(payload),
                        )
                    mime_b, temp_b, raw_b = _remime_from_decoded_payload(
                        self, payload
                    )
                    if mime_b is not None and raw_b is not None:
                        _run_loader_drag(self, mime_b, temp_b, raw_b)
                        return
        if _log:
            _log.debug(
                "startDrag: no payload (product row only?); fallback to super"
            )
        super().startDrag(supportedActions)


def _actions_sorter(item: tuple[ActionItem, str, str]):
    """Sort actions by order and then by their visible group/name."""

    action_item, group_label, label = item
    if group_label is None:
        group_label = label
        label = ""
    return action_item.order, group_label, label


def _split_representation_label(label: str):
    match = re.match(r"^(.+?)\s\(([^()]+)\)$", label)
    if not match:
        return None
    return match.group(1), match.group(2)


def _exec_menu_at(menu, global_point):
    exec_fn = getattr(menu, "exec", None)
    if exec_fn is None:
        exec_fn = menu.exec_
    return exec_fn(global_point)


def _action_payload_id(action):
    item_id = action.data()
    if hasattr(item_id, "toPyObject"):
        item_id = item_id.toPyObject()
    return item_id


def _action_targets_representations(action_item):
    if getattr(action_item, "representation_ids", None):
        return True

    data = action_item.data or {}
    if data.get("entity_type") == "representation":
        return True
    return (
        data.get("representation_id") is not None
        or data.get("representation_ids") is not None
    )


def show_actions_menu(
    action_items: list[ActionItem],
    global_point: QtCore.QPoint,
    one_item_selected: bool,
    parent: QtWidgets.QWidget,
    use_representation_submenus: bool = True,
) -> tuple[Optional[ActionItem], Optional[dict[str, Any]]]:
    selected_action_item = None
    selected_options = None

    action_items = [
        item for item in action_items
        if getattr(item, "show_in_context_menu", True)
    ]

    if not action_items:
        menu = QtWidgets.QMenu(parent)
        action = _get_no_loader_action(menu, one_item_selected)
        menu.addAction(action)
        _exec_menu_at(menu, global_point)
        return selected_action_item, selected_options

    menu = OptionalMenu(parent)

    representation_groups = {}
    flat_items = []
    for action_item in action_items:
        if (
            action_item.group_label is None
            and getattr(action_item, "representation_ids", None)
        ):
            split_label = _split_representation_label(action_item.label)
            if split_label:
                base_label, repre_label = split_label
                representation_groups.setdefault(base_label, []).append(
                    (repre_label, action_item)
                )
                continue
        flat_items.append(action_item)

    action_items_by_id = {}

    def _add_qaction_for_item(qmenu, item_label, action_item):
        item_id = uuid.uuid4().hex
        action_items_by_id[item_id] = action_item
        item_options = action_item.options
        icon = get_qt_icon(action_item.icon)
        use_option = bool(item_options)
        action = OptionalAction(
            item_label,
            icon,
            use_option,
            qmenu
        )
        if use_option:
            action.set_option_tip(item_options)
        tip = action_item.tooltip
        if tip:
            action.setToolTip(tip)
            action.setStatusTip(tip)
        action.setData(item_id)
        qmenu.addAction(action)
        return icon

    action_groups = {}
    root_entries = []
    for action_item in flat_items:
        group_label = action_item.group_label
        if group_label:
            action_groups.setdefault(group_label, []).append(action_item)
        else:
            root_entries.append((
                "action",
                action_item.order,
                action_item.label,
                (action_item, action_item.label),
            ))

    for group_label, items in action_groups.items():
        first_item = min(items, key=lambda item: (item.order, item.label))
        if (
            not use_representation_submenus
            and len(items) == 1
            and _action_targets_representations(first_item)
        ):
            root_entries.append((
                "action",
                first_item.order,
                group_label,
                (first_item, group_label),
            ))
            continue

        root_entries.append((
            "group",
            first_item.order,
            group_label,
            (group_label, items),
        ))

    for base_label, items in representation_groups.items():
        if len(items) == 1:
            _, action_item = items[0]
            item_label = action_item.label
            if not use_representation_submenus:
                item_label = base_label
            root_entries.append((
                "action",
                action_item.order,
                item_label,
                (action_item, item_label),
            ))
            continue
        first_item = min(items, key=lambda item: (item[1].order, item[0]))
        root_entries.append((
            "representation_group",
            first_item[1].order,
            base_label,
            (base_label, items),
        ))

    for entry_type, _, _, payload in sorted(
        root_entries, key=lambda item: (item[1], item[2])
    ):
        if entry_type == "action":
            action_item, item_label = payload
            _add_qaction_for_item(menu, item_label, action_item)
            continue

        if entry_type == "group":
            group_label, items = payload
            group_menu = OptionalMenu(group_label, menu)
            group_icon_set = False
            for action_item in sorted(
                items,
                key=lambda item: _actions_sorter(
                    (item, item.group_label, item.label)
                )
            ):
                icon = _add_qaction_for_item(
                    group_menu, action_item.label, action_item
                )
                if icon is not None and not group_icon_set:
                    group_menu.setIcon(icon)
                    group_icon_set = True
            menu.addMenu(group_menu)
            continue

        base_label, items = payload
        sub_menu = OptionalMenu(base_label, menu)
        sub_icon_set = False
        for repre_label, action_item in sorted(
            items, key=lambda item: (item[1].order, item[0].lower())
        ):
            icon = _add_qaction_for_item(
                sub_menu, repre_label, action_item
            )
            if icon is not None and not sub_icon_set:
                sub_menu.setIcon(icon)
                sub_icon_set = True
        menu.addMenu(sub_menu)

    action = _exec_menu_at(menu, global_point)
    if action is not None:
        item_id = _action_payload_id(action)
        selected_action_item = action_items_by_id.get(item_id)

    if selected_action_item is not None:
        selected_options = _get_options(action, selected_action_item, parent)

    return selected_action_item, selected_options


def _get_options(action, action_item, parent):
    """Provides dialog to select value from loader provided options.

    Loader can provide static or dynamically created options based on
    AttributeDefinitions, and for backwards compatibility qargparse.

    Args:
        action (OptionalAction) - Action object in menu.
        action_item (ActionItem) - Action item with context information.
        parent (QtCore.QObject) - Parent object for dialog.

    Returns:
        Union[dict[str, Any], None]: Selected value from attributes or
            'None' if dialog was cancelled.
    """

    # Pop option dialog
    options = action_item.options
    if not getattr(action, "optioned", False) or not options:
        return {}

    dialog_title = action.label + " Options"
    if isinstance(options[0], AbstractAttrDef):
        qargparse_options = False
        dialog = AttributeDefinitionsDialog(
            options, title=dialog_title, parent=parent
        )
    else:
        qargparse_options = True
        dialog = OptionDialog(parent)
        dialog.create(options)
        dialog.setWindowTitle(dialog_title)

    if not dialog.exec_():
        return None

    # Get option
    if qargparse_options:
        return dialog.parse()
    return dialog.get_values()


def _get_no_loader_action(menu, one_item_selected):
    """Creates dummy no loader option in 'menu'"""

    if one_item_selected:
        submsg = "this version."
    else:
        submsg = "your selection."
    msg = "No compatible loaders for {}".format(submsg)
    icon = qtawesome.icon(
        "fa.exclamation",
        color=QtGui.QColor(255, 51, 0)
    )
    return QtWidgets.QAction(icon, ("*" + msg), menu)


def show_loader_drop_rep_action_picker(
    repre_names_by_id: dict[str, str],
    actions_by_repre_id: dict[str, list[dict[str, Any]]],
    callback: Callable[[str, Optional[dict], dict, dict], None],
    parent: Optional[QtWidgets.QWidget] = None,
) -> bool:
    """Modal dialog: pick representation then loader action (ambiguous version reps)."""
    if not repre_names_by_id or not actions_by_repre_id:
        return False

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Choose representation and action")
    layout = QtWidgets.QVBoxLayout(dialog)
    row = QtWidgets.QHBoxLayout()
    rep_combo = QtWidgets.QComboBox()
    act_combo = QtWidgets.QComboBox()
    row.addWidget(QtWidgets.QLabel("Representation"))
    row.addWidget(rep_combo)
    row.addWidget(QtWidgets.QLabel("Action"))
    row.addWidget(act_combo)
    layout.addLayout(row)

    rids = sorted(
        repre_names_by_id.keys(),
        key=lambda x: (repre_names_by_id.get(x, "") or "").lower(),
    )
    for rid in rids:
        rep_combo.addItem(repre_names_by_id.get(rid, rid), rid)

    def refill_actions() -> None:
        act_combo.clear()
        rid = rep_combo.currentData()
        if rid is None:
            return
        acts = actions_by_repre_id.get(str(rid), [])
        for a in acts:
            act_combo.addItem(
                a.get("label", a.get("identifier", "?")),
                a,
            )

    rep_combo.currentIndexChanged.connect(lambda _i: refill_actions())
    refill_actions()

    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return False

    rid = rep_combo.currentData()
    action_dict = act_combo.currentData()
    if rid is None or not action_dict:
        return False

    data = dict(action_dict.get("data") or {})
    data["entity_ids"] = [str(rid)]
    callback(
        str(action_dict.get("identifier", "")),
        data,
        {},
        {},
    )
    return True


def show_loader_drop_action_picker(
    actions: list[dict[str, Any]],
    callback: Callable[[str, Optional[dict], dict, dict], None],
    parent: Optional[QtWidgets.QWidget] = None,
) -> bool:
    """Show a small modal to pick one loader action when multiple are available.

    Args:
        actions: List of dicts with "identifier", "data", "label" (and optionally
            "default_for_drag_drop"). Used when more than one drag-drop action
            is valid and none is the single default.
        callback: Callable(identifier, data, options, form_values) to run the
            chosen action. options and form_values can be empty dicts.
        parent: Parent widget for the dialog.

    Returns:
        True if user picked an action and callback was called, False if cancelled.
    """
    if not actions:
        return False
    if len(actions) == 1:
        a = actions[0]
        callback(
            a.get("identifier", ""),
            a.get("data"),
            {},
            {},
        )
        return True

    dialog = QtWidgets.QDialog(parent)
    dialog.setWindowTitle("Choose load action")
    layout = QtWidgets.QVBoxLayout(dialog)
    list_widget = QtWidgets.QListWidget()
    for a in actions:
        list_widget.addItem(a.get("label", a.get("identifier", "Unknown")))
    list_widget.setCurrentRow(0)
    layout.addWidget(list_widget)
    buttons = QtWidgets.QDialogButtonBox(
        QtWidgets.QDialogButtonBox.Ok | QtWidgets.QDialogButtonBox.Cancel
    )
    buttons.accepted.connect(dialog.accept)
    buttons.rejected.connect(dialog.reject)
    layout.addWidget(buttons)

    if dialog.exec_() != QtWidgets.QDialog.Accepted:
        return False

    row = list_widget.currentRow()
    if 0 <= row < len(actions):
        a = actions[row]
        callback(
            a.get("identifier", ""),
            a.get("data"),
            {},
            {},
        )
        return True
    return False
