"""Shared QTreeView setup for ProductsProxyModel (list view and grid group headers)."""
from __future__ import annotations

from typing import Any, Dict, Optional, TYPE_CHECKING

from qtpy import QtWidgets

from ayon_core.pipeline.compatibility import is_product_base_type_supported
from ayon_core.tools.utils.delegates import PrettyTimeDelegate, StatusDelegate
from .products_model import (
    VERSION_STATUS_COLOR_ROLE,
    VERSION_STATUS_ICON_ROLE,
    VERSION_STATUS_NAME_ROLE,
    VERSION_STATUS_SHORT_ROLE,
)
from .products_delegates import (
    LoadedInSceneDelegate,
    SiteSyncDelegate,
    VersionDelegate,
)

if TYPE_CHECKING:
    from .products_model import ProductsModel


def configure_loader_products_tree_view(
    products_view: QtWidgets.QTreeView,
    products_model: "ProductsModel",
    controller: Any,
    *,
    hide_folders_column: bool = False,
) -> Dict[str, object]:
    """Apply delegates, column visibility, and layout matching the main product list.

    Returns delegate instances for filter updates (e.g. VersionDelegate.set_tasks_filter).
    """
    version_delegate = VersionDelegate()
    time_delegate = PrettyTimeDelegate()
    status_delegate = StatusDelegate(
        VERSION_STATUS_NAME_ROLE,
        VERSION_STATUS_SHORT_ROLE,
        VERSION_STATUS_COLOR_ROLE,
        VERSION_STATUS_ICON_ROLE,
    )
    in_scene_delegate = LoadedInSceneDelegate()
    sitesync_delegate = SiteSyncDelegate()

    for col, delegate in (
        (products_model.version_col, version_delegate),
        (products_model.published_time_col, time_delegate),
        (products_model.status_col, status_delegate),
        (products_model.in_scene_col, in_scene_delegate),
        (products_model.sitesync_avail_col, sitesync_delegate),
    ):
        products_view.setItemDelegateForColumn(col, delegate)

    products_view.setColumnHidden(
        products_model.in_scene_col,
        not controller.is_loaded_products_supported(),
    )
    products_view.setColumnHidden(
        products_model.sitesync_avail_col,
        not controller.is_sitesync_enabled(),
    )
    if not is_product_base_type_supported():
        products_view.setColumnHidden(products_model.product_base_type_col, True)

    if hide_folders_column:
        products_view.setColumnHidden(products_model.folders_label_col, True)
    else:
        products_view.setColumnHidden(
            products_model.folders_label_col,
            len(controller.get_selected_folder_ids()) <= 1,
        )

    header = products_view.header()
    header.setSectionResizeMode(
        products_model.product_name_col,
        QtWidgets.QHeaderView.ResizeToContents,
    )
    header.setSectionResizeMode(
        products_model.product_type_col,
        QtWidgets.QHeaderView.ResizeToContents,
    )

    default_widths = (
        200,
        90,
        90,
        130,
        60,
        100,
        125,
        75,
        75,
        60,
        55,
        10,
        25,
        65,
    )
    for idx, width in enumerate(default_widths):
        if idx in (
            products_model.product_name_col,
            products_model.product_type_col,
        ):
            continue
        products_view.setColumnWidth(idx, width)

    return {
        "version_delegate": version_delegate,
        "time_delegate": time_delegate,
        "status_delegate": status_delegate,
        "in_scene_delegate": in_scene_delegate,
        "sitesync_delegate": sitesync_delegate,
    }


def apply_delegate_filters_from_products_grid(
    delegates: Optional[Dict[str, object]],
    *,
    task_ids,
    status_names,
    version_tags,
    task_tags,
) -> None:
    """Mirror ProductsGridWidget filter application onto shared delegates."""
    if not delegates:
        return
    vd = delegates.get("version_delegate")
    if vd is not None:
        vd.set_tasks_filter(task_ids)
        vd.set_statuses_filter(status_names)
        vd.set_version_tags_filter(version_tags)
        vd.set_task_tags_filter(task_tags)
