"""Tests for stacking USD contributions into a layer."""
from __future__ import annotations

import logging

import pytest

pytest.importorskip("pxr")

from pxr import Sdf  # noqa: E402

from ayon_core.pipeline.usdlib import (  # noqa: E402
    BaseContribution,
    ReferenceContribution,
    SublayerContribution,
    VariantContribution,
    get_sdf_format_args,
)
from ayon_core.plugins.publish.extract_usd_layer_contributions import (  # noqa: E402, E501
    USDContributionStackingMixin,
)


class _Stacker(USDContributionStackingMixin):
    log = logging.getLogger("test_usd_contribution_stacking")


@pytest.fixture
def stacker() -> _Stacker:
    return _Stacker()


@pytest.fixture
def layer() -> Sdf.Layer:
    return Sdf.Layer.CreateAnonymous()


def _sublayers(layer: Sdf.Layer) -> list[tuple[str, str]]:
    """Return (path, layer id) for each sublayer, strongest first."""
    result = []
    for sublayer_path in layer.subLayerPaths:
        path, _args = Sdf.Layer.SplitIdentifier(sublayer_path)
        layer_id = get_sdf_format_args(sublayer_path)["layer_id"]
        result.append((path, layer_id))
    return result


def _references(layer: Sdf.Layer, prim_path: str) -> list[str]:
    prim_spec = layer.GetPrimAtPath(prim_path)
    return [ref.assetPath for ref in prim_spec.referenceList.prependedItems]


def _variant(variant_name: str, source: str, layer_id: str, policy: str):
    return VariantContribution(
        source=source,
        layer_id=layer_id,
        order=0,
        target_prim_path="/hero",
        variant_set_name="model",
        variant_name=variant_name,
        variant_default_policy=policy,
    )


class TestSublayerContributions:
    def test_higher_order_is_stronger(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                SublayerContribution("/look.usd", "look", 200),
                SublayerContribution("/model.usd", "model", 100),
                SublayerContribution("/rig.usd", "rig", 300),
            ],
            layer,
        )
        assert _sublayers(layer) == [
            ("/rig.usd", "rig"),
            ("/look.usd", "look"),
            ("/model.usd", "model"),
        ]

    def test_same_layer_id_is_replaced(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                SublayerContribution("/model_v001.usd", "model", 100),
                SublayerContribution("/look_v001.usd", "look", 200),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [SublayerContribution("/model_v002.usd", "model", 100)],
            layer,
        )
        assert _sublayers(layer) == [
            ("/look_v001.usd", "look"),
            ("/model_v002.usd", "model"),
        ]

    def test_different_layer_ids_with_same_order_are_kept(
        self, stacker, layer
    ):
        """Multiple products can contribute to the same department layer."""
        stacker.add_contributions_to_layer(
            [
                SublayerContribution("/modelMain.usd", "modelMain", 0),
                SublayerContribution("/modelProxy.usd", "modelProxy", 0),
            ],
            layer,
        )
        assert sorted(_sublayers(layer)) == [
            ("/modelMain.usd", "modelMain"),
            ("/modelProxy.usd", "modelProxy"),
        ]

    def test_string_source_is_authored_as_is(self, stacker, layer):
        uri = "ayon://test/sq01?product=usdSequence&version=latest"
        stacker.add_contributions_to_layer(
            [
                SublayerContribution(uri, "sequence", 0),
                SublayerContribution("./relative.usd", "relative", 1),
            ],
            layer,
        )
        assert _sublayers(layer) == [
            ("./relative.usd", "relative"),
            (uri, "sequence"),
        ]


class TestReferenceContributions:
    def test_reference_is_added_to_target_prim(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [ReferenceContribution("/ref.usd", "ref", 0, "/root/child")],
            layer,
        )
        assert _references(layer, "/root/child") == ["/ref.usd"]

    def test_same_layer_id_is_replaced(self, stacker, layer):
        for source in ["/ref_v001.usd", "/ref_v002.usd"]:
            stacker.add_contributions_to_layer(
                [
                    ReferenceContribution(source, "ref", 0, "/root"),
                    ReferenceContribution("/other.usd", "other", 0, "/root"),
                ],
                layer,
            )
        assert _references(layer, "/root") == ["/ref_v002.usd", "/other.usd"]

    def test_higher_order_is_stronger(self, stacker, layer):
        """Earlier prepended references are the stronger opinion."""
        stacker.add_contributions_to_layer(
            [
                ReferenceContribution("/look.usd", "look", 200, "/root"),
                ReferenceContribution("/model.usd", "model", 100, "/root"),
                ReferenceContribution("/rig.usd", "rig", 300, "/root"),
            ],
            layer,
        )
        assert _references(layer, "/root") == [
            "/rig.usd", "/look.usd", "/model.usd"
        ]

        # A later contribution is inserted at its order among existing ones
        stacker.add_contributions_to_layer(
            [ReferenceContribution("/groom.usd", "groom", 150, "/root")],
            layer,
        )
        assert _references(layer, "/root") == [
            "/rig.usd", "/look.usd", "/groom.usd", "/model.usd"
        ]

    def test_missing_target_prim_path(self, stacker, layer):
        with pytest.raises(ValueError):
            stacker.add_contributions_to_layer(
                [ReferenceContribution("/ref.usd", "ref", 0, "")],
                layer,
            )


