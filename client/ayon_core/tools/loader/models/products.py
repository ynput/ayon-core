"""Products model for loader tools."""

from __future__ import annotations

import collections
import contextlib
import logging
import os
from typing import TYPE_CHECKING, Iterable, Optional

import arrow
import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import NestedCacheItem
from ayon_core.pipeline.load.reviewables import (
    is_reviewable_product_id,
    list_version_reviewables,
    make_reviewable_product_id,
    make_reviewable_repre_id,
    parse_reviewable_product_id,
)
from ayon_core.style import get_default_entity_icon_color
from ayon_core.tools.common_models import ProductTypeIconMapping
from ayon_core.tools.loader.abstract import (
    ProductTypeItem,
    ProductBaseTypeItem,
    ProductItem,
    VersionItem,
    RepreItem,
)

if TYPE_CHECKING:
    from ayon_api.typing import (
        ProductBaseTypeDict,
        ProductDict,
        VersionDict,
    )

PRODUCTS_MODEL_SENDER = "products.model"

_log = logging.getLogger(__name__)

_REPRE_CACHE_SEP = "\x1f"
# Default group folder for REST reviewable synthetic products (studio may
# override via project settings hook in `_reviewable_bundle_group_name`).
REVIEWABLE_PRODUCT_GROUP_DEFAULT = "Reviewables"

# Explicit GraphQL fields for loader product rows (defaults may omit `attrib`).
LOADER_PRODUCT_LIST_FIELDS: frozenset[str] = frozenset(
    {
        "id",
        "folderId",
        "name",
        "productType",
        "productBaseType",
        "attrib",
    }
)


def _repre_cache_key(product_id: str, version_id: str) -> str:
    """NestedCacheItem leaf key for representation buckets."""
    return f"{product_id}{_REPRE_CACHE_SEP}{version_id}"


def _reviewable_bundle_group_name(controller) -> str:
    """Display/productGroup folder name for synthetic reviewable products."""
    _ = controller
    return REVIEWABLE_PRODUCT_GROUP_DEFAULT


def _loader_version_query_fields() -> set[str]:
    """Loader version row fields including ``attrib`` and ``status``."""
    fields = set(ayon_api.get_default_fields_for_type("version"))
    fields.update({"status", "attrib"})
    return fields


def version_item_from_entity(version):
    version_attribs = version.get("attrib") or {}
    tags = version.get("tags") or []
    frame_start = version_attribs.get("frameStart")
    frame_end = version_attribs.get("frameEnd")
    handle_start = version_attribs.get("handleStart")
    handle_end = version_attribs.get("handleEnd")
    step = version_attribs.get("step")
    comment = version_attribs.get("comment")
    source = version_attribs.get("source")

    frame_range = None
    duration = None
    handles = None
    if frame_start is not None and frame_end is not None:
        # Remove superfluous zeros from numbers (3.0 -> 3) to improve
        # readability for most frame ranges
        frame_start = int(frame_start)
        frame_end = int(frame_end)
        frame_range = "{}-{}".format(frame_start, frame_end)
        duration = frame_end - frame_start + 1

    if handle_start is not None and handle_end is not None:
        handles = "{}-{}".format(int(handle_start), int(handle_end))

    # NOTE There is also 'updatedAt', should be used that instead?
    # TODO skip conversion - converting to '%Y%m%dT%H%M%SZ' is because
    #   'PrettyTimeDelegate' expects it
    created_at = arrow.get(version["createdAt"]).to("local")
    published_time = created_at.strftime("%Y%m%dT%H%M%SZ")
    author = version["author"]
    version_num = version["version"]
    is_hero = version_num < 0

    return VersionItem(
        version_id=version["id"],
        version=version_num,
        is_hero=is_hero,
        product_id=version["productId"],
        task_id=version["taskId"],
        thumbnail_id=version["thumbnailId"],
        published_time=published_time,
        author=author,
        tags=tags,
        status=version["status"],
        frame_range=frame_range,
        duration=duration,
        handles=handles,
        step=step,
        comment=comment,
        source=source,
    )


