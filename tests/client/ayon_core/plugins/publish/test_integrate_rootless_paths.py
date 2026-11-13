"""Tests for rootless path resolution in the integrator.

The integrator should resolve representation file paths using the root
that was used to fill the publish template, not by guessing the root from
the absolute destination path.
"""
from __future__ import annotations

from typing import Any

import pyblish.api
import pytest

from ayon_core.pipeline.anatomy import AnatomyStringTemplate
from ayon_core.pipeline.anatomy.roots import AnatomyRoot
from ayon_core.pipeline.anatomy.templates import AnatomyTemplates
from ayon_core.plugins.publish.integrate import IntegrateAsset

# Overlapping roots: 'render' lives inside 'work'. Guessing from the
#   absolute path matches 'work' first, which is the wrong root.
ROOTS_RAW = {
    "work": "P:/projects",
    "render": "P:/projects/renders",
}


class _FakeAnatomy:
    """Minimal anatomy with roots, matching roots in definition order."""

    def __init__(self) -> None:
        self.roots = {
            name: AnatomyRoot(
                None, {"windows": path, "linux": path, "darwin": path}, name
            )
            for name, path in ROOTS_RAW.items()
        }
        self.templates_obj = type("_T", (), {"frame_padding": 4})()

    def find_root_template_from_path(self, path: str) -> tuple[bool, str]:
        for root in self.roots.values():
            success, result = root.find_root_template_from_path(path)
            if success:
                return success, result
        return False, path


class _FakeAnatomyTemplates:
    def __init__(self, anatomy: _FakeAnatomy) -> None:
        self.anatomy = anatomy

    get_rootless_path_from_result = (
        AnatomyTemplates.get_rootless_path_from_result
    )


def _make_plugin(monkeypatch: pytest.MonkeyPatch) -> IntegrateAsset:
    plugin = IntegrateAsset()
    monkeypatch.setattr(
        plugin, "_get_attributes_for_type", lambda *_args: {}
    )
    return plugin


def _make_instance(anatomy: _FakeAnatomy) -> pyblish.api.Instance:
    context = pyblish.api.Context()
    context.data["anatomy"] = anatomy
    instance = context.create_instance("test")
    instance.data["anatomyData"] = {
        "project": {"name": "demo"},
        "product": {"name": "renderMain"},
        "user": {"name": "tester"},
    }
    instance.data["publishDir"] = "P:/projects/renders/demo"
    return instance


def _make_publish_template(anatomy: _FakeAnatomy, path: str) -> dict:
    templates = _FakeAnatomyTemplates(anatomy)
    return {"path": AnatomyStringTemplate(templates, path)}


def _prepare(
    monkeypatch: pytest.MonkeyPatch,
    template: str,
    repre: dict[str, Any],
) -> Any:
    anatomy = _FakeAnatomy()
    instance = _make_instance(anatomy)
    plugin = _make_plugin(monkeypatch)
    return plugin.prepare_representation(
        repre,
        _make_publish_template(anatomy, template),
        existing_repres_by_name={},
        version_entity={"id": "a" * 32, "version": 1},
        instance_stagingdir="C:/staging",
        instance=instance,
    )


def test_single_file_uses_template_root(monkeypatch):
    prepared = _prepare(
        monkeypatch,
        "{root[render]}/{project[name]}/{product[name]}.{ext}",
        {"name": "exr", "ext": "exr", "files": "render.exr"},
    )
    (_src, dst), = prepared.transfers
    assert prepared.rootless_by_dst[str(dst)] == (
        "{root[render]}/demo/renderMain.exr"
    )


def test_sequence_uses_template_root(monkeypatch):
    prepared = _prepare(
        monkeypatch,
        "{root[render]}/{project[name]}/{product[name]}.{frame}.{ext}",
        {
            "name": "exr",
            "ext": "exr",
            "files": ["render.1001.exr", "render.1002.exr"],
        },
    )
    rootless = [
        prepared.rootless_by_dst[str(dst)] for _, dst in prepared.transfers
    ]
    assert rootless == [
        "{root[render]}/demo/renderMain.1001.exr",
        "{root[render]}/demo/renderMain.1002.exr",
    ]


def test_original_basename_uses_template_root(monkeypatch):
    prepared = _prepare(
        monkeypatch,
        "{root[render]}/{project[name]}/{originalBasename}.{ext}",
        {"name": "exr", "ext": "exr", "files": "beauty.exr"},
    )
    (_src, dst), = prepared.transfers
    assert prepared.rootless_by_dst[str(dst)] == (
        "{root[render]}/demo/beauty.exr"
    )


def test_unknown_root_falls_back_to_guessing(monkeypatch):
    """Without a root in the template the old guessing is used."""
    prepared = _prepare(
        monkeypatch,
        "P:/projects/renders/{project[name]}/{product[name]}.{ext}",
        {"name": "exr", "ext": "exr", "files": "render.exr"},
    )
    (_src, dst), = prepared.transfers
    assert prepared.rootless_by_dst[str(dst)] == (
        "{root[work]}/renders/demo/renderMain.exr"
    )
