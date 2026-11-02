"""Tests for 'AnatomyTemplates.get_rootless_path_from_result'."""
from __future__ import annotations

from ayon_core.lib.path_templates import StringTemplate
from ayon_core.pipeline.anatomy import templates


def test_rootless_path_uses_forward_slashes_on_windows(monkeypatch):
    monkeypatch.setattr(templates, "_IS_WINDOWS", True)
    result = StringTemplate("{root[work]}/{folder}/file.ext").format({
        "root": {"work": "P:/projects"},
        "folder": r"demo\shots",
    })

    rootless = templates.AnatomyTemplates.get_rootless_path_from_result(
        result
    )

    assert rootless == "{root[work]}/demo/shots/file.ext"
