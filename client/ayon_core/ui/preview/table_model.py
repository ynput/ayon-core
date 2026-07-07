from __future__ import annotations

from typing import Any, Callable
import random
import sys

from qtpy.QtWidgets import QApplication

from ayon_core.ui.components.table_model import (
    PaginatedTableModel,
    BatchFetchRequest,
)


TABLE_TEST_DATA: list[dict[str, Any]] = [
    {
        "name": f"Asset {i:03d}",
        "status": [
            "Not ready",
            "Ready to start",
            "In progress",
            "Pending review",
            "Approved",
            "On hold",
            "Omitted",
        ][i % 7],
        "status__icon": [
            "fiber_new",
            "timer",
            "play_arrow",
            "visibility",
            "task_alt",
            "back_hand",
            "block",
        ][i % 7],
        "status__color": [
            "#434a56",
            "#bababa",
            "#3498db",
            "#ff9b0a",
            "#00f0b4",
            "#fa6e46",
            "#cb1a1a",
        ][i % 7],
        "type": random.choice(
            [
                "Model",
                "Texture",
                "Rig",
                "Animation",
                "Look-dev",
                "Compositing",
                "Grading",
            ]
        ),
        "author": random.choice(
            [
                "Alice",
                "Bob",
                "Charlie",
                "Diana",
                "Steve",
                "Eva",
                "Frank",
                "Grace",
            ]
        ),
        "version": f"v{(i % 10) + 1:03d}",
    }
    for i in range(200)
]


