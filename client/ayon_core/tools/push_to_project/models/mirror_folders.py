"""Mirror folder hierarchies between projects (shared by Loader and Push-to-Project)."""
from __future__ import annotations

import copy
import os
import tempfile
from collections import deque
from typing import Any, Callable, Optional

import ayon_api
from ayon_api.operations import OperationsSession, new_folder_entity


class MirrorFoldersError(Exception):
    """Raised when subtree mirroring cannot complete."""


def resolve_dst_folder_type(
    project_entity: dict[str, Any], src_folder_type: str
) -> str:
    """Match destination project folder type name to source type."""
    for folder_type in project_entity["folderTypes"]:
        if folder_type["name"].lower() == src_folder_type.lower():
            return folder_type["name"]

    raise MirrorFoldersError(
        f"'{src_folder_type}' folder type is not configured in project Anatomy."
    )


def copy_folder_thumbnail_to_project(
    src_project_name: str,
    src_folder_entity: dict[str, Any],
    dst_project_name: str,
) -> Optional[str]:
    """Copy folder thumbnail binary to destination project; return new id."""
    if not src_folder_entity.get("thumbnailId"):
        return None

    thumbnail = ayon_api.get_folder_thumbnail(
        src_project_name,
        src_folder_entity["id"],
        src_folder_entity["thumbnailId"],
    )
    if not thumbnail.id:
        return None

    with tempfile.NamedTemporaryFile(delete=False) as tmp_file:
        tmp_file.write(thumbnail.content)
        temp_file_path = tmp_file.name

    new_thumbnail_id = None
    try:
        new_thumbnail_id = ayon_api.create_thumbnail(
            dst_project_name, temp_file_path
        )
    finally:
        if os.path.exists(temp_file_path):
            os.remove(temp_file_path)
    return new_thumbnail_id


def create_folder_under_parent(
    operations: OperationsSession,
    *,
    src_folder_entity: dict[str, Any],
    dst_project_entity: dict[str, Any],
    parent_folder_entity: Optional[dict[str, Any]],
    folder_name: str,
    src_project_name: str,
    log_debug: Callable[[str], Any] = lambda _m: None,
    log_info: Callable[[str], Any] = lambda _m: None,
) -> dict[str, Any]:
    """Create one folder under parent; reuse name if sibling exists."""
    parent_id = None
    if parent_folder_entity:
        parent_id = parent_folder_entity["id"]

    folder_name_low = folder_name.lower()
    other_folder_entities = ayon_api.get_folders(
        dst_project_entity["name"],
        parent_ids=[parent_id],
        fields={"id", "name"},
    )
    for other_folder_entity in other_folder_entities:
        other_name = other_folder_entity["name"]
        if other_name.lower() != folder_name_low:
            continue

        log_debug(
            f'Found already existing folder with name "{other_name}"'
            f' which match requested name "{folder_name}"'
        )
        return ayon_api.get_folder_by_id(
            dst_project_entity["name"], other_folder_entity["id"]
        )

    data_keys = (
        "clipIn",
        "clipOut",
        "frameStart",
        "frameEnd",
        "handleStart",
        "handleEnd",
        "resolutionWidth",
        "resolutionHeight",
        "fps",
        "pixelAspect",
    )
    new_folder_attrib = {}
    src_attrib = src_folder_entity["attrib"]
    for attr_name, attr_value in src_attrib.items():
        if attr_name in data_keys:
            new_folder_attrib[attr_name] = attr_value

    new_folder_name = ayon_api.slugify_string(folder_name)
    folder_label = None
    if new_folder_name != folder_name:
        folder_label = folder_name

    src_folder_type = src_folder_entity["folderType"]
    dst_folder_type = resolve_dst_folder_type(
        dst_project_entity, src_folder_type
    )
    new_thumbnail_id = copy_folder_thumbnail_to_project(
        src_project_name, src_folder_entity, dst_project_entity["name"]
    )
    folder_entity = new_folder_entity(
        new_folder_name,
        dst_folder_type,
        parent_id=parent_id,
        attribs=new_folder_attrib,
        thumbnail_id=new_thumbnail_id,
    )
    if folder_label:
        folder_entity["label"] = folder_label

    operations.create_entity(
        dst_project_entity["name"], "folder", folder_entity
    )
    log_info(f'Creating new folder with name "{folder_name}"')

    parent_path = ""
    if parent_folder_entity:
        parent_path = parent_folder_entity["path"]
    folder_entity["path"] = "/".join([parent_path, folder_name])
    return folder_entity


