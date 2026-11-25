"""Loading options, preview and completion helpers for template builder.

Kept separate from ``workfile_template_builder`` so the load-option query and
preview logic does not grow the core builder module further. The mixin is
mixed into ``PlaceholderLoadMixin``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

import ayon_api
from ayon_api import (
    get_folders,
    get_last_versions,
    get_products,
    get_representations,
)


@dataclass
class _LoadQueryResult:
    """Entities matching options of a load placeholder.

    Attributes:
        folder_entities_by_id (dict[str, dict]): Folder entities matching
            builder type and folder filter.
        product_entities_by_id (dict[str, dict]): Product entities matching
            product base type and product filter.
        version_entities_by_id (dict[str, dict]): Last version entities of
            matching products.
        representation_entities (list[dict]): Representation entities of
            matching versions.

    """
    folder_entities_by_id: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    product_entities_by_id: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    version_entities_by_id: dict[str, dict[str, Any]] = field(
        default_factory=dict
    )
    representation_entities: list[dict[str, Any]] = field(
        default_factory=list
    )


class PlaceholderLoadOptionsMixin:
    def _get_version_entities(self, project_name, product_ids, placeholder):
        """Query version entities of products based on load options.

        This function is directly connected to options defined in
        'get_load_plugin_options'. The 'version' option decides which
        version is queried for each product:

        - 'latest' (default): The last standard version of each product.
            Products without any standard version are skipped.
        - 'hero': The hero version of each product. Products without a
            hero version are skipped.

        Args:
            project_name (str): Name of the project.
            product_ids (Iterable[str]): Product ids to query versions for.
            placeholder (PlaceholderItem): Item which should be populated.

        Returns:
            List[Dict[str, Any]]: Version documents matching the version
                option of the placeholder.
        """
        product_ids = set(product_ids)
        version_entities = []
        version_mode = placeholder.data.get("version")
        if version_mode == "hero":
            version_entities.extend(
                ayon_api.get_hero_versions(
                    project_name,
                    product_ids=product_ids,
                    fields={"id", "version", "productId"},
            ))

        else:
            version_entities.extend(
                version_entity
                for version_entity in get_last_versions(
                    project_name,
                    product_ids,
                    fields={"id", "version", "productId"},
                ).values()
                # Version may be none if a product has no versions
                if version_entity is not None
            )

        return version_entities

    def _get_load_folder_entities(self, placeholder_data):
        """Folder entities matching 'builder_type' of load options.

        Args:
            placeholder_data (dict[str, Any]): Placeholder options.

        Returns:
            list[dict[str, Any]]: Folder entities to look for products in.

        """
        from ayon_core.pipeline.workfile.workfile_template_builder import (
            AbstractTemplateBuilder,
        )

        project_name = self.builder.project_name
        builder_type = placeholder_data["builder_type"]
        folder_path_regex = placeholder_data["folder_path"]

        if builder_type == "all_folders":
            return list(get_folders(
                project_name,
                folder_path_regex=folder_path_regex,
                fields={"id", "path"}
            ))

        if builder_type == "context_folder":
            folder_entity = self.builder.current_folder_entity
            if not folder_entity:
                return []
            return [folder_entity]

        if builder_type == "linked_folders":
            if not isinstance(self.builder, AbstractTemplateBuilder):
                return []
            # link type from placeholder data or default to "template"
            link_type = placeholder_data.get("link_type", "template")
            return list(self.builder.get_linked_folder_entities(
                link_type=link_type,
                folder_path_regex=folder_path_regex
            ))

        return []

    def _validate_load_option_regexes(self, placeholder_data):
        """Validate regex filters before querying the server.

        Args:
            placeholder_data (dict[str, Any]): Placeholder options.

        Raises:
            ValueError: A filter is not a valid regular expression.

        """
        errors = []
        for key, label in (
            ("folder_path", "Folder path"),
            ("product_name", "Product name"),
        ):
            value = placeholder_data.get(key)
            if not value:
                continue
            try:
                re.compile(value)
            except re.error as exc:
                errors.append(
                    "Invalid {} filter '{}': {}".format(label, value, exc)
                )
        if errors:
            raise ValueError("\n".join(errors))

    def _query_load_options(
        self,
        placeholder_data,
        filter_representation_name=True,
        filter_product_name=True,
        placeholder=None,
    ):
        """Query entities matching load options of a placeholder.

        This function is directly connected to options defined in
        'get_load_plugin_options'. It does not require an existing
        placeholder item so it can also be used to preview options that are
        not stored in the scene yet.

        Note:
            Versions are resolved by '_get_version_entities', based on the
                'version' option.

        Args:
            placeholder_data (dict[str, Any]): Placeholder options.
            filter_representation_name (bool): Filter representations by
                'representation' option.
            filter_product_name (bool): Filter products by 'product_name'
                regex option.
            placeholder (Optional[PlaceholderItem]): Placeholder item the
                options belong to. A temporary item is used when the
                options are not stored in the scene yet.

        Returns:
            _LoadQueryResult: Matching entities.

        """
        from ayon_core.pipeline.workfile.workfile_template_builder import (
            PlaceholderItem,
        )

        self._validate_load_option_regexes(placeholder_data)

        project_name = self.builder.project_name

        product_base_type = placeholder_data.get("product_base_type")
        if product_base_type is None:
            product_base_type = placeholder_data.get("product_type")
            if product_base_type is None:
                product_base_type = placeholder_data["family"]

        folder_entities_by_id = {
            folder_entity["id"]: folder_entity
            for folder_entity in self._get_load_folder_entities(
                placeholder_data
            )
        }
        if not folder_entities_by_id:
            return _LoadQueryResult()

        filter_key = "product_base_types"
        if ayon_api.get_server_version_tuple() < (1, 14, 0):
            filter_key = "product_types"
        filter_kwargs = {
            filter_key: {product_base_type},
        }

        product_name_regex = None
        if filter_product_name:
            product_name_regex_value = placeholder_data["product_name"]
            if product_name_regex_value:
                product_name_regex = re.compile(product_name_regex_value)

        product_entities_by_id = {
            product_entity["id"]: product_entity
            for product_entity in get_products(
                project_name,
                folder_ids=set(folder_entities_by_id),
                **filter_kwargs,
                fields={"id", "name", "folderId"}
            )
            if (
                product_name_regex is None
                or product_name_regex.match(product_entity["name"])
            )
        }
        if not product_entities_by_id:
            return _LoadQueryResult(
                folder_entities_by_id=folder_entities_by_id
            )

        if placeholder is None:
            placeholder = PlaceholderItem("", placeholder_data, self)

        version_entities_by_id = {
            version_entity["id"]: version_entity
            for version_entity in self._get_version_entities(
                project_name,
                set(product_entities_by_id),
                placeholder
            )
        }
        if not version_entities_by_id:
            return _LoadQueryResult(
                folder_entities_by_id=folder_entities_by_id,
                product_entities_by_id=product_entities_by_id,
            )

        representation_names = None
        if filter_representation_name:
            representation_name = placeholder_data["representation"]
            if representation_name:
                representation_names = [representation_name]

        representation_entities = list(get_representations(
            project_name,
            representation_names=representation_names,
            version_ids=set(version_entities_by_id)
        ))
        return _LoadQueryResult(
            folder_entities_by_id=folder_entities_by_id,
            product_entities_by_id=product_entities_by_id,
            version_entities_by_id=version_entities_by_id,
            representation_entities=representation_entities,
        )

    def _get_representations(self, placeholder):
        """Prepared query of representations based on load options.

        This function is directly connected to options defined in
        'get_load_plugin_options'.

        Note:
            The default implementation returns representations of the
                versions resolved by '_get_version_entities', based on the
                'version' option. Host integrations may override this
                method and return representations of multiple versions of
                a product. The final version selection is then done by
                '_reduce_last_version_repre_entities'.

        Args:
            placeholder (PlaceholderItem): Item which should be populated.

        Returns:
            List[Dict[str, Any]]: Representation documents matching filters
                from placeholder data.
        """

        # An OpenPype placeholder loaded in AYON
        if "asset" in placeholder.data:
            return []

        return self._query_load_options(
            placeholder.data, placeholder=placeholder
        ).representation_entities

    def get_load_placeholder_preview(self, placeholder_data):
        """Products that would be loaded with current load options.

        Use it in 'get_placeholder_preview'. Default implementation of
        'PlaceholderPlugin.get_placeholder_preview' calls it automatically.

        Args:
            placeholder_data (dict[str, Any]): Placeholder options.

        Returns:
            PlaceholderPreview: Products matching the options.

        """
        from ayon_core.pipeline.workfile.workfile_template_builder import (
            PlaceholderPreview,
            PlaceholderPreviewItem,
        )

        if "asset" in placeholder_data:
            return PlaceholderPreview(
                title="Legacy placeholder",
                hint=(
                    "Placeholder was created in OpenPype and can't be"
                    " populated in AYON. Create a new placeholder to"
                    " replace it."
                ),
                is_error=True,
            )

        product_base_type = (
            placeholder_data.get("product_base_type")
            or placeholder_data.get("product_type")
            or placeholder_data.get("family")
        )
        if not product_base_type:
            return PlaceholderPreview(
                title="Nothing to load",
                hint=(
                    "Fill in 'Product base type' to see which products"
                    " would be loaded."
                ),
            )

        if (
            placeholder_data.get("builder_type") == "all_folders"
            and not placeholder_data.get("folder_path")
        ):
            return PlaceholderPreview(
                title="Filter folders for preview",
                hint=(
                    "Enter a folder path filter to preview what would be"
                    " loaded from all folders. Unfiltered all-folders"
                    " previews can query the whole project."
                ),
            )

        try:
            result = self._query_load_options(placeholder_data)
        except Exception as exc:
            return PlaceholderPreview(
                title="Preview failed",
                hint=str(exc),
                is_error=True,
            )

        items = []
        for repre_entity in result.representation_entities:
            version_entity = result.version_entities_by_id.get(
                repre_entity["versionId"]
            )
            if version_entity is None:
                continue
            product_entity = result.product_entities_by_id.get(
                version_entity.get("productId")
            )
            if product_entity is None:
                continue
            folder_entity = result.folder_entities_by_id.get(
                product_entity["folderId"]
            )
            folder_path = "<unknown>"
            if folder_entity is not None:
                folder_path = folder_entity.get("path") or folder_path

            version = version_entity.get("version")
            if version is None:
                version_label = "v???"
            elif version < 0:
                # Hero versions have negative version numbers
                version_label = "HERO"
            else:
                version_label = "v{:0>3}".format(version)

            items.append(PlaceholderPreviewItem(
                label="{}/{}".format(folder_path, product_entity["name"]),
                detail="{} - {}".format(version_label, repre_entity["name"]),
            ))

        items.sort(key=lambda item: (item.label, item.detail or ""))

        hint = None
        loader_name = placeholder_data.get("loader")
        if not loader_name:
            hint = "No loader is selected, nothing will be loaded."
        elif loader_name not in self.builder.get_loaders_by_name():
            hint = "Loader '{}' is not available in this host.".format(
                loader_name
            )

        if not items:
            return PlaceholderPreview(
                title="Nothing to load",
                hint=hint or (
                    "No representations match the filled in options in the"
                    " current context."
                ),
                is_error=bool(hint),
            )

        max_items = 30
        hidden_items_count = max(0, len(items) - max_items)
        return PlaceholderPreview(
            title="Would load {} representation{}".format(
                len(items), "" if len(items) == 1 else "s"
            ),
            items=items[:max_items],
            hint=hint,
            is_error=bool(hint),
            hidden_items_count=hidden_items_count,
        )

    def get_load_placeholder_completions(self, placeholder_data):
        """Representation and product names available for load options.

        Use it in 'get_placeholder_completions'. Default implementation of
        'PlaceholderPlugin.get_placeholder_completions' calls it
        automatically.

        Args:
            placeholder_data (dict[str, Any]): Placeholder options.

        Returns:
            dict[str, list[str]]: Suggestions by option key.

        """
        output = {}
        product_base_type = (
            placeholder_data.get("product_base_type")
            or placeholder_data.get("product_type")
            or placeholder_data.get("family")
        )
        if not product_base_type:
            return output

        if (
            placeholder_data.get("builder_type") == "all_folders"
            and not placeholder_data.get("folder_path")
        ):
            # Avoid querying the whole project for suggestions.
            return output

        try:
            result = self._query_load_options(
                placeholder_data,
                filter_representation_name=False,
                filter_product_name=False,
            )
        except Exception:
            self.log.debug(
                "Failed to collect placeholder completions.", exc_info=True
            )
            return output

        output["representation"] = sorted({
            repre_entity["name"]
            for repre_entity in result.representation_entities
        })
        output["product_name"] = sorted({
            product_entity["name"]
            for product_entity in result.product_entities_by_id.values()
        })
        return output
