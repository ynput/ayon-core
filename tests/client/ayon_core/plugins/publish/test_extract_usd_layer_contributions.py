"""Tests for USD layer contributions."""
import pytest

pytest.importorskip("pxr")

from pxr import Sdf  # noqa: E402

from ayon_core.pipeline.usdlib import variant_nested_prim_path  # noqa: E402
from ayon_core.plugins.publish.extract_usd_layer_contributions import (  # noqa: E402, E501
    ExtractUSDLayerContribution,
    VariantContribution,
)


class _Instance:
    """Minimal stand-in for a `pyblish.api.Instance`."""
    def __init__(self, product_name, version):
        self.data = {
            "projectEntity": {"name": "test"},
            "folderPath": "/assets/hero",
            "productName": product_name,
            "version": version,
        }


def _contribute(plugin, layer, product_name, version, variant_name):
    """Contribute product as variant like the plug-in does on process."""
    instance = _Instance(product_name, version)
    contribution = VariantContribution(
        instance=instance,
        layer_id="model",
        target_product="usdAsset",
        order=0,
        variant_set_name="model",
        variant_name=variant_name,
        variant_default_policy="never",
    )
    variant_prim_path = variant_nested_prim_path(
        prim_path="/hero",
        variant_selections=[("model", variant_name)]
    )
    plugin.remove_previous_reference_contributions(layer, instance)
    plugin.add_reference_contribution(
        layer,
        variant_prim_path,
        f"/publish/{product_name}_v{version:03d}.usd",
        contribution,
    )


def _references(layer, variant_name):
    prim_spec = layer.GetPrimAtPath(f"/hero{{model={variant_name}}}")
    return [ref.assetPath for ref in prim_spec.referenceList.prependedItems]


@pytest.fixture
def plugin():
    return ExtractUSDLayerContribution()


@pytest.fixture
def layer():
    return Sdf.Layer.CreateAnonymous()


def test_republish_replaces_reference_in_variant(plugin, layer):
    _contribute(plugin, layer, "modelMain", 1, "main")
    _contribute(plugin, layer, "modelMain", 2, "main")
    assert _references(layer, "main") == ["/publish/modelMain_v002.usd"]


def test_republish_to_other_variant_removes_stale_reference(plugin, layer):
    """Changing the variant name must not leave the old reference behind."""
    _contribute(plugin, layer, "modelMain", 1, "main")
    _contribute(plugin, layer, "modelMain", 2, "default")
    assert _references(layer, "main") == []
    assert _references(layer, "default") == ["/publish/modelMain_v002.usd"]


def test_other_products_are_preserved(plugin, layer):
    _contribute(plugin, layer, "modelMain", 1, "main")
    _contribute(plugin, layer, "modelDamaged", 1, "damaged")
    _contribute(plugin, layer, "modelProxy", 1, "main")
    _contribute(plugin, layer, "modelMain", 2, "default")
    assert _references(layer, "main") == ["/publish/modelProxy_v001.usd"]
    assert _references(layer, "damaged") == ["/publish/modelDamaged_v001.usd"]
    assert _references(layer, "default") == ["/publish/modelMain_v002.usd"]
