"""Tests for workfile template builder placeholder API."""
import pytest

from ayon_core.lib import attribute_definitions
from ayon_core.pipeline.workfile import workfile_template_builder as wtb


FOLDER_ENTITIES = [
    {"id": "f1", "path": "/assets/bob"},
    {"id": "f2", "path": "/assets/jim"},
]
PRODUCT_ENTITIES = [
    {"id": "p1", "name": "modelMain", "folderId": "f1"},
    {"id": "p2", "name": "modelProxy", "folderId": "f1"},
    {"id": "p3", "name": "modelMain", "folderId": "f2"},
]
VERSION_ENTITIES = {
    "p1": {"id": "v1", "version": 3, "productId": "p1"},
    "p2": {"id": "v2", "version": 1, "productId": "p2"},
    "p3": {"id": "v3", "version": 12, "productId": "p3"},
}
# Only one of the products has a hero version
HERO_VERSION_ENTITIES = {
    "p1": {"id": "hv1", "version": -3, "productId": "p1"},
}
REPRE_ENTITIES = [
    {"id": "r1", "name": "ma", "versionId": "v1"},
    {"id": "r2", "name": "abc", "versionId": "v1"},
    {"id": "r3", "name": "ma", "versionId": "v2"},
    {"id": "r4", "name": "usd", "versionId": "v3"},
    {"id": "r5", "name": "ma", "versionId": "hv1"},
]

LOAD_OPTIONS = {
    "builder_type": "all_folders",
    "folder_path": "",
    "product_name": "",
    "product_base_type": "model",
    "representation": "ma",
    "loader": "MyLoader",
    "order": 0,
}


class _BasePlugin(wtb.PlaceholderPlugin):
    """Minimal plugin implementation to test the shared API."""

    def create_placeholder(self, placeholder_data):
        pass

    def update_placeholder(self, placeholder_item, placeholder_data):
        pass

    def collect_placeholders(self):
        return []

    def populate_placeholder(self, placeholder):
        pass


class _LoadPlugin(_BasePlugin, wtb.PlaceholderLoadMixin):
    label = "Fake load"
    identifier = "fake.load"

    def get_placeholder_options(self, options=None):
        return self.get_load_plugin_options(options)


class _CreatePlugin(_BasePlugin, wtb.PlaceholderCreateMixin):
    label = "Fake create"
    identifier = "fake.create"

    def get_placeholder_options(self, options=None):
        return self.get_create_plugin_options(options)


class _Creator:
    label = "Fake creator"

    def get_product_name(
        self, project_name, folder_entity, task_entity, variant, host_name
    ):
        return "model{}".format(variant.capitalize())


class _Builder(wtb.AbstractTemplateBuilder):
    def get_placeholder_plugin_classes(self):
        return [_LoadPlugin, _CreatePlugin]

    def import_template(self, path):
        return True

    def get_loaders_by_name(self):
        return {"MyLoader": object()}

    def get_creators_by_name(self):
        return {"FakeCreator": _Creator()}

    @property
    def current_folder_entity(self):
        return {"id": "f1", "path": "/assets/bob"}

    @property
    def current_task_entity(self):
        return {"id": "t1", "name": "modeling"}


class _Placeholder:
    """Stand-in for 'PlaceholderItem', only 'data' is used by the query."""

    def __init__(self, data):
        self.data = data


@pytest.fixture
def load_plugin(monkeypatch):
    """Load placeholder plugin with mocked server queries."""

    def get_folders(project_name, folder_path_regex=None, fields=None):
        return list(FOLDER_ENTITIES)

    def get_products(project_name, folder_ids=None, fields=None, **kwargs):
        return [
            product_entity
            for product_entity in PRODUCT_ENTITIES
            if product_entity["folderId"] in folder_ids
        ]

    def get_last_versions(project_name, product_ids, fields=None):
        return {
            product_id: VERSION_ENTITIES[product_id]
            for product_id in product_ids
        }

    def get_representations(
        project_name, representation_names=None, version_ids=None
    ):
        return [
            repre_entity
            for repre_entity in REPRE_ENTITIES
            if repre_entity["versionId"] in version_ids
            and (
                representation_names is None
                or repre_entity["name"] in representation_names
            )
        ]

    def get_hero_versions(project_name, product_ids=None, fields=None):
        return [
            HERO_VERSION_ENTITIES[product_id]
            for product_id in product_ids
            if product_id in HERO_VERSION_ENTITIES
        ]

    monkeypatch.setattr(wtb.ayon_api, "get_hero_versions", get_hero_versions)
    monkeypatch.setattr(wtb, "get_folders", get_folders)
    monkeypatch.setattr(wtb, "get_products", get_products)
    monkeypatch.setattr(wtb, "get_last_versions", get_last_versions)
    monkeypatch.setattr(wtb, "get_representations", get_representations)
    monkeypatch.setattr(
        wtb.ayon_api, "get_server_version_tuple", lambda: (1, 14, 0)
    )
    return _LoadPlugin(_Builder(None))


