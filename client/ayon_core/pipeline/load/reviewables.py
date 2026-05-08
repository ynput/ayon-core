"""Server reviewables as synthetic Loader representations.

Fetch list via REST, download with ``download_project_file``, tag
``data['__reviewable__']`` so :func:`get_representation_path` returns a
cache path without an anatomy template.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any

import ayon_api

log = logging.getLogger(__name__)

# Synthetic ids: ``reviewable:{version_id}:{file_id}``
# (see :func:`parse_reviewable_repre_id`).
REVIEWABLE_REPRE_ID_PREFIX = "reviewable:"


def is_reviewable_repre_id(repre_id: str | None) -> bool:
    """True if *repre_id* is a synthetic reviewable representation id."""
    if not repre_id or not isinstance(repre_id, str):
        return False
    if not repre_id.startswith(REVIEWABLE_REPRE_ID_PREFIX):
        return False
    rest = repre_id[len(REVIEWABLE_REPRE_ID_PREFIX) :]
    return ":" in rest


def make_reviewable_repre_id(version_id: str, file_id: str) -> str:
    """Build synthetic representation id for Loader rows and actions."""
    return f"{REVIEWABLE_REPRE_ID_PREFIX}{version_id}:{file_id}"


def parse_reviewable_repre_id(repre_id: str) -> tuple[str, str] | None:
    """Parse ``(version_id, file_id)`` from a synthetic id, or None."""
    if not is_reviewable_repre_id(repre_id):
        return None
    rest = repre_id[len(REVIEWABLE_REPRE_ID_PREFIX) :]
    version_id, file_id = rest.rsplit(":", 1)
    if not version_id or not file_id:
        return None
    return version_id, file_id


# Synthetic Loader product rows (REST reviewables as exclusive products).
REVIEWABLE_PRODUCT_ID_PREFIX = "reviewable-product:"
_REVIEWABLE_PRODUCT_SEP = "\x1f"


def is_reviewable_product_id(product_id: str | None) -> bool:
    """True if *product_id* is a synthetic reviewable product row."""
    if not product_id or not isinstance(product_id, str):
        return False
    return product_id.startswith(REVIEWABLE_PRODUCT_ID_PREFIX)


def make_reviewable_product_id(
    parent_product_id: str, version_id: str, file_id: str
) -> str:
    """Stable synthetic ``product`` id for one REST reviewable file."""
    return (
        f"{REVIEWABLE_PRODUCT_ID_PREFIX}{parent_product_id}"
        f"{_REVIEWABLE_PRODUCT_SEP}{version_id}"
        f"{_REVIEWABLE_PRODUCT_SEP}{file_id}"
    )


def parse_reviewable_product_id(
    product_id: str,
) -> tuple[str, str, str] | None:
    """Parse ``(parent_product_id, version_id, file_id)`` or None."""
    if not is_reviewable_product_id(product_id):
        return None
    rest = product_id[len(REVIEWABLE_PRODUCT_ID_PREFIX) :]
    parts = rest.split(_REVIEWABLE_PRODUCT_SEP)
    if len(parts) != 3:
        return None
    parent_pid, vid, fid = parts
    if not parent_pid or not vid or not fid:
        return None
    return parent_pid, vid, fid


def _norm_project_file_id(raw: Any) -> str | None:
    """Hex-only id for project files (strips hyphens from UUID)."""
    if raw is None:
        return None
    s = str(raw).strip()
    if not s:
        return None
    hx = re.sub(r"[^a-fA-F0-9]", "", s, flags=re.IGNORECASE)
    if len(hx) < 20:
        return None
    return hx.lower()


def _parse_version_reviewables_payload(payload: Any) -> list[tuple[str, str]]:
    """Parse REST ``GET .../versions/{version_id}/reviewables`` JSON."""
    found: list[tuple[str, str]] = []
    seen: set[str] = set()
    blocks: list[dict[str, Any]] = []
    if isinstance(payload, list) and payload:
        if all(
            isinstance(x, dict) and ("fileId" in x or "file_id" in x)
            for x in payload
        ) and not any(
            "reviewables" in x for x in payload if isinstance(x, dict)
        ):
            blocks = [{"reviewables": list(payload)}]
        else:
            for item in payload:
                if isinstance(item, dict):
                    blocks.append(item)
    elif isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict):
                blocks.append(item)
    elif isinstance(payload, dict):
        if "reviewables" in payload and isinstance(
            payload.get("reviewables"), list
        ):
            blocks.append(payload)
        elif "data" in payload and isinstance(payload.get("data"), list):
            return _parse_version_reviewables_payload(payload["data"])
        else:
            return found
    else:
        return found
    for block in blocks:
        relist = block.get("reviewables")
        if not isinstance(relist, list):
            continue
        for i, rev in enumerate(relist):
            if not isinstance(rev, dict):
                continue
            fid = rev.get("fileId") or rev.get("file_id")
            label = (
                rev.get("label")
                or rev.get("filename")
                or rev.get("name")
                or f"reviewable_{i}"
            )
            if not isinstance(label, str):
                label = str(label)
            nf = _norm_project_file_id(fid) if isinstance(fid, str) else None
            if nf and nf not in seen:
                seen.add(nf)
                found.append((nf, label[:200]))
    return found


def _fetch_reviewable_tuples_from_rest(
    project_name: str,
    version_id: str,
    *,
    debug: dict[str, Any] | None = None,
) -> list[tuple[str, str]]:
    """REST ``.../versions/.../reviewables`` — file ids and labels."""
    if not hasattr(ayon_api, "get_server_api_connection"):
        if debug is not None:
            debug["error"] = "no get_server_api_connection"
        return []
    con = ayon_api.get_server_api_connection()
    get = getattr(con, "get", None)
    if not callable(get):
        if debug is not None:
            debug["error"] = "connection has no get()"
        return []
    rel = f"projects/{project_name}/versions/{version_id}/reviewables"
    paths = (rel, f"api/{rel}")
    last_pair: list[tuple[str, str]] = []
    path_status: list[tuple[str, int]] = []
    for path in paths:
        if debug is not None:
            debug["path_tried"] = path
        try:
            r = get(path)
        except Exception as exc:  # noqa: BLE001
            if debug is not None:
                debug["exception"] = repr(exc)
            continue
        code = int(getattr(r, "status_code", 0) or 0) if r is not None else 0
        path_status.append((path, code))
        if debug is not None:
            debug["status_code"] = code
        if r is None or code >= 400:
            last_pair = []
            continue
        if hasattr(r, "json"):
            try:
                payload = r.json()
            except Exception as exc:  # noqa: BLE001
                if debug is not None:
                    debug["json_error"] = repr(exc)
                continue
        elif isinstance(r, (list, dict)):
            payload = r
        elif hasattr(r, "data") and r.data is not None:
            payload = r.data
        else:
            if debug is not None:
                debug["response_type"] = type(r).__name__
            continue
        last_pair = _parse_version_reviewables_payload(payload)
        if last_pair:
            return last_pair
    if debug is not None:
        debug["path_status"] = path_status
    return []


def loader_synthetic_representation_name(rest_label: str, file_id: str) -> str:
    """Unique Loader row label for one server reviewable under a version.

    Multiple reviewables can share the same type (e.g. two PNGs); include a
    short file id tail so representation rows stay distinguishable.
    """
    hx = _norm_project_file_id(file_id)
    tail = hx[:8] if hx else ""
    if not tail:
        hx2 = re.sub(
            r"[^a-fA-F0-9]", "", str(file_id), flags=re.IGNORECASE
        ).lower()
        tail = hx2[:8] if len(hx2) >= 8 else hx2
    base = os.path.basename(rest_label.strip()) or "reviewable"
    stem, ext = os.path.splitext(base)
    stem_clean = re.sub(r"[^0-9A-Za-z._-]", "_", stem.strip("_"))[:48]
    if not stem_clean:
        stem_clean = "reviewable"
    ext_clean = ext.lower().lstrip(".")[:16]
    short = f"{stem_clean}.{ext_clean}" if ext_clean else stem_clean
    return f"{short}__{tail}" if tail else short


def representation_name_from_label(label: str) -> str:
    """Loader representation *name* (extension) from filename or label."""
    base = os.path.basename(label.strip()) or "reviewable"
    _, ext = os.path.splitext(base)
    if ext:
        return ext.lower().lstrip(".")[:32]
    # Common extensions in labels without dot
    lower = label.lower()
    for token in (
        "mov",
        "mp4",
        "webm",
        "mkv",
        "avi",
        "jpg",
        "jpeg",
        "png",
        "gif",
    ):
        if token in lower:
            return token
    return "reviewable"


def list_version_reviewables(
    project_name: str, version_id: str
) -> list[tuple[str, str]]:
    """``(file_id, label)`` for *version_id* (REST reviewables list only)."""
    return _fetch_reviewable_tuples_from_rest(project_name, version_id)


def reviewable_cache_dir(project_name: str, version_id: str) -> Path:
    """Root directory for cached reviewable files for a version."""
    return (
        Path.home()
        / ".ayon"
        / "reviewable-cache"
        / project_name.replace("/", "_")
        / version_id
    )


def _safe_label_segment(label: str) -> str:
    s = re.sub(r"[^0-9A-Za-z._-]", "_", label.strip())[:120]
    return s or "reviewable"


def materialize_reviewable(
    project_name: str,
    version_id: str,
    file_id: str,
    label: str,
) -> str:
    """Download if needed; return absolute path to cached file."""
    dlp = getattr(ayon_api, "download_project_file", None)
    if not callable(dlp):
        raise RuntimeError("ayon_api.download_project_file is not available")

    cache_dir = reviewable_cache_dir(project_name, version_id)
    cache_dir.mkdir(parents=True, exist_ok=True)
    fname = f"{file_id}__{_safe_label_segment(label)}"
    dest = cache_dir / fname
    if dest.is_file() and dest.stat().st_size > 0:
        return str(dest.resolve())

    tmp = cache_dir / (fname + ".partial")
    try:
        dlp(project_name=project_name, file_id=file_id, filepath=str(tmp))
    except TypeError:
        dlp(project_name, file_id, str(tmp))
    if not tmp.is_file() or tmp.stat().st_size == 0:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        _fid = file_id[:16]
        raise RuntimeError(
            f"download_project_file produced empty file (file_id={_fid}…)"
        )
    tmp.replace(dest)
    return str(dest.resolve())


def build_synthetic_repre_entity(
    project_name: str,
    version_id: str,
    file_id: str,
    label: str,
) -> dict[str, Any]:
    """Minimal representation dict for Loader contexts / path resolution."""
    name = representation_name_from_label(label)
    repre_id = make_reviewable_repre_id(version_id, file_id)
    return {
        "id": repre_id,
        "name": name,
        "versionId": version_id,
        "data": {
            "__reviewable__": {
                "project_name": project_name,
                "version_id": version_id,
                "file_id": file_id,
                "label": label,
            }
        },
    }