def _collect_subtree_entities(
    src_project_name: str,
    root_folder_ids: list[str],
    *,
    include_descendants: bool = True,
) -> dict[str, dict[str, Any]]:
    """Folders to mirror: subtree under roots, or roots plus all ancestors.

    When ``include_descendants`` is True, performs BFS under each root (full
    subtree). When False, loads only the given folder ids and every ancestor
    up to the project root (no children of the selected folders).
    """
    entities_by_id: dict[str, dict[str, Any]] = {}

    if not include_descendants:
        pending = list(root_folder_ids)
        while pending:
            fid = pending.pop()
            if fid in entities_by_id:
                continue
            folder_entity = ayon_api.get_folder_by_id(
                src_project_name, fid, own_attributes=True
            )
            if not folder_entity:
                raise MirrorFoldersError(
                    f'Could not load folder id "{fid}" in "{src_project_name}"'
                )
            entities_by_id[fid] = folder_entity
            parent_id = folder_entity.get("parentId")
            if parent_id:
                pending.append(parent_id)
        return entities_by_id

    queue: deque[str] = deque()
    for fid in root_folder_ids:
        queue.append(fid)

    while queue:
        fid = queue.popleft()
        if fid in entities_by_id:
            continue
        folder_entity = ayon_api.get_folder_by_id(
            src_project_name, fid, own_attributes=True
        )
        if not folder_entity:
            raise MirrorFoldersError(
                f'Could not load folder id "{fid}" in "{src_project_name}"'
            )
        entities_by_id[fid] = folder_entity
        children = ayon_api.get_folders(
            src_project_name, parent_ids=[fid]
        )
        for ch in children:
            if ch["id"] not in entities_by_id:
                queue.append(ch["id"])
    return entities_by_id


def _sort_folders_parent_before_child(
    entities_by_id: dict[str, dict[str, Any]]
) -> list[dict[str, Any]]:
    """Topological order: shorter paths first."""
    return sorted(
        entities_by_id.values(),
        key=lambda fe: (len(fe.get("path") or ""), fe["name"]),
    )


def _mirror_tasks_for_folder(
    operations: OperationsSession,
    dst_project_entity: dict[str, Any],
    src_project_name: str,
    src_folder_id: str,
    dst_folder_entity: dict[str, Any],
) -> None:
    """Create tasks on dst folder from tasks on source folder."""
    src_tasks = ayon_api.get_tasks(
        src_project_name, folder_ids=[src_folder_id]
    )
    dst_project_name = dst_project_entity["name"]
    existing = {
        t["name"].lower(): t
        for t in ayon_api.get_tasks(
            dst_project_name, folder_ids=[dst_folder_entity["id"]]
        )
    }

    for src_task in src_tasks:
        name_lower = src_task["name"].lower()
        if name_lower in existing:
            continue
        src_task_type = src_task["taskType"]
        found = False
        for tt in dst_project_entity["taskTypes"]:
            if tt["name"].lower() == src_task_type.lower():
                found = True
                break
        if not found:
            raise MirrorFoldersError(
                f"'{src_task_type}' task type is not configured in "
                "destination project Anatomy."
            )

        operations.create_task(
            dst_project_name,
            src_task["name"],
            folder_id=dst_folder_entity["id"],
            task_type=src_task_type,
            attrib=copy.deepcopy(src_task.get("attrib") or {}),
        )