class TestPlaceholderCapabilities:
    def test_defaults_are_not_reported_as_implemented(self):
        assert not _BasePlugin._is_method_implemented("delete_placeholder")
        assert not _BasePlugin.is_delete_placeholder_supported(_BasePlugin)
        assert not _BasePlugin.is_select_placeholder_supported(_BasePlugin)

    def test_mixin_defaults_are_not_reported_as_implemented(self):
        """Mixins define no-op defaults that must not count as support."""
        assert not _LoadPlugin._is_method_implemented("delete_placeholder")
        assert not _CreatePlugin._is_method_implemented("delete_placeholder")

    def test_overrides_are_detected(self):
        class Implemented(_LoadPlugin):
            def delete_placeholder(self, placeholder_item):
                pass

            def select_placeholder(self, placeholder_item):
                pass

        assert Implemented._is_method_implemented("delete_placeholder")
        assert Implemented._is_method_implemented("select_placeholder")


class TestLoadPlaceholderQuery:
    def test_representations_are_filtered_by_options(self, load_plugin):
        repre_entities = load_plugin._get_representations(
            _Placeholder(dict(LOAD_OPTIONS))
        )
        assert sorted(
            repre_entity["id"] for repre_entity in repre_entities
        ) == ["r1", "r3"]

    def test_openpype_placeholder_is_skipped(self, load_plugin):
        placeholder = _Placeholder(dict(LOAD_OPTIONS, asset="bob"))
        assert load_plugin._get_representations(placeholder) == []

    def test_product_name_regex_is_applied(self, load_plugin):
        result = load_plugin._query_load_options(
            dict(LOAD_OPTIONS, product_name="modelP.*", representation="")
        )
        assert [
            product_entity["name"]
            for product_entity in result.product_entities_by_id.values()
        ] == ["modelProxy"]

    def test_context_folder_uses_current_folder(self, load_plugin):
        result = load_plugin._query_load_options(
            dict(LOAD_OPTIONS, builder_type="context_folder")
        )
        assert list(result.folder_entities_by_id) == ["f1"]

    def test_unknown_builder_type_matches_nothing(self, load_plugin):
        result = load_plugin._query_load_options(
            dict(LOAD_OPTIONS, builder_type="unknown")
        )
        assert result.representation_entities == []


class TestLoadPlaceholderVersion:
    def test_hero_option_loads_hero_versions(self, load_plugin):
        repre_entities = load_plugin._get_representations(
            _Placeholder(dict(LOAD_OPTIONS, version="hero"))
        )
        assert [repre["id"] for repre in repre_entities] == ["r5"]

    def test_hero_version_is_labeled_in_preview(self, load_plugin):
        preview = load_plugin.get_placeholder_preview(
            dict(LOAD_OPTIONS, version="hero")
        )
        assert [(item.label, item.detail) for item in preview.items] == [
            ("/assets/bob/modelMain", "HERO - ma"),
        ]

    def test_version_entities_override_is_used(self, load_plugin):
        """Host override of '_get_version_entities' drives the query."""
        calls = []

        def _get_version_entities(project_name, product_ids, placeholder):
            calls.append(placeholder.data["version"])
            # Override may not query fields used by the preview
            return [{"id": "v3"}]

        load_plugin._get_version_entities = _get_version_entities
        options = dict(LOAD_OPTIONS, version="latest", representation="")

        result = load_plugin._query_load_options(options)
        assert [
            repre["id"] for repre in result.representation_entities
        ] == ["r4"]
        assert calls == ["latest"]
        # Preview skips entries it can't describe instead of failing
        assert load_plugin.get_placeholder_preview(options).items == []


