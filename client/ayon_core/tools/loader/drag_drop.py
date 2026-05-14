"""Drag-and-drop payload encoding/decoding for Loader tool.

MIME type and JSON payload format for dragging loader actions from the Loader
UI into the host. Hosts can decode the payload and run the same action via
trigger_action_item. Drag to an AYON host (e.g. DCC) to load; dropping on
desktop or file explorer does not copy files (payload is host-specific).
"""
from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any, List, Optional

import ayon_api

from ayon_core.lib import Logger
from ayon_core.pipeline.load import (
    filter_repre_contexts_by_loader,
    get_representation_contexts_by_ids,
)
from ayon_core.tools.loader.abstract import ActionItem

LOADER_PAYLOAD_MIME_TYPE = "application/x-ayon-loader-payload"

"""Prefix for temp file used in OS DnD bridge (e.g. Unity). File name: ayon_loader_<uuid>.json."""
LOADER_PAYLOAD_TEMP_PREFIX = "ayon_loader_"

_log = Logger.get_logger(__name__)

# Serialized loader action identifier (matches models.actions.LOADER_PLUGIN_ID).
_LOADER_PLUGIN_ID = "__loader_plugin__"


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
        return None
    if not mime_data.hasFormat(LOADER_PAYLOAD_MIME_TYPE):
        return None
    raw = mime_data.data(LOADER_PAYLOAD_MIME_TYPE)
    if not raw:
        return None
    try:
        data = json.loads(bytes(raw).decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        _log.debug("Loader drag payload decode failed: %s", e, exc_info=True)
        return None
    if not isinstance(data, dict):
        return None
    if "project_name" not in data or "entity_type" not in data or "actions" not in data:
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
        return None
    if "project_name" not in data or "entity_type" not in data or "actions" not in data:
        return None
    if data.get("entity_type") not in ("version", "representation"):
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


def _plugin_name_from_action(action: dict[str, Any]) -> Optional[str]:
    """Loader class name from a serialized Loader action item."""
    ident = action.get("identifier")
    data = action.get("data") or {}
    if ident == _LOADER_PLUGIN_ID:
        plug = data.get("loader")
        return str(plug) if plug else None
    if ident:
        return str(ident)
    return None


def _ordered_actions_for_pick(
    actions: List[dict[str, Any]],
) -> List[dict[str, Any]]:
    """Order actions like LoaderWindow.dropEvent (defaults first)."""
    if len(actions) <= 1:
        return list(actions)
    defaults = [a for a in actions if a.get("default_for_drag_drop")]
    if len(defaults) == 1:
        return defaults
    if defaults:
        chosen = {id(a) for a in defaults}
        rest = [a for a in actions if id(a) not in chosen]
        return defaults + rest
    return list(actions)


def _pick_one_repre_id_from_group(
    repres: List[dict[str, Any]],
) -> Optional[str]:
    """Pick one representation id from a version's reps (Loader DnD fallback)."""
    if not repres:
        return None

    def _is_thumb(r: dict[str, Any]) -> bool:
        return (r.get("name") or "").lower() == "thumbnail"

    non_thumb = [r for r in repres if not _is_thumb(r)]
    pool = non_thumb if non_thumb else repres
    sorted_pool = sorted(
        pool,
        key=lambda r: ((r.get("name") or ""), str(r.get("id") or "")),
    )
    rid = sorted_pool[0].get("id")
    return str(rid) if rid else None


def _repre_ids_one_per_version_from_payload(
    project_name: str,
    version_ids: List[str],
    payload: dict[str, Any],
) -> Optional[List[str]]:
    """Resolve version drag to one representation id per version id."""
    dd = payload.get("default_repre_ids_by_version_id") or {}
    need_fetch: List[str] = []
    for vid in version_ids:
        vs = str(vid)
        cands = dd.get(vid)
        if cands is None:
            cands = dd.get(vs)
        cands = list(cands or [])
        if not cands:
            need_fetch.append(vs)

    repres_by_vid: dict[str, List[dict[str, Any]]] = {}
    if need_fetch:
        try:
            fetched = ayon_api.get_representations(
                project_name,
                version_ids=need_fetch,
            )
        except Exception as exc:
            _log.debug(
                "resolve_loader_drop: get_representations failed: %s",
                exc,
            )
            return None
        for r in fetched or []:
            vkey = r.get("versionId")
            if vkey is None:
                continue
            repres_by_vid.setdefault(str(vkey), []).append(r)

    out: List[str] = []
    for vid in version_ids:
        vs = str(vid)
        cands = dd.get(vid)
        if cands is None:
            cands = dd.get(vs)
        cands = list(cands or [])
        if cands:
            out.append(str(cands[0]))
            continue
        picked = _pick_one_repre_id_from_group(repres_by_vid.get(vs, []))
        if not picked:
            _log.debug(
                "resolve_loader_drop: could not pick representation "
                "for version %s",
                vs,
            )
            return None
        out.append(picked)

    return out


def _fallback_sort_key(
    loader_cls: Any,
    fallback_class_order: Optional[tuple[str, ...]],
) -> tuple[Any, ...]:
    name = getattr(loader_cls, "__name__", "")
    order = getattr(loader_cls, "order", 999)
    if not fallback_class_order:
        return (order, name)
    try:
        pref_idx = fallback_class_order.index(name)
    except ValueError:
        pref_idx = len(fallback_class_order)
    return (pref_idx, order, name)


def _pick_loader_for_context(
    ctx: dict[str, Any],
    actions_ordered: List[dict[str, Any]],
    loaders: List[Any],
    host_name: str,
    fallback_class_order: Optional[tuple[str, ...]],
) -> Optional[Any]:
    """Return loader class that accepts ``ctx`` alone, or None."""
    loaders_by_name = {
        getattr(c, "__name__", ""): c for c in loaders if getattr(c, "__name__", "")
    }

    for action in actions_ordered:
        plug_name = _plugin_name_from_action(action)
        if not plug_name:
            continue
        loader_cls = loaders_by_name.get(plug_name)
        if loader_cls is None:
            continue
        if host_name not in getattr(loader_cls, "hosts", []):
            continue
        try:
            inst = loader_cls()
            filt = filter_repre_contexts_by_loader([ctx], inst)
            if len(filt) == 1:
                return loader_cls
        except Exception:
            continue

    compatible: list[Any] = []
    for loader_cls in loaders:
        if host_name not in getattr(loader_cls, "hosts", []):
            continue
        try:
            inst = loader_cls()
            filt = filter_repre_contexts_by_loader([ctx], inst)
            if len(filt) == 1:
                compatible.append(loader_cls)
        except Exception:
            continue
    if not compatible:
        return None
    compatible.sort(
        key=lambda c: _fallback_sort_key(c, fallback_class_order),
    )
    return compatible[0]


def _skip_reason_no_loader(ctx: dict[str, Any], host_name: str) -> str:
    prod = ctx.get("product") or {}
    rep = ctx.get("representation") or {}
    ctx_rep = rep.get("context") or {}
    return (
        "no compatible loader for host=%r productType=%r "
        "productBaseType=%r rep_name=%r ext=%r"
        % (
            host_name,
            prod.get("productType"),
            prod.get("productBaseType"),
            rep.get("name"),
            ctx_rep.get("ext"),
        )
    )


def resolve_loader_drop_per_context(
    payload: dict[str, Any],
    get_loaders: Callable[[str], List[Any]],
    host_name: str,
    *,
    drop_context_id: Optional[str] = None,
    pick_one_repre_per_version: bool = False,
    fallback_class_order: Optional[tuple[str, ...]] = None,
) -> tuple[list[tuple[Any, dict[str, Any]]], list[tuple[Optional[dict[str, Any]], str]]]:
    """Resolve drag payload to one (loader class, context) pair per representation.

    Each context gets an independently chosen loader (heterogeneous drops).
    Contexts with no compatible host loader are listed in ``skipped`` only.

    Args:
        payload: Raw or decoded loader drag dict (see ``decode_loader_drag_payload``).
        get_loaders: ``project_name ->`` list of loader plugin classes.
        host_name: Current host key (e.g. ``\"harmony\"``, ``\"photoshop\"``).
        drop_context_id: If set, filter serialized actions by drop surface.
        pick_one_repre_per_version: When entity type is ``version``, pick one
            representation per version (Harmony) vs. expand all reps (Photoshop).
        fallback_class_order: Optional class-name tie-break order for fallback
            loader choice when multiple loaders accept the same context.

    Returns:
        ``(pairs, skipped)`` where ``pairs`` is ``[(loader_cls, ctx), ...]`` and
        ``skipped`` is ``[(ctx_or_None, reason), ...]``.
    """
    skipped: list[tuple[Optional[dict[str, Any]], str]] = []
    decoded = decode_loader_drag_payload(payload)
    if not decoded:
        skipped.append((None, "invalid or undecodable payload"))
        return [], skipped

    merged = dict(decoded)
    merged["actions"] = filter_actions_by_drop_context(merged, drop_context_id)

    project_name = merged.get("project_name")
    entity_type = merged.get("entity_type")
    entity_ids = list(merged.get("entity_ids") or [])

    if merged.get("needs_rep_choice") and entity_type == "version":
        dd = merged.get("default_repre_ids_by_version_id") or {}
        picked: list[str] = []
        for vid in entity_ids:
            cands = dd.get(vid)
            if cands is None:
                cands = dd.get(str(vid))
            cands = cands or []
            if cands:
                picked.append(str(cands[0]))
        if picked:
            entity_ids = picked
            entity_type = "representation"

    if not project_name or not entity_ids or entity_type not in (
        "version",
        "representation",
    ):
        skipped.append((None, "missing project_name, entity_ids, or entity_type"))
        return [], skipped

    if entity_type == "representation":
        repre_ids = [str(x) for x in entity_ids]
    elif pick_one_repre_per_version:
        resolved = _repre_ids_one_per_version_from_payload(
            str(project_name),
            list(entity_ids),
            merged,
        )
        if not resolved:
            skipped.append((None, "could not resolve version ids to repre ids"))
            return [], skipped
        repre_ids = resolved
    else:
        try:
            repres = ayon_api.get_representations(
                str(project_name),
                version_ids=entity_ids,
            )
            repre_ids = [r["id"] for r in repres] if repres else []
        except Exception as exc:
            _log.debug(
                "resolve_loader_drop: get_representations failed: %s",
                exc,
            )
            skipped.append((None, "get_representations failed: %s" % exc))
            return [], skipped
        if not repre_ids:
            skipped.append((None, "no representations for version ids"))
            return [], skipped

    try:
        contexts_by_id = get_representation_contexts_by_ids(
            str(project_name),
            repre_ids,
        )
    except Exception as exc:
        skipped.append((None, "get_representation_contexts_by_ids: %s" % exc))
        return [], skipped

    contexts: list[dict[str, Any]] = []
    for rid in repre_ids:
        c = contexts_by_id.get(rid) or contexts_by_id.get(str(rid))
        if c and all(
            c.get(k)
            for k in (
                "project",
                "folder",
                "product",
                "version",
                "representation",
            )
        ):
            contexts.append(c)

    if not contexts:
        skipped.append((None, "no valid representation contexts"))
        return [], skipped

    try:
        loaders = list(get_loaders(str(project_name)))
    except Exception as exc:
        skipped.append((None, "get_loaders failed: %s" % exc))
        return [], skipped

    actions_ordered = _ordered_actions_for_pick(merged.get("actions") or [])
    pairs: list[tuple[Any, dict[str, Any]]] = []
    for ctx in contexts:
        loader_cls = _pick_loader_for_context(
            ctx,
            actions_ordered,
            loaders,
            host_name,
            fallback_class_order,
        )
        if loader_cls is None:
            skipped.append((ctx, _skip_reason_no_loader(ctx, host_name)))
            continue
        pairs.append((loader_cls, ctx))

    return pairs, skipped