def product_item_from_entity(
    product_entity: ProductDict,
    version_entities,
    folder_label,
    icons_mapping,
    product_in_scene,
):
    product_attribs = product_entity.get("attrib") or {}
    group = product_attribs.get("productGroup")
    product_type = product_entity["productType"]
    product_base_type = product_entity.get("productBaseType")

    product_icon = icons_mapping.get_icon(product_base_type, product_type)
    version_items = {
        version_entity["id"]: version_item_from_entity(version_entity)
        for version_entity in version_entities
    }

    return ProductItem(
        product_id=product_entity["id"],
        product_type=product_type,
        product_base_type=product_base_type,
        product_name=product_entity["name"],
        product_icon=product_icon,
        product_in_scene=product_in_scene,
        group_name=group,
        folder_id=product_entity["folderId"],
        folder_label=folder_label,
        version_items=version_items,
    )


def product_base_type_item_from_data(
    product_base_type_data: ProductBaseTypeDict,
) -> ProductBaseTypeItem:
    """Create product base type item from data.

    Args:
        product_base_type_data (ProductBaseTypeDict): Product base type data.

    Returns:
        ProductBaseTypeDict: Product base type item.

    """
    icon = {
        "type": "awesome-font",
        "name": "fa.folder",
        "color": "#0091B2",
    }
    return ProductBaseTypeItem(name=product_base_type_data["name"], icon=icon)