class TestLoadPlaceholderPreview:
    def test_preview_lists_matching_products(self, load_plugin):
        preview = load_plugin.get_placeholder_preview(dict(LOAD_OPTIONS))

        assert not preview.is_error
        assert preview.title == "Would load 2 representations"
        assert [(item.label, item.detail) for item in preview.items] == [
            ("/assets/bob/modelMain", "v003 - ma"),
            ("/assets/bob/modelProxy", "v001 - ma"),
        ]

    def test_preview_without_product_base_type(self, load_plugin):
        preview = load_plugin.get_placeholder_preview(
            dict(LOAD_OPTIONS, product_base_type=None)
        )
        assert preview.items == []
        assert not preview.is_error
        assert "Product base type" in preview.hint

    def test_preview_reports_unknown_loader(self, load_plugin):
        preview = load_plugin.get_placeholder_preview(
            dict(LOAD_OPTIONS, loader="Missing")
        )
        assert preview.is_error
        assert "Missing" in preview.hint

    def test_preview_of_openpype_placeholder(self, load_plugin):
        preview = load_plugin.get_placeholder_preview(
            dict(LOAD_OPTIONS, asset="bob")
        )
        assert preview.is_error

    def test_legacy_family_key_is_used(self, load_plugin):
        options = dict(LOAD_OPTIONS)
        options.pop("product_base_type")
        options["family"] = "model"
        assert load_plugin.get_placeholder_preview(options).items


class TestLoadPlaceholderCompletions:
    def test_completions_ignore_filled_filters(self, load_plugin):
        completions = load_plugin.get_placeholder_completions(
            dict(
                LOAD_OPTIONS,
                representation="zzz",
                product_name="nothing-matches",
            )
        )
        assert completions["representation"] == ["abc", "ma", "usd"]
        assert completions["product_name"] == ["modelMain", "modelProxy"]

    def test_no_completions_without_product_base_type(self, load_plugin):
        completions = load_plugin.get_placeholder_completions(
            dict(LOAD_OPTIONS, product_base_type=None)
        )
        assert completions == {}


class TestCreatePlaceholderPreview:
    def test_preview_shows_product_name(self):
        plugin = _CreatePlugin(_Builder(None))
        preview = plugin.get_placeholder_preview({
            "creator": "FakeCreator",
            "create_variant": "main",
            "active": True,
        })
        assert not preview.is_error
        assert preview.items[0].label == "/assets/bob/modelMain"
        assert "Fake creator" in preview.items[0].detail

    def test_preview_without_creator(self):
        plugin = _CreatePlugin(_Builder(None))
        preview = plugin.get_placeholder_preview({"creator": None})
        assert preview.items == []
        assert not preview.is_error

    def test_preview_with_unknown_creator(self):
        plugin = _CreatePlugin(_Builder(None))
        preview = plugin.get_placeholder_preview({"creator": "Missing"})
        assert preview.is_error
        assert "Missing" in preview.hint

    def test_create_plugin_has_no_completions(self):
        plugin = _CreatePlugin(_Builder(None))
        assert plugin.get_placeholder_completions({}) == {}


class TestPlaceholderPreviewSerialization:
    def test_round_trip(self):
        preview = wtb.PlaceholderPreview(
            title="Would load 1 representation",
            items=[wtb.PlaceholderPreviewItem("/assets/bob", "v001 - ma")],
            hint="hint",
            is_error=True,
            hidden_items_count=3,
        )
        assert wtb.PlaceholderPreview.from_data(preview.to_data()) == preview


class TestTextDefCompletions:
    def test_completions_survive_serialization(self):
        attr_def = attribute_definitions.TextDef(
            "representation", completions=["abc", "ma"]
        )
        restored = attribute_definitions.deserialize_attr_def(
            attr_def.serialize()
        )
        assert restored.completions == ["abc", "ma"]

    def test_completions_do_not_change_def_identity(self):
        """Completions are UI hints, they change while editing options."""
        assert attribute_definitions.TextDef(
            "key", completions=["a"]
        ).compare_to_def(
            attribute_definitions.TextDef("key", completions=["b"])
        )