def make_test_fetch(
    data: list[dict[str, Any]],
) -> Callable[[int, int, str | None, bool, str | None], list[dict[str, Any]]]:
    """Create a flat fetch_page callback from static data.

    ``parent_id`` is accepted but ignored — all data lives at root level.

    Args:
        data: The full dataset to paginate.

    Returns:
        A callable suitable for PaginatedTableModel.
    """

    def _fetch(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None = None,  # noqa: ARG001
    ) -> list[dict[str, Any]]:
        print(
            f"[test]  Fetching page {page} (page_size={page_size}, "
            f"sort_key={sort_key!r}, descending={descending})"
        )
        rows = data
        if sort_key:
            rows = sorted(
                data,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page * page_size
        end = start + page_size
        return rows[start:end]

    return _fetch


# ---------------------------------------------------------------------------
# Hierarchical test data
# ---------------------------------------------------------------------------

_FOLDER_ICON = "folder"
_FOLDER_COLOR = "#8898a8"


def _make_hierarchical_test_data(
    n: int,
    subfolders_per_root: int = 8,
) -> dict[str | None, list[dict[str, Any]]]:
    """Generate hierarchical test data with a configurable number of leaf
    entries.

    Two root folders (Assets, Shots) are always present.  Under each,
    ``subfolders_per_root`` sub-folders are generated from a fixed name
    pool.  Leaf entries are distributed as evenly as possible across all
    sub-folders.

    The function is deterministic: the same arguments always produce the
    same dataset because a seeded :class:`random.Random` instance is
    used internally.

    Args:
        n: Total number of leaf entries to generate.
        subfolders_per_root: Number of sub-folders to create under each
            root folder.  Capped at 10 for asset folders (the size of
            the name pool); shot folders are auto-named so there is no
            cap.

    Returns:
        A mapping of parent_id -> list[row_dict] suitable for use with
        :func:`_make_hierarchical_test_fetch`.
    """
    rng = random.Random(42)

    _statuses = [
        ("Not ready", "fiber_new", "#434a56"),
        ("Ready to start", "timer", "#bababa"),
        ("In progress", "play_arrow", "#3498db"),
        ("Pending review", "visibility", "#ff9b0a"),
        ("Approved", "task_alt", "#00f0b4"),
        ("On hold", "back_hand", "#fa6e46"),
        ("Omitted", "block", "#cb1a1a"),
    ]
    _asset_folder_pool = [
        "Hero",
        "Villain",
        "Sidekick",
        "Creature",
        "NPC_A",
        "NPC_B",
        "Prop_Vehicle",
        "Prop_Furniture",
        "Environment_City",
        "Environment_Forest",
    ]
    _asset_task_names = ["model", "rig", "lookdev", "texture", "layout"]
    _asset_types = ["Model", "Texture", "Rig", "Look-dev"]
    _shot_task_names = [
        "Animation",
        "Lighting",
        "Compositing",
        "Grading",
        "FX",
    ]
    _shot_types = ["Animation", "Lighting", "Compositing", "Grading"]
    _authors = ["Alice", "Bob", "Carol", "Dave", "Eve", "Frank", "Grace"]

    num_asset = min(subfolders_per_root, len(_asset_folder_pool))
    asset_names = _asset_folder_pool[:num_asset]
    asset_ids = [name.lower() for name in asset_names]

    num_shots = subfolders_per_root
    shot_names = [f"SH{(i + 1) * 10:03d}" for i in range(num_shots)]
    shot_ids = [name.lower() for name in shot_names]

    total_subfolders = num_asset + num_shots
    base, remainder = divmod(n, total_subfolders)
    counts = [
        base + (1 if i < remainder else 0) for i in range(total_subfolders)
    ]
    asset_counts = counts[:num_asset]
    shot_counts = counts[num_asset:]

    def _make_entries(
        parent_id: str,
        count: int,
        task_names: list[str],
        task_types: list[str],
    ) -> list[dict[str, Any]]:
        entries = []
        for i in range(count):
            status, icon, color = rng.choice(_statuses)
            entries.append(
                {
                    "id": f"{parent_id}_{i:04d}",
                    "name": rng.choice(task_names),
                    "name__icon": "package_2",
                    "status": status,
                    "status__icon": icon,
                    "status__color": color,
                    "type": rng.choice(task_types),
                    "author": rng.choice(_authors),
                    "version": f"v{rng.randint(1, 20):03d}",
                    "thumb": "",  # placeholder for thumbnail column
                    "thumb__icon": "panorama",  # placeholder for thumbnail column  # noqa: E501
                }
            )
        return entries

    def _folder_row(folder_id: str, folder_name: str) -> dict[str, Any]:
        return {
            "id": folder_id,
            "name": folder_name,
            "has_children": True,
            "name__icon": _FOLDER_ICON,
            "name__color": _FOLDER_COLOR,
        }

    result: dict[str | None, list[dict[str, Any]]] = {
        None: [
            _folder_row("assets", "Assets"),
            _folder_row("shots", "Shots"),
        ],
        "assets": [
            _folder_row(fid, name) for fid, name in zip(asset_ids, asset_names)
        ],
        "shots": [
            _folder_row(sid, name) for sid, name in zip(shot_ids, shot_names)
        ],
    }

    for folder_id, count in zip(asset_ids, asset_counts):
        result[folder_id] = _make_entries(
            folder_id, count, _asset_task_names, _asset_types
        )
    for shot_id, count in zip(shot_ids, shot_counts):
        result[shot_id] = _make_entries(
            shot_id, count, _shot_task_names, _shot_types
        )

    return result


HIERARCHICAL_TEST_DATA = _make_hierarchical_test_data(500)


def make_hierarchical_test_fetch(
    data: dict[str | None, list[dict[str, Any]]],
) -> Callable[[int, int, str | None, bool, str | None], list[dict[str, Any]]]:
    """Create a fetch_page callback from hierarchical test data.

    Args:
        data: Mapping of parent_id -> list[row_dict].
              ``None`` key holds the root-level rows.

    Returns:
        A callable suitable for PaginatedTableModel in tree mode.
    """

    def _fetch(
        page: int,
        page_size: int,
        sort_key: str | None,
        descending: bool,
        parent_id: str | None = None,
    ) -> list[dict[str, Any]]:
        print(
            f"[test]  Fetching page {page} (page_size={page_size}, "
            f"sort_key={sort_key!r}, descending={descending}, "
            f"parent_id={parent_id!r})"
        )
        rows = list(data.get(parent_id, []))
        if sort_key:
            rows = sorted(
                rows,
                key=lambda r: (
                    r.get(sort_key) is None,
                    str(r.get(sort_key, "")),
                ),
                reverse=descending,
            )
        start = page * page_size
        end = start + page_size
        return rows[start:end]

    return _fetch


def make_hierarchical_test_fetch_batch(
    data: dict[str | None, list[dict[str, Any]]],
) -> Callable[
    [list[BatchFetchRequest]], dict[str | None, list[dict[str, Any]]]
]:
    """Create a *fetch_page_batch* callback from hierarchical test data.

    Wraps :func:`make_hierarchical_test_fetch` so that several child
    fetch requests are resolved in one call, mimicking a batched server
    API.  Use together with ``fetch_page_batch=`` on
    :class:`PaginatedTableModel` to exercise the batch code path.

    Args:
        data: Mapping of parent_id -> list[row_dict].
              ``None`` key holds the root-level rows.

    Returns:
        A callable suitable for ``PaginatedTableModel(fetch_page_batch=…)``
        in tree mode.
    """
    single_fetch = make_hierarchical_test_fetch(data)

    def _batch_fetch(
        requests: list[BatchFetchRequest],
    ) -> dict[str | None, list[dict[str, Any]]]:
        print(
            f"[test]  Batch fetch for {len(requests)} parent(s): "
            f"{[r.parent_id for r in requests]!r}"
        )
        return {
            req.parent_id: single_fetch(
                req.page,
                req.page_size,
                req.sort_key,
                req.descending,
                req.parent_id,
            )
            for req in requests
        }

    return _batch_fetch


def main():
    _app = QApplication(sys.argv)
    fetch = make_test_fetch(TABLE_TEST_DATA)
    model = PaginatedTableModel(fetch_page=fetch, page_size=25)
    print(f"[test]  Rows: {model.rowCount()}, Columns: {model.columnCount()}")
    print(f"[test]  Columns: {[c.label for c in model.columns]}")
    has_more = model.canFetchMore()
    print(f"[test]  Has more: {has_more}")


if __name__ == "__main__":
    main()