class ProductsModel:
    """Model for products, version and representation.

    All the entities are product based. This model prepares data for UI
    and caches it for faster access.

    Note:
        Data are not used for actions model because that would require to
            break OpenPype compatibility of 'LoaderPlugin's.
    """

    lifetime = 60  # In seconds (minute by default)

    def __init__(self, controller):
        self._controller = controller

        # Mapping helpers
        # NOTE - mapping must be cleaned up with cache cleanup
        self._product_item_by_id = collections.defaultdict(dict)
        self._version_item_by_id = collections.defaultdict(dict)
        self._product_folder_ids_mapping = collections.defaultdict(dict)

        # Cache helpers
        self._product_type_items_cache = NestedCacheItem(
            levels=1, default_factory=list, lifetime=self.lifetime
        )
        self._product_base_type_items_cache = NestedCacheItem(
            levels=1, default_factory=list, lifetime=self.lifetime
        )
        self._product_items_cache = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime
        )
        self._repre_items_cache = NestedCacheItem(
            levels=2, default_factory=dict, lifetime=self.lifetime
        )

    def reset(self):
        """Reset model with all cached data."""

        self._product_item_by_id.clear()
        self._version_item_by_id.clear()
        self._product_folder_ids_mapping.clear()

        self._product_type_items_cache.reset()
        self._product_items_cache.reset()
        self._repre_items_cache.reset()

    def get_product_type_items(
        self, project_name: Optional[str]
    ) -> list[ProductTypeItem]:
        """Product type items for project.

        Args:
            project_name (Union[str, None]): Project name.

        Returns:
            list[ProductTypeItem]: Product type items.

        """
        if not project_name:
            return []

        cache = self._product_type_items_cache[project_name]
        if not cache.is_valid:
            icons_mapping = self._get_product_type_icons(project_name)

            # Get registered product types from API
            registered_product_types = ayon_api.get_project_product_types(
                project_name
            )
            registered_type_names = {
                product_type["name"]
                for product_type in registered_product_types
            }

            # Get product types from anatomy settings (incl. anatomy
            # product_types.definitions)
            anatomy_product_types = {}
            try:
                from ayon_core.pipeline import Anatomy

                anatomy = Anatomy(project_name)
                product_types_data = anatomy.get("product_types")
                if product_types_data:
                    definitions = product_types_data.get("definitions", [])
                    for pt_def in definitions:
                        pt_name = pt_def.get("name")
                        if pt_name:
                            anatomy_product_types[pt_name] = pt_def
            except Exception:
                # If anatomy access fails, continue with API types only
                pass

            # Also get product types from actual products in the project
            # This ensures all product types that exist are included
            actual_product_types = set()
            try:
                products = ayon_api.get_products(
                    project_name, fields=["productType"]
                )
                actual_product_types = {
                    product["productType"]
                    for product in products
                    if product.get("productType")
                }
            except Exception:
                # If query fails, continue without actual product types
                pass

            # Merge registered, anatomy, and on-disk product type names
            all_product_type_names = (
                registered_type_names
                | set(anatomy_product_types.keys())
                | actual_product_types
            )

            # Create product type items, preserving registered ones first
            product_type_items = []
            seen_names = set()

            # Registered types first (order + API fields preserved)
            for product_type in registered_product_types:
                name = product_type["name"]
                if name in all_product_type_names:
                    product_type_items.append(
                        ProductTypeItem(
                            name,
                            icons_mapping.get_icon(product_type=name),
                        )
                    )
                    seen_names.add(name)

            # Add anatomy product types that aren't in registered types
            for pt_name in sorted(anatomy_product_types.keys()):
                if pt_name not in seen_names:
                    product_type_items.append(
                        ProductTypeItem(
                            pt_name,
                            icons_mapping.get_icon(product_type=pt_name),
                        )
                    )
                    seen_names.add(pt_name)

            # Add on-disk types missing from registered/anatomy
            for pt_name in sorted(actual_product_types):
                if pt_name not in seen_names:
                    product_type_items.append(
                        ProductTypeItem(
                            pt_name,
                            icons_mapping.get_icon(product_type=pt_name),
                        )
                    )

            cache.update_data(product_type_items)
        return cache.get_data()

    def get_product_base_type_items(
        self, project_name: Optional[str]
    ) -> list[ProductBaseTypeItem]:
        """Product base type items for the project.

        Notes:
            This will be used for filtering product types in UI when
                product base types are fully implemented.

        Args:
            project_name (optional, str): Project name.

        Returns:
            list[ProductBaseTypeDict]: Product base type items.

        """
        if not project_name:
            return []

        cache = self._product_base_type_items_cache[project_name]
        if not cache.is_valid:
            icons_mapping = self._get_product_type_icons(project_name)
            product_base_types = []
            # TODO add temp implementation here when it is actually
            #   implemented and available on server.
            if hasattr(ayon_api, "get_project_product_base_types"):
                product_base_types = ayon_api.get_project_product_base_types(
                    project_name
                )
            cache.update_data(
                [
                    ProductBaseTypeItem(
                        product_base_type["name"],
                        icons_mapping.get_icon(product_base_type["name"]),
                    )
                    for product_base_type in product_base_types
                ]
            )
        return cache.get_data()

    def get_product_items(self, project_name, folder_ids, sender):
        """Product items with versions for project and folder ids.

        Product items also contain version items. They're directly connected
        to product items in the UI and the separation is not needed.

        Args:
            project_name (Union[str, None]): Project name.
            folder_ids (Iterable[str]): Folder ids.
            sender (Union[str, None]): Who triggered the method.

        Returns:
            list[ProductItem]: Product items.
        """

        if not project_name or not folder_ids:
            return []

        project_cache = self._product_items_cache[project_name]
        output = []
        folder_ids_to_update = set()
        for folder_id in folder_ids:
            cache = project_cache[folder_id]
            if cache.is_valid:
                output.extend(cache.get_data().values())
            else:
                folder_ids_to_update.add(folder_id)

        self._refresh_product_items(project_name, folder_ids_to_update, sender)

        for folder_id in folder_ids_to_update:
            cache = project_cache[folder_id]
            output.extend(cache.get_data().values())
        return output

    def get_product_item(self, project_name, product_id):
        """Get product item based on passed product id.

        This method is using cached items, but if cache is not valid it also
        can query the item.

        Args:
            project_name (Union[str, None]): Where to look for product.
            product_id (Union[str, None]): Product id to receive.

        Returns:
            Union[ProductItem, None]: Product item or 'None' if not found.
        """

        if not any((project_name, product_id)):
            return None

        product_items_by_id = self._product_item_by_id[project_name]
        product_item = product_items_by_id.get(product_id)
        if product_item is not None:
            return product_item
        for product_item in self._query_product_items_by_ids(
            project_name, product_ids=[product_id]
        ).values():
            return product_item

    def get_product_ids_by_repre_ids(self, project_name, repre_ids):
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
        self,
        project_name,
        version_ids,
        sender,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ):
        """Get representation items for passed version ids.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            sender (Union[str, None]): Who triggered the method.
            product_version_pairs: Optional explicit ``(product_id, version_id)``
                rows; inferred from the in-memory version map when omitted.

        Returns:
            list[RepreItem]: Representation items.
        """

        output: list[RepreItem] = []
        if not any((project_name, version_ids)):
            return output

        pairs = product_version_pairs or self._infer_product_version_pairs(
            project_name, version_ids
        )
        if not pairs:
            return output

        invalid_pairs: list[tuple[str, str]] = []
        project_cache = self._repre_items_cache[project_name]
        for product_id, version_id in pairs:
            ck = _repre_cache_key(product_id, version_id)
            slot = project_cache[ck]
            if slot.is_valid:
                output.extend(slot.get_data().values())
            else:
                invalid_pairs.append((product_id, version_id))

        if invalid_pairs:
            self.refresh_representation_items(
                project_name,
                {vid for _pid, vid in invalid_pairs},
                sender,
                product_version_pairs=pairs,
            )

        for product_id, version_id in invalid_pairs:
            ck = _repre_cache_key(product_id, version_id)
            output.extend(project_cache[ck].get_data().values())

        return output

    def get_repre_items_grouped(
        self,
        project_name,
        version_ids,
        sender,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ):
        """Warm representation cache; group reps per ``(product_id, version_id)``.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            sender (Union[str, None]): Who triggered the method.
            product_version_pairs: Optional explicit selection rows.

        Returns:
            dict[tuple[str, str], list[RepreItem]]: Keys are
            ``(product_id, version_id)``.
        """

        version_ids = set(version_ids)
        if not project_name or not version_ids:
            return {}

        pairs = product_version_pairs or self._infer_product_version_pairs(
            project_name, version_ids
        )
        if not pairs:
            return {}

        self.get_repre_items(
            project_name,
            version_ids,
            sender,
            product_version_pairs=pairs,
        )

        project_cache = self._repre_items_cache[project_name]
        output: dict[tuple[str, str], list[RepreItem]] = {}
        for product_id, version_id in pairs:
            ck = _repre_cache_key(product_id, version_id)
            output[(product_id, version_id)] = list(
                project_cache[ck].get_data().values()
            )
        return output

    def get_versions_repre_count(
        self,
        project_name,
        version_ids,
        sender,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ):
        """Get representation count for passed version ids.

        Args:
            project_name (str): Project name.
            version_ids (Iterable[str]): Version ids.
            sender (Union[str, None]): Who triggered the method.
            product_version_pairs: Optional explicit rows.

        Returns:
            dict[str, int]: Number of representations by version id (sum across
            product rows that share a version).
        """

        output: dict[str, int] = {}
        if not any((project_name, version_ids)):
            return output

        pairs = product_version_pairs or self._infer_product_version_pairs(
            project_name, version_ids
        )
        if not pairs:
            return output

        invalid_pairs: list[tuple[str, str]] = []
        project_cache = self._repre_items_cache[project_name]
        for product_id, version_id in pairs:
            ck = _repre_cache_key(product_id, version_id)
            slot = project_cache[ck]
            if slot.is_valid:
                output[version_id] = output.get(version_id, 0) + len(
                    slot.get_data()
                )
            else:
                invalid_pairs.append((product_id, version_id))

        if invalid_pairs:
            self.refresh_representation_items(
                project_name,
                {vid for _pid, vid in invalid_pairs},
                sender,
                product_version_pairs=pairs,
            )

        for product_id, version_id in invalid_pairs:
            ck = _repre_cache_key(product_id, version_id)
            output[version_id] = output.get(version_id, 0) + len(
                project_cache[ck].get_data()
            )

        return output

    def change_products_group(self, project_name, product_ids, group_name):
        """Change group name for passed product ids.

        Group name is stored in 'attrib' of product entity and is used in UI
        to group items.

        Method triggers "products.group.changed" event with data:
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "product_ids": product_ids,
                "group_name": group_name
            }

        Args:
            project_name (str): Project name.
            product_ids (Iterable[str]): Product ids to change group name for.
            group_name (str): Group name to set.
        """

        product_ids = [
            pid for pid in product_ids if not is_reviewable_product_id(pid)
        ]
        if not product_ids:
            return

        product_items = self._get_product_items_by_id(
            project_name, product_ids
        )
        if not product_items:
            return

        session = OperationsSession()
        folder_ids = set()
        for product_item in product_items.values():
            session.update_entity(
                project_name,
                "product",
                product_item.product_id,
                {"attrib": {"productGroup": group_name}},
            )
            folder_ids.add(product_item.folder_id)
            product_item.group_name = group_name

        session.commit()
        self._controller.emit_event(
            "products.group.changed",
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "product_ids": product_ids,
                "group_name": group_name,
            },
            PRODUCTS_MODEL_SENDER,
        )

    def _get_product_type_icons(
        self, project_name: Optional[str]
    ) -> ProductTypeIconMapping:
        return self._controller.get_product_type_icons_mapping(project_name)

    def _get_product_items_by_id(self, project_name, product_ids):
        product_item_by_id = self._product_item_by_id[project_name]
        missing_product_ids = set()
        output = {}
        for product_id in product_ids:
            product_item = product_item_by_id.get(product_id)
            if product_item is not None:
                output[product_id] = product_item
            else:
                missing_product_ids.add(product_id)

        output.update(
            self._query_product_items_by_ids(
                project_name, product_ids=missing_product_ids
            )
        )
        return output

    def _infer_product_version_pairs(
        self, project_name: str, version_ids: Iterable[str]
    ) -> list[tuple[str, str]]:
        """All (product_id, version_id) rows matching *version_ids*."""
        wanted = set(version_ids)
        m = self._version_item_by_id[project_name]
        pairs: list[tuple[str, str]] = []
        for (vid, pid), _vi in m.items():
            if vid in wanted:
                pairs.append((pid, vid))
        return pairs

    def _get_version_items_for_pairs(
        self,
        project_name: str,
        product_version_pairs: list[tuple[str, str]],
    ) -> dict[tuple[str, str], VersionItem]:
        """Map (product_id, version_id) -> VersionItem."""
        m = self._version_item_by_id[project_name]
        out: dict[tuple[str, str], VersionItem] = {}
        missing_vids: set[str] = set()
        pair_set = set(product_version_pairs)
        for product_id, version_id in product_version_pairs:
            vi = m.get((version_id, product_id))
            if vi is not None:
                out[(product_id, version_id)] = vi
            else:
                missing_vids.add(version_id)
        if not missing_vids:
            return out
        fetched = self._query_version_items_by_ids(project_name, missing_vids)
        for (vid, pid), vi in fetched.items():
            if (pid, vid) in pair_set:
                out[(pid, vid)] = vi
        return out

    def _build_reviewable_synthetic_products(
        self,
        project_name: str,
        parent_item: ProductItem,
        icons_mapping: ProductTypeIconMapping,
        bundle_group: str,
    ) -> list[ProductItem]:
        """Synthetic ProductItem rows for REST reviewables (exclusive vs DB reps)."""
        out: list[ProductItem] = []
        for version_id, base_vi in parent_item.version_items.items():
            try:
                pairs = list_version_reviewables(project_name, version_id)
            except Exception as exc:
                _log.debug(
                    "list_version_reviewables failed for %s: %s",
                    version_id,
                    exc,
                    exc_info=True,
                )
                pairs = []
            if not pairs:
                continue
            for file_id, label in pairs:
                synth_pid = make_reviewable_product_id(
                    parent_item.product_id, version_id, file_id
                )
                pdata = base_vi.to_data()
                pdata["product_id"] = synth_pid
                cloned_vi = VersionItem.from_data(pdata)
                stem = os.path.basename((label or "").strip()) or "reviewable"
                pt_name = "review"
                product_icon = icons_mapping.get_icon(product_type=pt_name)
                synth = ProductItem(
                    synth_pid,
                    pt_name,
                    parent_item.product_base_type,
                    stem,
                    product_icon,
                    bundle_group,
                    parent_item.folder_id,
                    parent_item.folder_label,
                    {version_id: cloned_vi},
                    False,
                )
                out.append(synth)
        return out

    def _create_product_items(
        self,
        project_name: str,
        products: Iterable[ProductDict],
        versions: Iterable[VersionDict],
        folder_items=None,
    ):
        if folder_items is None:
            folder_items = self._controller.get_folder_items(project_name)

        loaded_product_ids = self._controller.get_loaded_product_ids()

        versions_by_product_id = collections.defaultdict(list)
        for version in versions:
            versions_by_product_id[version["productId"]].append(version)

        output: dict[str, ProductItem] = {}
        icons_mapping = self._get_product_type_icons(project_name)
        for product in products:
            product_id = product["id"]
            folder_id = product["folderId"]
            folder_item = folder_items.get(folder_id)
            if not folder_item:
                continue
            versions = versions_by_product_id[product_id]
            if not versions:
                continue
            product_item = product_item_from_entity(
                product,
                versions,
                folder_item.label,
                icons_mapping,
                product_id in loaded_product_ids,
            )
            output[product_id] = product_item
        return output

    def _query_product_items_by_ids(
        self,
        project_name,
        folder_ids=None,
        product_ids=None,
        folder_items=None,
    ):
        """Query product items.

        This method does get from, or store to, cache attributes.

        One of 'product_ids' or 'folder_ids' must be passed to the method.

        Args:
            project_name (str): Project name.
            folder_ids (Optional[Iterable[str]]): Folder ids under which are
                products.
            product_ids (Optional[Iterable[str]]): Product ids to use.
            folder_items (Optional[Dict[str, FolderItem]]): Prepared folder
                items from controller.

        Returns:
            dict[str, ProductItem]: Product items by product id.
        """

        if not folder_ids and not product_ids:
            return {}

        kwargs = {}
        if folder_ids is not None:
            kwargs["folder_ids"] = folder_ids

        if product_ids is not None:
            kwargs["product_ids"] = product_ids

        kwargs["fields"] = LOADER_PRODUCT_LIST_FIELDS
        products = list(ayon_api.get_products(project_name, **kwargs))

        # Apply product type filtering based on loader settings
        product_types_filter = self._controller.get_product_types_filter()
        if product_types_filter.product_types:
            filtered_products = []
            filter_types_set = set(product_types_filter.product_types)
            for product in products:
                product_type = product.get("productType", "")
                if product_types_filter.is_allow_list:
                    # Allow list: only include products in the list
                    if product_type in filter_types_set:
                        filtered_products.append(product)
                else:
                    # Deny list: exclude products in the list
                    if product_type not in filter_types_set:
                        filtered_products.append(product)
            products = filtered_products

        product_ids = {product["id"] for product in products}

        version_fields = _loader_version_query_fields()
        versions = ayon_api.get_versions(
            project_name, product_ids=product_ids, fields=version_fields
        )

        return self._create_product_items(
            project_name, products, versions, folder_items=folder_items
        )

    def _query_version_items_by_ids(self, project_name, version_ids):
        version_fields = _loader_version_query_fields()
        versions = list(
            ayon_api.get_versions(
                project_name,
                version_ids=version_ids,
                fields=version_fields,
            )
        )
        product_ids = {version["productId"] for version in versions}
        products = list(
            ayon_api.get_products(
                project_name,
                product_ids=product_ids,
                fields=LOADER_PRODUCT_LIST_FIELDS,
            )
        )
        product_items = self._create_product_items(
            project_name, products, versions
        )
        version_items_by_vp: dict[tuple[str, str], VersionItem] = {}
        for product_item in product_items.values():
            for vid, vi in product_item.version_items.items():
                version_items_by_vp[(vid, product_item.product_id)] = vi
        return version_items_by_vp

    def _clear_product_version_items(self, project_name, folder_ids):
        """Clear product and version items from memory.

        When products are re-queried for a folders, the old product and version
        items in '_product_item_by_id' and '_version_item_by_id' should
        be cleaned up from memory. And mapping in stored in
        '_product_folder_ids_mapping' is not relevant either.

        Args:
            project_name (str): Name of project.
            folder_ids (Iterable[str]): Folder ids which are being refreshed.
        """

        project_mapping = self._product_folder_ids_mapping[project_name]
        if not project_mapping:
            return

        product_item_by_id = self._product_item_by_id[project_name]
        version_item_by_id = self._version_item_by_id[project_name]
        for folder_id in folder_ids:
            product_ids = project_mapping.pop(folder_id, None)
            if not product_ids:
                continue

            for product_id in product_ids:
                product_item = product_item_by_id.pop(product_id, None)
                if product_item is None:
                    continue
                for version_item in product_item.version_items.values():
                    version_item_by_id.pop(
                        (version_item.version_id, product_id), None
                    )

    def _refresh_product_items(self, project_name, folder_ids, sender):
        """Refresh product items and store them in cache.

        Args:
            project_name (str): Name of project.
            folder_ids (Iterable[str]): Folder ids which are being refreshed.
            sender (Union[str, None]): Who triggered the refresh.
        """

        if not project_name or not folder_ids:
            return

        self._clear_product_version_items(project_name, folder_ids)

        project_mapping = self._product_folder_ids_mapping[project_name]
        product_item_by_id = self._product_item_by_id[project_name]
        version_item_by_id = self._version_item_by_id[project_name]

        for folder_id in folder_ids:
            project_mapping[folder_id] = set()

        with self._product_refresh_event_manager(
            project_name, folder_ids, sender
        ):
            folder_items = self._controller.get_folder_items(project_name)
            items_by_folder_id = {folder_id: {} for folder_id in folder_ids}
            product_items_by_id = self._query_product_items_by_ids(
                project_name, folder_ids=folder_ids, folder_items=folder_items
            )
            for product_id, product_item in product_items_by_id.items():
                folder_id = product_item.folder_id
                items_by_folder_id[product_item.folder_id][product_id] = (
                    product_item
                )

                project_mapping[folder_id].add(product_id)
                product_item_by_id[product_id] = product_item
                for (
                    version_id,
                    version_item,
                ) in product_item.version_items.items():
                    version_item_by_id[
                        (version_id, product_item.product_id)
                    ] = version_item

            bundle_group = _reviewable_bundle_group_name(self._controller)
            icons_mapping = self._get_product_type_icons(project_name)
            synth_added: dict[str, ProductItem] = {}
            for _pid, parent_item in list(product_items_by_id.items()):
                if is_reviewable_product_id(_pid):
                    continue
                for synth in self._build_reviewable_synthetic_products(
                    project_name,
                    parent_item,
                    icons_mapping,
                    bundle_group,
                ):
                    synth_added[synth.product_id] = synth
            for synth in synth_added.values():
                folder_id = synth.folder_id
                sid = synth.product_id
                items_by_folder_id[folder_id][sid] = synth
                project_mapping[folder_id].add(sid)
                product_item_by_id[sid] = synth
                for vid, vi in synth.version_items.items():
                    version_item_by_id[(vid, sid)] = vi

            project_cache = self._product_items_cache[project_name]
            for folder_id, product_items in items_by_folder_id.items():
                project_cache[folder_id].update_data(product_items)

    @contextlib.contextmanager
    def _product_refresh_event_manager(self, project_name, folder_ids, sender):
        self._controller.emit_event(
            "products.refresh.started",
            {
                "project_name": project_name,
                "folder_ids": folder_ids,
                "sender": sender,
            },
            PRODUCTS_MODEL_SENDER,
        )
        try:
            yield

        finally:
            self._controller.emit_event(
                "products.refresh.finished",
                {
                    "project_name": project_name,
                    "folder_ids": folder_ids,
                    "sender": sender,
                },
                PRODUCTS_MODEL_SENDER,
            )

    def refresh_representation_items(
        self,
        project_name,
        version_ids,
        sender,
        *,
        product_version_pairs: Optional[list[tuple[str, str]]] = None,
    ):
        if not any((project_name, version_ids)):
            return
        pairs = product_version_pairs or self._infer_product_version_pairs(
            project_name, version_ids
        )
        self._controller.emit_event(
            "model.representations.refresh.started",
            {
                "project_name": project_name,
                "version_ids": version_ids,
                "sender": sender,
            },
            PRODUCTS_MODEL_SENDER,
        )
        failed = False
        try:
            self._refresh_representation_items(project_name, pairs)
        except Exception:
            # TODO add more information about failed refresh
            failed = True

        self._controller.emit_event(
            "model.representations.refresh.finished",
            {
                "project_name": project_name,
                "version_ids": version_ids,
                "sender": sender,
                "failed": failed,
            },
            PRODUCTS_MODEL_SENDER,
        )

    def _refresh_representation_items(
        self,
        project_name: str,
        product_version_pairs: list[tuple[str, str]],
    ) -> None:
        if not product_version_pairs:
            return

        unique_versions = {vid for _pid, vid in product_version_pairs}
        representations = list(
            ayon_api.get_representations(
                project_name,
                version_ids=list(unique_versions),
                fields=["id", "name", "versionId"],
            )
        )

        versions_api = list(
            ayon_api.get_versions(
                project_name,
                version_ids=list(unique_versions),
                fields=["id", "productId"],
            )
        )
        version_canonical_product = {v["id"]: v["productId"] for v in versions_api}

        version_items_map = self._get_version_items_for_pairs(
            project_name, product_version_pairs
        )
        product_ids_needed = {pid for pid, _vid in product_version_pairs}
        product_items_by_id = self._get_product_items_by_id(
            project_name, product_ids_needed
        )

        repre_icon = {
            "type": "awesome-font",
            "name": "fa.file-o",
            "color": get_default_entity_icon_color(),
        }

        repre_by_bucket: dict[str, dict[str, RepreItem]] = collections.defaultdict(
            dict
        )

        for representation in representations:
            version_id = representation["versionId"]
            canonical_pid = version_canonical_product.get(version_id)
            if canonical_pid is None:
                continue
            vi = version_items_map.get((canonical_pid, version_id))
            if vi is None:
                continue
            product_item = product_items_by_id.get(canonical_pid)
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
            ck = _repre_cache_key(canonical_pid, version_id)
            repre_by_bucket[ck][repre_id] = repre_item

        for product_id, version_id in product_version_pairs:
            if not is_reviewable_product_id(product_id):
                continue
            parsed = parse_reviewable_product_id(product_id)
            if parsed is None:
                continue
            parent_pid, exp_vid, file_id = parsed
            if exp_vid != version_id:
                continue
            parent_item = product_items_by_id.get(parent_pid)
            if parent_item is None:
                continue
            label = ""
            try:
                for fid, lab in list_version_reviewables(project_name, version_id):
                    if fid == file_id:
                        label = lab
                        break
            except Exception:
                pass
            rid = make_reviewable_repre_id(version_id, file_id)
            display_name = os.path.basename((label or "").strip()) or rid
            repre_item = RepreItem(
                rid,
                display_name,
                repre_icon,
                parent_item.product_name,
                parent_item.folder_label,
                reviewable_rest_label=label or None,
            )
            ck = _repre_cache_key(product_id, version_id)
            repre_by_bucket[ck][rid] = repre_item

        project_cache = self._repre_items_cache[project_name]
        for product_id, version_id in product_version_pairs:
            ck = _repre_cache_key(product_id, version_id)
            repre_items = dict(repre_by_bucket.get(ck, {}))
            project_cache[ck].update_data(repre_items)
