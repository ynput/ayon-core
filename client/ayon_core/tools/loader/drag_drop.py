"""Drag-and-drop payload encoding/decoding for Loader tool.

MIME type and JSON payload format for dragging loader actions from the Loader
UI into the host. Hosts can decode the payload and run the same action via
trigger_action_item. Drag to an AYON host (e.g. DCC) to load; dropping on
desktop or file explorer does not copy files (payload is host-specific).
"""
from __future__ import annotations

import json
from typing import Any, Optional

from ayon_core.lib import Logger
from ayon_core.tools.loader.abstract import ActionItem

LOADER_PAYLOAD_MIME_TYPE = "application/x-ayon-loader-payload"

"""Prefix for temp file used in OS DnD bridge (e.g. Unity). File name: ayon_loader_<uuid>.json."""
LOADER_PAYLOAD_TEMP_PREFIX = "ayon_loader_"

_log = Logger.get_logger(__name__)


def _serialize_action_item(item: ActionItem) -> dict[str, Any]:
    return {
        "identifier": item.identifier,
        "data": item.data,
        "label": item.label,
        "default_for_drag_drop": getattr(
            item, "default_for_drag_drop", False
        ),
        "drag_drop_contexts": (
            list(item.drag_drop_contexts)
            if getattr(item, "drag_drop_contexts", None)
            else None
        ),
    }


def encode_loader_drag_payload(
    project_name: str,
    entity_type: str,
    entity_ids: list[str],
    action_items: list[ActionItem],
    *,
    default_repre_ids_by_version_id: Optional[dict[str, list[str]]] = None,
    needs_rep_choice: bool = False,
    actions_by_repre_id: Optional[dict[str, list[ActionItem]]] = None,
    repre_names_by_id: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    """Build JSON-serializable payload for loader drag.

    Args:
        project_name: Project name.
        entity_type: "version" or "representation".
        entity_ids: List of version or representation ids.
        action_items: Action items with drag_drop_enabled (caller must filter).
        default_repre_ids_by_version_id: Optional per-version ordered candidate
            representation ids when drag defaults are ambiguous.
        needs_rep_choice: True when user must pick representation + action (Loader UI).
        actions_by_repre_id: Per-representation drag-drop actions when needs_rep_choice.
        repre_names_by_id: Display names for representation ids (needs_rep_choice).

    Returns:
        Dict suitable for json.dumps and decode_loader_drag_payload.
    """
    actions = [_serialize_action_item(item) for item in action_items]
    out: dict[str, Any] = {
        "project_name": project_name,
        "entity_type": entity_type,
        "entity_ids": list(entity_ids),
        "actions": actions,
    }
    if default_repre_ids_by_version_id:
        out["default_repre_ids_by_version_id"] = {
            k: list(v) for k, v in default_repre_ids_by_version_id.items()
        }
    if needs_rep_choice:
        out["needs_rep_choice"] = True
        if repre_names_by_id:
            out["repre_names_by_id"] = dict(repre_names_by_id)
        if actions_by_repre_id:
            out["actions_by_repre_id"] = {
                rid: [_serialize_action_item(a) for a in items]
                for rid, items in actions_by_repre_id.items()
            }
    return out


def _json_serializable_default(obj: Any) -> Any:
    """Convert non-JSON types for dumps (e.g. set -> list)."""
    if isinstance(obj, set):
        return list(obj)
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def loader_payload_to_bytes(payload: dict[str, Any]) -> bytes:
    """Serialize payload for QMimeData.setData."""
    return json.dumps(payload, default=_json_serializable_default).encode("utf-8")


def decode_loader_drag_payload_from_mime(mime_data: Any) -> Optional[dict[str, Any]]:
    """Decode loader drag payload from Qt QMimeData.

    Args:
        mime_data: QMimeData instance (e.g. from drop event).

    Returns:
        Decoded payload dict with project_name, entity_type, entity_ids, actions,
        or None if not a valid loader payload.
    """
    if mime_data is None:
        _log.debug("Loader drag payload decode skipped: mime_data is None")
        return None
    if not mime_data.hasFormat(LOADER_PAYLOAD_MIME_TYPE):
        _log.debug("Loader drag payload decode skipped: wrong MIME type")
        return None
    raw = mime_data.data(LOADER_PAYLOAD_MIME_TYPE)
    if not raw:
        _log.debug("Loader drag payload decode skipped: empty MIME data")
        return None
    try:
        data = json.loads(bytes(raw).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        _log.debug("Loader drag payload decode failed: %s", e)
        return None
    if not isinstance(data, dict):
        _log.debug("Loader drag payload decode skipped: root is not dict")
        return None
    if "project_name" not in data or "entity_type" not in data or "actions" not in data:
        _log.debug(
            "Loader drag payload decode skipped: missing required keys"
        )
        return None
    return data


def decode_loader_drag_payload(data: dict[str, Any]) -> Optional[dict[str, Any]]:
    """Decode loader drag payload from a dict (e.g. from JSON).

    Args:
        data: Dict with project_name, entity_type, entity_ids, actions.

    Returns:
        The same dict if valid, or None.
    """
    if not data or not isinstance(data, dict):
        _log.debug("Loader drag payload decode skipped: invalid data type")
        return None
    if "project_name" not in data or "entity_type" not in data or "actions" not in data:
        _log.debug(
            "Loader drag payload decode skipped: missing required keys"
        )
        return None
    if data.get("entity_type") not in ("version", "representation"):
        _log.debug(
            "Loader drag payload decode skipped: invalid entity_type"
        )
        return None
    return data


def filter_actions_by_drop_context(
    payload: dict[str, Any],
    drop_context_id: Optional[str],
) -> list[dict[str, Any]]:
    """Filter payload actions by drop context.

    Args:
        payload: Decoded payload from decode_loader_drag_payload.
        drop_context_id: Context id at drop location; None means no filter.

    Returns:
        List of action dicts (identifier, data, label, default_for_drag_drop) that
        are valid for the drop context.
    """
    actions = payload.get("actions") or []
    if not drop_context_id:
        return actions
    out = []
    for a in actions:
        contexts = a.get("drag_drop_contexts")
        if contexts is None:
            out.append(a)
            continue
        if drop_context_id in contexts:
            out.append(a)
    return out