def mirror_source_path_under_parent(
    src_project_name: str,
    src_leaf_folder_id: str,
    dst_project_name: str,
    dst_parent_folder_id: Optional[str],
    *,
    include_tasks: bool = True,
    log_debug: Callable[[str], Any] = lambda _m: None,
    log_info: Callable[[str], Any] = lambda _m: None,
) -> dict[str, Any]:
    """Recreate the source folder chain (project root to leaf) under dst parent.

    Walks ``parentId`` from the source leaf up to the project root, then
    creates or matches each segment under ``dst_parent_folder_id`` (or project
    root when that is None).

    Returns:
        Destination folder entity dict for the source leaf.

    Raises:
        MirrorFoldersError: On validation or API failures.
    """
    dst_project_entity = ayon_api.get_project(dst_project_name)
    if not dst_project_entity:
        raise MirrorFoldersError(
            f"Destination project '{dst_project_name}' was not found"
        )

    dst_parent_entity = None
    if dst_parent_folder_id:
        dst_parent_entity = ayon_api.get_folder_by_id(
            dst_project_name, dst_parent_folder_id
        )
        if not dst_parent_entity:
            raise MirrorFoldersError(
                f'Could not find destination parent folder id '
                f'"{dst_parent_folder_id}" in project "{dst_project_name}"'
            )

    chain_rev: list[dict[str, Any]] = []
    cur_id: Optional[str] = src_leaf_folder_id
    while cur_id:
        folder_entity = ayon_api.get_folder_by_id(
            src_project_name, cur_id, own_attributes=True
        )
        if not folder_entity:
            raise MirrorFoldersError(
                f'Could not load folder id "{cur_id}" '
                f'in "{src_project_name}"'
            )
        chain_rev.append(folder_entity)
        cur_id = folder_entity.get("parentId")

    chain = list(reversed(chain_rev))
    if not chain:
        raise MirrorFoldersError("Source folder chain is empty")

    operations = OperationsSession()
    dst_cursor: Optional[dict[str, Any]] = dst_parent_entity

    for src_fe in chain:
        created = create_folder_under_parent(
            operations,
            src_folder_entity=src_fe,
            dst_project_entity=dst_project_entity,
            parent_folder_entity=dst_cursor,
            folder_name=src_fe["name"],
            src_project_name=src_project_name,
            log_debug=log_debug,
            log_info=log_info,
        )
        dst_cursor = created
        if include_tasks:
            _mirror_tasks_for_folder(
                operations,
                dst_project_entity,
                src_project_name,
                src_fe["id"],
                created,
            )

    operations.commit()
    assert dst_cursor is not None
    return dst_cursor


def mirror_folder_subtree(
    src_project_name: str,
    src_folder_ids: list[str],
    dst_project_name: str,
    dst_parent_folder_id: Optional[str],
    *,
    include_tasks: bool = True,
    include_products: bool = False,
    include_descendants: bool = True,
) -> dict[str, str]:
    """Mirror selected folders into dst project.

    With ``include_descendants`` True (default), mirrors each selected folder
    and all descendants. With False, mirrors only the selected folders and
    their ancestors (so hierarchy under the selection is preserved).

    Returns:
        Mapping src_folder_id -> dst_folder_id for every created or matched
        folder in the mirrored subtree.

    Raises:
        MirrorFoldersError: On validation or API failures.
        NotImplementedError: If ``include_products`` is True.
    """
    if include_products:
        raise NotImplementedError(
            "Mirroring products is not implemented yet."
        )

    dst_project_entity = ayon_api.get_project(dst_project_name)
    if not dst_project_entity:
        raise MirrorFoldersError(
            f"Destination project '{dst_project_name}' was not found"
        )

    dst_parent_entity = None
    if dst_parent_folder_id:
        dst_parent_entity = ayon_api.get_folder_by_id(
            dst_project_name, dst_parent_folder_id
        )
        if not dst_parent_entity:
            raise MirrorFoldersError(
                f'Could not find destination parent folder id "{dst_parent_folder_id}"'
                f' in project "{dst_project_name}"'
            )

    entities_by_id = _collect_subtree_entities(
        src_project_name,
        src_folder_ids,
        include_descendants=include_descendants,
    )
    ordered = _sort_folders_parent_before_child(entities_by_id)

    src_to_dst: dict[str, str] = {}
    operations = OperationsSession()

    for src_fe in ordered:
        src_id = src_fe["id"]
        parent_src_id = src_fe.get("parentId")

        if (
            parent_src_id is None
            or parent_src_id not in entities_by_id
        ):
            dst_par = dst_parent_entity
        elif parent_src_id in src_to_dst:
            dst_par_id = src_to_dst[parent_src_id]
            dst_par = ayon_api.get_folder_by_id(dst_project_name, dst_par_id)
        else:
            raise MirrorFoldersError(
                "Internal ordering error: parent not mirrored before child."
            )

        folder_name = src_fe["name"]
        created = create_folder_under_parent(
            operations,
            src_folder_entity=src_fe,
            dst_project_entity=dst_project_entity,
            parent_folder_entity=dst_par,
            folder_name=folder_name,
            src_project_name=src_project_name,
        )
        src_to_dst[src_id] = created["id"]

        if include_tasks:
            _mirror_tasks_for_folder(
                operations,
                dst_project_entity,
                src_project_name,
                src_id,
                created,
            )

    operations.commit()
    return src_to_dst