class TestVariantContributions:
    def test_reference_is_added_inside_variant(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main.usd", "modelMain", "never"),
                _variant("damaged", "/damaged.usd", "modelDamaged", "never"),
            ],
            layer,
        )
        assert _references(layer, "/hero{model=main}") == ["/main.usd"]
        assert _references(layer, "/hero{model=damaged}") == ["/damaged.usd"]
        # No references outside of the variants
        assert _references(layer, "/hero") == []

    def test_republish_replaces_reference_in_variant(self, stacker, layer):
        for source in ["/main_v001.usd", "/main_v002.usd"]:
            stacker.add_contributions_to_layer(
                [_variant("main", source, "modelMain", "never")], layer
            )
        assert _references(layer, "/hero{model=main}") == ["/main_v002.usd"]

    @pytest.mark.parametrize("policy, expected", [
        ("never", {}),
        ("if_not_set", {"model": "main"}),
        ("always", {"model": "main"}),
    ])
    def test_default_policy_without_existing_selection(
        self, stacker, layer, policy, expected
    ):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main.usd", "modelMain", policy)], layer
        )
        selections = dict(layer.GetPrimAtPath("/hero").variantSelections)
        assert selections == expected

    @pytest.mark.parametrize("policy, expected", [
        ("never", "main"),
        ("if_not_set", "main"),
        ("always", "damaged"),
    ])
    def test_default_policy_with_existing_selection(
        self, stacker, layer, policy, expected
    ):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main.usd", "modelMain", "always")], layer
        )
        stacker.add_contributions_to_layer(
            [_variant("damaged", "/damaged.usd", "modelDamaged", policy)],
            layer,
        )
        selections = dict(layer.GetPrimAtPath("/hero").variantSelections)
        assert selections == {"model": expected}


