"""Products model for loader tools."""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Iterable

import ayon_api

from ayon_core.lib import NestedCacheItem
from ayon_core.lib.icon_definitions import AwesomeFontIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.browser.abstract import RepreItem

PRODUCTS_MODEL_SENDER = "products.model"


@dataclass
class ProductItem:
    product_id: str
    product_name: str
    folder_label: str


@dataclass
class ProjectCache:
    product_id_by_version_id: dict[str, str | None] = field(
        default_factory=dict
    )
    product_items_by_id: dict[str, ProductItem | None] = field(
        default_factory=dict
    )
    folder_label_by_id: dict[str, str | None] = field(
        default_factory=dict
    )


class ProductsModel:
    """Model for products, version and representation.

    All the entities are product based. This model prepares data for UI
    and caches it for faster access.

    Note:
        Data are not used for actions model because that would require to
            break OpenPype compatibility of 'LoaderPlugin's.
    """

    lifetime = 60  # In seconds (minute by default)

    def __init__(self):
        self._project_cache: dict[str, ProjectCache] = defaultdict(
            ProjectCache
        )

        # Cache helpers
        self._repre_items_cache = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime
        )

    def reset(self) -> None:
        """Reset model with all cached data."""

        self._project_cache.clear()

        self._repre_items_cache.reset()

    def get_versions_repre_count(
        self, project_name: str, version_ids: set[str]
    ) -> dict[str, int]:
        """Get representation count for passed version ids.

        Args:
            project_name (str): Project name.
            version_ids (set[str]): Version ids.

        Returns:
            dict[str, int]: Number of representations by version id.

        """
        output = {}
        if not project_name or not version_ids:
            return output

        invalid_version_ids = set()
        project_cache = self._repre_items_cache[project_name]
        for version_id in version_ids:
            version_cache = project_cache[version_id]
            if version_cache.is_valid:
                output[version_id] = len(version_cache.get_data())
            else:
                invalid_version_ids.add(version_id)

        if invalid_version_ids:
            self._refresh_representation_items(
                project_name, invalid_version_ids
            )

        for version_id in invalid_version_ids:
            version_cache = project_cache[version_id]
            output[version_id] = len(version_cache.get_data())

        return output

    def get_product_ids_by_repre_ids(
        self, project_name: str, repre_ids: list[str] | set[str]
    ) -> set[str]:
        """Get product ids based on passed representation ids.

        Args:
            project_name (str): Where to look for representations.
            repre_ids (Iterable[str]): Representation ids.

        Returns:
            set[str]: Product ids for passed representation ids.
        """

        # TODO look out how to use single server call
        if not repre_ids:
            return set()
        repres = ayon_api.get_representations(
            project_name, repre_ids, fields=["versionId"]
        )
        version_ids = {repre["versionId"] for repre in repres}
        if not version_ids:
            return set()
        versions = ayon_api.get_versions(
            project_name, version_ids=version_ids, fields=["productId"]
        )
        return {v["productId"] for v in versions}

    def get_repre_items(
        self, project_name: str, version_ids: set[str]
    ) -> list[RepreItem]:
        """Get representation items for passed version ids.

        Args:
            project_name (str): Project name.
            version_ids (set[str]): Version ids.

        Returns:
            list[RepreItem]: Representation items.

        """
        output = []
        if not project_name or not version_ids:
            return output

        invalid_version_ids = set()
        project_cache = self._repre_items_cache[project_name]
        for version_id in version_ids:
            version_cache = project_cache[version_id]
            if version_cache.is_valid:
                output.extend(version_cache.get_data().values())
            else:
                invalid_version_ids.add(version_id)

        if invalid_version_ids:
            self._refresh_representation_items(
                project_name, invalid_version_ids
            )

        for version_id in invalid_version_ids:
            version_cache = project_cache[version_id]
            output.extend(version_cache.get_data().values())

        return output

    def _refresh_representation_items(
        self, project_name: str, version_ids: set[str]
    ) -> None:
        if not project_name or not version_ids:
            return

        try:
            repre_items_by_version_id = self._get_repre_items_by_version_ids(
                project_name, version_ids
            )

            repre_items_cache = self._repre_items_cache[project_name]
            for version_id, repre_items in repre_items_by_version_id.items():
                version_cache = repre_items_cache[version_id]
                version_cache.update_data(repre_items)

        except Exception:
            pass

    def _fill_versions_mapping(
        self, project_name: str, version_ids: set[str]
    ) -> None:
        project_cache = self._project_cache[project_name]
        missing_version_ids = set()
        for version_id in version_ids:
            if version_id in project_cache.product_id_by_version_id:
                continue
            missing_version_ids.add(version_id)
            project_cache.product_id_by_version_id[version_id] = None

        if not missing_version_ids:
            return

        for version in ayon_api.get_versions(
            project_name,
            version_ids=missing_version_ids,
            fields={"id", "productId"},
        ):
            version_id = version["id"]
            product_id = version["productId"]
            project_cache.product_id_by_version_id[version_id] = (
                product_id
            )

    def _fill_product_items(
        self, project_name: str, version_ids: set[str]
    ) -> None:
        self._fill_versions_mapping(project_name, version_ids)

        project_cache = self._project_cache[project_name]
        product_ids = {
            project_cache.product_id_by_version_id[version_id]
            for version_id in version_ids
        }
        product_ids.discard(None)

        missing_product_ids = set()
        for product_id in product_ids:
            if product_id not in project_cache.product_items_by_id:
                missing_product_ids.add(product_id)
                project_cache.product_items_by_id[product_id] = None

        if not missing_product_ids:
            return

        products_by_id = {
            product["id"]: product
            for product in ayon_api.get_products(
                project_name,
                product_ids=product_ids,
                fields={"id", "name", "folderId"}
            )
        }
        folder_ids = {p["folderId"] for p in products_by_id.values()}
        missing_folder_ids = set()
        for folder_id in folder_ids:
            if folder_id not in project_cache.folder_label_by_id:
                missing_folder_ids.add(folder_id)
                project_cache.folder_label_by_id[folder_id] = None

        if missing_folder_ids:
            for folder in ayon_api.get_folders(
                project_name,
                folder_ids=missing_folder_ids,
                fields={"id", "label", "name"}
            ):
                folder_id = folder["id"]
                label = folder["label"] or folder["name"]
                project_cache.folder_label_by_id[folder_id] = label

        for product_id, product in products_by_id.items():
            folder_id = product["folderId"]
            folder_label = project_cache.folder_label_by_id[folder_id]
            project_cache.product_items_by_id[product_id] = ProductItem(
                product_id=product_id,
                product_name=product["name"],
                folder_label=folder_label or "N/A",
            )

    def _get_repre_items_by_version_ids(
        self,
        project_name: str,
        version_ids: set[str],
    ) -> dict[str, dict[str, RepreItem]]:

        repre_items_by_version_id = defaultdict(dict)
        representations = list(ayon_api.get_representations(
            project_name,
            version_ids=version_ids,
            fields={"id", "name", "versionId"}
        ))
        if not representations:
            return repre_items_by_version_id

        self._fill_product_items(project_name, version_ids)
        project_cache = self._project_cache[project_name]

        repre_icon = AwesomeFontIcon(
            "fa.file-o",
            color=get_default_entity_icon_color(),
        )
        for representation in representations:
            version_id = representation["versionId"]
            product_id = project_cache.product_id_by_version_id[version_id]
            if not product_id:
                continue
            product_item = project_cache.product_items_by_id[product_id]
            if product_item is None:
                continue
            repre_id = representation["id"]
            repre_item = RepreItem(
                repre_id,
                representation["name"],
                repre_icon,
                product_item.product_name,
                product_item.folder_label,
            )
            repre_items_by_version_id[version_id][repre_id] = repre_item
        return repre_items_by_version_id
