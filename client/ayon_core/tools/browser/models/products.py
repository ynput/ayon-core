"""Products model for loader tools."""
from __future__ import annotations

import threading
from collections import defaultdict
from dataclasses import dataclass, field

import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import NestedCacheItem
from ayon_core.lib.icon_definitions import AwesomeFontIcon
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.browser.abstract import ProductGroupsInfo, RepreItem

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
    # Permissions of a user rarely change
    permissions_lifetime = 300  # In seconds

    def __init__(self):
        self._project_cache: dict[str, ProjectCache] = defaultdict(
            ProjectCache
        )

        # Cache helpers
        self._repre_items_cache = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime
        )
        self._can_change_group_cache = NestedCacheItem(
            levels=1, lifetime=self.permissions_lifetime
        )
        self._refresh_lock = threading.Lock()

    def reset(self) -> None:
        """Reset model with all cached data."""

        self._project_cache.clear()

        self._repre_items_cache.reset()
        self._can_change_group_cache.reset()

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
            repre_ids (set[str] | list[str]): Representation ids.

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

    def get_product_groups_info(
        self, project_name: str, product_ids: set[str]
    ) -> ProductGroupsInfo:
        """Get product group names related to passed product ids.

        Args:
            project_name (str): Project name.
            product_ids (set[str]): Product ids.

        Returns:
            ProductGroupsInfo: Group names of the products and group names
                available in their folders.

        """
        output = ProductGroupsInfo(selected=set(), available=set())
        if not project_name or not product_ids:
            return output

        fields = {"id", "folderId", "attrib.productGroup"}
        folder_ids = set()
        for product in ayon_api.get_products(
            project_name, product_ids=product_ids, fields=fields
        ):
            folder_ids.add(product["folderId"])
            group_name = product.get("attrib", {}).get("productGroup")
            if group_name:
                output.selected.add(group_name)

        if not folder_ids:
            return output

        for product in ayon_api.get_products(
            project_name, folder_ids=folder_ids, fields=fields
        ):
            group_name = product.get("attrib", {}).get("productGroup")
            if group_name:
                output.available.add(group_name)
        return output

    def can_change_products_group(self, project_name: str) -> bool:
        """Whether current user may write the product group attribute.

        Admins, managers and services always can. Other users can unless their
        access groups restrict attribute writing in the project and
        'productGroup' is not among the writable attributes.

        The result is cached per project.

        Args:
            project_name (str): Project name.

        Returns:
            bool: Product group attribute can be changed by the user.

        """
        cache = self._can_change_group_cache[project_name]
        if not cache.is_valid:
            cache.update_data(self._query_can_change_products_group(
                project_name
            ))
        return cache.get_data()

    def _query_can_change_products_group(self, project_name: str) -> bool:
        # REST user has the role flags under 'data'
        user_data = ayon_api.get_user().get("data") or {}
        if any(
            user_data.get(key)
            for key in ("isAdmin", "isManager", "isService")
        ):
            return True

        response = ayon_api.get(f"/users/me/permissions/{project_name}")
        permissions = response.data
        if response.status_code != 200 or not isinstance(permissions, dict):
            # Permissions are unknown, the server validates the change
            return True

        attrib_write = permissions.get("attrib_write") or {}
        if not attrib_write.get("enabled"):
            return True
        return "productGroup" in (attrib_write.get("attributes") or [])

    def change_products_group(
        self, project_name: str, product_ids: set[str], group_name: str
    ) -> None:
        """Change group name for passed product ids.

        Group name is stored in 'attrib' of product entity.

        Args:
            project_name (str): Project name.
            product_ids (set[str]): Product ids to change group name for.
            group_name (str): Group name to set, empty string to ungroup.

        """
        if not project_name or not product_ids:
            return

        session = OperationsSession()
        for product_id in product_ids:
            session.update_entity(
                project_name,
                "product",
                product_id,
                {"attrib": {"productGroup": group_name or None}},
            )
        session.commit()

    def _refresh_representation_items(
        self, project_name: str, version_ids: set[str]
    ) -> None:
        if not project_name or not version_ids:
            return

        repre_items_cache = self._repre_items_cache[project_name]
        with self._refresh_lock:
            try:
                repre_items_by_version_id = (
                    self._get_repre_items_by_version_ids(
                        project_name, version_ids
                    )
                )
                for version_id, repre_items in (
                    repre_items_by_version_id.items()
                ):
                    repre_items_cache[version_id].update_data(repre_items)

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