class TestStaleContributions:
    """A contribution key must only ever exist once in a layer."""

    def test_changed_variant_name(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main_v001.usd", "modelMain", "never"),
                _variant("main", "/proxy_v001.usd", "modelProxy", "never"),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert _references(layer, "/hero{model=main}") == ["/proxy_v001.usd"]
        assert _references(layer, "/hero{model=default}") == [
            "/main_v002.usd"
        ]

    def test_changed_target_prim_path(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                ReferenceContribution("/ref_v001.usd", "ref", 0, "/root/a"),
                ReferenceContribution("/other.usd", "other", 0, "/root/a"),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [ReferenceContribution("/ref_v002.usd", "ref", 0, "/root/b")],
            layer,
        )
        assert _references(layer, "/root/a") == ["/other.usd"]
        assert _references(layer, "/root/b") == ["/ref_v002.usd"]

    def test_sublayer_to_variant(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                SublayerContribution("/main_v001.usd", "modelMain", 0),
                SublayerContribution("/proxy_v001.usd", "modelProxy", 0),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert _sublayers(layer) == [("/proxy_v001.usd", "modelProxy")]
        assert _references(layer, "/hero{model=main}") == ["/main_v002.usd"]

    def test_variant_to_sublayer(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main_v001.usd", "modelMain", "never"),
                _variant("main", "/proxy_v001.usd", "modelProxy", "never"),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [SublayerContribution("/main_v002.usd", "modelMain", 0)],
            layer,
        )
        assert _sublayers(layer) == [("/main_v002.usd", "modelMain")]
        assert _references(layer, "/hero{model=main}") == ["/proxy_v001.usd"]


class TestEmptyVariantCleanup:
    """Variants emptied by removing a stale contribution are removed."""

    @staticmethod
    def _variants(layer: Sdf.Layer, variant_set_name="model") -> list[str]:
        prim_spec = layer.GetPrimAtPath("/hero")
        if variant_set_name not in prim_spec.variantSets:
            return []
        return sorted(prim_spec.variantSets[variant_set_name].variants.keys())

    @staticmethod
    def _selections(layer: Sdf.Layer) -> dict[str, str]:
        return dict(layer.GetPrimAtPath("/hero").variantSelections)

    @pytest.mark.parametrize("policy", ["never", "if_not_set", "always"])
    def test_renamed_variant_is_removed(self, stacker, layer, policy):
        """Selection of the removed variant moves along with the rename."""
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v001.usd", "modelMain", "always")],
            layer,
        )
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", policy)],
            layer,
        )
        assert self._variants(layer) == ["default"]
        assert self._selections(layer) == {"model": "default"}
        assert _references(layer, "/hero{model=default}") == [
            "/main_v002.usd"
        ]

    def test_selection_of_other_variant_is_preserved(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main_v001.usd", "modelMain", "never"),
                _variant("damaged", "/dmg_v001.usd", "modelDamaged", "always"),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert self._variants(layer) == ["damaged", "default"]
        assert self._selections(layer) == {"model": "damaged"}

    def test_variant_with_other_contribution_is_kept(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main_v001.usd", "modelMain", "always"),
                _variant("main", "/proxy_v001.usd", "modelProxy", "never"),
            ],
            layer,
        )
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert self._variants(layer) == ["default", "main"]
        assert self._selections(layer) == {"model": "main"}

    def test_variant_with_other_opinions_is_kept(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v001.usd", "modelMain", "always")],
            layer,
        )
        # Manually authored opinion inside the variant
        Sdf.CreatePrimInLayer(layer, "/hero{model=main}child")
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert self._variants(layer) == ["default", "main"]
        assert _references(layer, "/hero{model=main}") == []
        assert self._selections(layer) == {"model": "main"}

    def test_untouched_empty_variant_is_kept(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v001.usd", "modelMain", "always")],
            layer,
        )
        # An intentionally empty variant not created by a contribution
        Sdf.CreatePrimInLayer(layer, "/hero{model=none}")
        stacker.add_contributions_to_layer(
            [_variant("default", "/main_v002.usd", "modelMain", "never")],
            layer,
        )
        assert self._variants(layer) == ["default", "none"]

    def test_variant_refilled_in_same_publish_is_kept(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v001.usd", "modelMain", "always")],
            layer,
        )
        stacker.add_contributions_to_layer(
            [
                _variant("default", "/main_v002.usd", "modelMain", "never"),
                _variant("main", "/proxy_v001.usd", "modelProxy", "never"),
            ],
            layer,
        )
        assert self._variants(layer) == ["default", "main"]
        assert _references(layer, "/hero{model=main}") == ["/proxy_v001.usd"]
        assert self._selections(layer) == {"model": "main"}

    def test_variant_to_sublayer_removes_variant_set(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [_variant("main", "/main_v001.usd", "modelMain", "always")],
            layer,
        )
        stacker.add_contributions_to_layer(
            [SublayerContribution("/main_v002.usd", "modelMain", 0)],
            layer,
        )
        prim_spec = layer.GetPrimAtPath("/hero")
        assert _sublayers(layer) == [("/main_v002.usd", "modelMain")]
        assert dict(prim_spec.variantSets) == {}
        assert not prim_spec.HasInfo("variantSetNames")
        assert self._selections(layer) == {}
        assert "variant" not in layer.ExportToString()

    def test_moved_to_other_variant_set(self, stacker, layer):
        stacker.add_contributions_to_layer(
            [
                _variant("main", "/main_v001.usd", "modelMain", "always"),
                _variant("damaged", "/dmg_v001.usd", "modelDamaged", "never"),
            ],
            layer,
        )
        contribution = _variant(
            "main", "/main_v002.usd", "modelMain", "if_not_set"
        )
        contribution.variant_set_name = "geo"
        stacker.add_contributions_to_layer([contribution], layer)

        assert self._variants(layer, "model") == ["damaged"]
        assert self._variants(layer, "geo") == ["main"]
        # No selection remains for the removed variant of the other set
        assert self._selections(layer) == {"geo": "main"}


def test_unsupported_contribution_type(stacker, layer):
    with pytest.raises(TypeError):
        stacker.add_contributions_to_layer(
            [BaseContribution("/file.usd", "base", 0)], layer
        )
