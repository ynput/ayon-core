"""Tests for instance selection and result handling of ExtractThumbnail."""
from __future__ import annotations

import copy
import os
import shutil
import tempfile
import threading
from pathlib import Path
from typing import Any, Callable

import pyblish.api
import pyblish.logic
import pyblish.plugin
import pytest

from ayon_core.plugins.publish import extract_thumbnail
from ayon_core.plugins.publish.extract_thumbnail import (
    ExtractThumbnail,
    _InstanceResult,
)

PROFILE = {
    "product_base_types": [],
    "host_names": [],
    "task_types": [],
    "task_names": [],
    "product_names": [],
    "integrate_thumbnail": True,
    "target_size": {"type": "source"},
    "duration_split": 0.5,
    "oiiotool_defaults": {
        "type": "colorspace",
        "colorspace": "color_picking",
    },
    "ffmpeg_args": {"input": [], "output": []},
}


def _create_context() -> pyblish.api.Context:
    context = pyblish.api.Context()
    context.data["cleanupFullPaths"] = []
    context.data["hostName"] = "traypublisher"
    context.data["anatomy"] = None
    context.data["project_settings"] = {
        "core": {"reviewable_layers": {"review_layers": []}}
    }
    return context


def _add_instance(
    context: pyblish.api.Context,
    name: str,
    family: str = "render",
    **data: Any,
) -> pyblish.api.Instance:
    instance = context.create_instance(name)
    instance.data["family"] = family
    instance.data["families"] = []
    instance.data["productName"] = name
    instance.data["productType"] = family
    instance.data["anatomyData"] = {
        "task": {"name": "comp", "type": "Compositing"}
    }
    instance.data["representations"] = []
    instance.data.update(data)
    return instance


def _write_file(path: str) -> str:
    with open(path, "wb") as stream:
        stream.write(b"jpg")
    return path


def _fake_main_process_factory(
    root: Path,
    on_process: Callable[[ExtractThumbnail, pyblish.api.Instance], None]
    | None = None,
):
    """Create fake '_main_process' creating a single thumbnail.

    Args:
        root (Path): Directory where staging directories are created.
        on_process (Callable | None): Called with plugin and instance
            before the thumbnail is created.

    """
    def _main_process(self, instance, result, log):
        dst_staging = tempfile.mkdtemp(prefix="thumb_", dir=root)
        result.staging_dir = dst_staging
        if on_process is not None:
            on_process(self, instance)
        log.info("Creating thumbnail")
        jpeg_file = "{}_thumb.jpg".format(instance.data["productName"])
        _write_file(os.path.join(dst_staging, jpeg_file))
        result.representations.append({
            "name": "thumbnail",
            "ext": "jpg",
            "files": jpeg_file,
            "stagingDir": dst_staging,
            "thumbnail": True,
            "tags": ["thumbnail"],
            "outputName": "thumbnail",
        })

    return _main_process


def test_plugin_discovered_by_pyblish(tmp_path) -> None:
    """pyblish-base discovery loads the plugin file.

    Discovery skips plugin files with dataclasses until
    pyblish/pyblish-base#403 is released.
    """
    shutil.copy(extract_thumbnail.__file__, tmp_path)
    host_registered = "shell" in pyblish.api.registered_hosts()
    pyblish.api.register_host("shell")
    try:
        plugins = pyblish.plugin.discover(paths=[str(tmp_path)])
    finally:
        if not host_registered:
            pyblish.api.deregister_host("shell")

    assert [plugin.__name__ for plugin in plugins] == ["ExtractThumbnail"]


def test_instance_selection_matches_instance_plugin() -> None:
    """Selected instances equal what pyblish yields to an InstancePlugin."""
    context = _create_context()
    _add_instance(context, "renderMain")
    _add_instance(context, "renderInactive", publish=False)
    _add_instance(context, "modelMain", family="model")
    _add_instance(context, "imageMain", family="image")
    other = _add_instance(context, "reviewMain", family="review")
    other.data["families"] = ["render2d"]
    _add_instance(context, "workfileMain", family="workfile")

    class _InstancePlugin(pyblish.api.InstancePlugin):
        families = ExtractThumbnail.families

        def process(self, instance):
            pass

    expected = [
        instance
        for _, instance in pyblish.logic.Iterator(
            [_InstancePlugin], context
        )
    ]

    instances = ExtractThumbnail()._get_instances(context)

    assert [i.name for i in instances] == [i.name for i in expected]
    assert [i.name for i in instances] == [
        "renderMain", "imageMain", "reviewMain"
    ]


def test_context_plugin_skipped_without_active_instances() -> None:
    """AYON publisher skips the plugin when no active instance matches."""
    from ayon_core.pipeline.publish.logic import (
        collect_families_from_instances,
    )

    context = _create_context()
    _add_instance(context, "renderInactive", publish=False)
    _add_instance(context, "modelMain", family="model")

    families = collect_families_from_instances(context, only_active=True)
    assert not pyblish.logic.plugins_by_families(
        [ExtractThumbnail], families
    )

    _add_instance(context, "renderMain")
    families = collect_families_from_instances(context, only_active=True)
    assert pyblish.logic.plugins_by_families([ExtractThumbnail], families)


def test_apply_result(tmp_path) -> None:
    """Apply adds representations, thumbnail path and removes sources."""
    context = _create_context()
    farm_repre = {
        "name": "farm", "tags": ["delete", "need_thumbnail", "publish_on_farm"]
    }
    temp_repre = {"name": "temp", "tags": ["delete", "need_thumbnail"]}
    keep_repre = {"name": "keep", "tags": ["need_thumbnail"]}
    instance = _add_instance(
        context,
        "renderMain",
        representations=[farm_repre, temp_repre, keep_repre],
    )
    _write_file(str(tmp_path / "a_thumb.jpg"))
    _write_file(str(tmp_path / "b_thumb.jpg"))
    plugin = ExtractThumbnail()
    result = _InstanceResult(instance, plugin.log)
    result.representations = [
        {"name": "thumbnail_a", "files": "a_thumb.jpg",
         "stagingDir": str(tmp_path)},
        {"name": "thumbnail_b", "files": "b_thumb.jpg",
         "stagingDir": str(tmp_path)},
    ]

    plugin._apply_result(result)

    assert instance.data["thumbnailPath"] == str(tmp_path / "a_thumb.jpg")
    assert [repre["name"] for repre in instance.data["representations"]] == [
        "farm", "keep", "thumbnail_a", "thumbnail_b"
    ]


def test_apply_result_keeps_existing_thumbnail_path(tmp_path) -> None:
    """Existing thumbnail path is not replaced when the file exists."""
    context = _create_context()
    existing = _write_file(str(tmp_path / "existing.jpg"))
    instance = _add_instance(context, "renderMain", thumbnailPath=existing)
    _write_file(str(tmp_path / "a_thumb.jpg"))
    plugin = ExtractThumbnail()
    result = _InstanceResult(instance, plugin.log)
    result.representations = [
        {"name": "thumbnail", "files": "a_thumb.jpg",
         "stagingDir": str(tmp_path)},
    ]

    plugin._apply_result(result)

    assert instance.data["thumbnailPath"] == existing


def test_main_process_does_not_modify_instance(tmp_path, monkeypatch):
    """Worker logic stores outputs to the result, not to the instance."""
    monkeypatch.setattr(extract_thumbnail, "is_oiio_supported", lambda: False)

    def _create_thumbnail_ffmpeg(self, src_path, dst_path, *args):
        _write_file(dst_path)
        return True

    monkeypatch.setattr(
        ExtractThumbnail, "_create_thumbnail_ffmpeg", _create_thumbnail_ffmpeg
    )
    context = _create_context()
    instance = _add_instance(
        context,
        "renderMain",
        representations=[{
            "name": "exr",
            "ext": "exr",
            "files": ["a.1001.exr", "a.1002.exr"],
            "stagingDir": str(tmp_path),
            "tags": ["review"],
        }],
    )
    plugin = ExtractThumbnail()
    plugin.profiles = [PROFILE]
    instance_data = copy.deepcopy(dict(instance.data))
    result = _InstanceResult(instance, plugin.log)

    plugin._main_process(instance, result, result.log)

    assert dict(instance.data) == instance_data
    assert context.data["cleanupFullPaths"] == []
    context.data["cleanupFullPaths"].append(result.staging_dir)
    assert result.staging_dir
    assert [repre["files"] for repre in result.representations] == [
        "a.1002_thumb.jpg"
    ]

    plugin._apply_result(result)

    thumbnail_path = os.path.join(result.staging_dir, "a.1002_thumb.jpg")
    assert instance.data["thumbnailPath"] == thumbnail_path
    assert instance.data["representations"][-1]["name"] == "thumbnail"


def test_process_runs_instances_in_parallel(tmp_path, monkeypatch) -> None:
    """Instances run concurrently and results are applied in order."""
    instance_count = 4
    barrier = threading.Barrier(instance_count, timeout=10)
    worker_threads = set()

    def _on_process(plugin, instance):
        worker_threads.add(threading.current_thread())
        # Nothing may be applied before all workers finished
        assert not instance.data["representations"]
        assert not instance.context.data["cleanupFullPaths"]
        # Fails with 'BrokenBarrierError' if instances run serially
        barrier.wait()

    monkeypatch.setattr(
        ExtractThumbnail,
        "_main_process",
        _fake_main_process_factory(tmp_path, _on_process),
    )
    context = _create_context()
    instances = [
        _add_instance(context, f"render{idx}")
        for idx in range(instance_count)
    ]
    plugin = ExtractThumbnail()
    plugin.max_workers = instance_count

    plugin.process(context)

    assert threading.main_thread() not in worker_threads
    assert len(worker_threads) == instance_count
    staging_dirs = []
    for instance in instances:
        repres = instance.data["representations"]
        assert [repre["name"] for repre in repres] == ["thumbnail"]
        staging_dirs.append(repres[0]["stagingDir"])
        assert instance.data["thumbnailPath"] == os.path.join(
            repres[0]["stagingDir"], repres[0]["files"]
        )
    assert context.data["cleanupFullPaths"] == staging_dirs


def test_process_serial_in_main_thread(tmp_path, monkeypatch) -> None:
    """With a single worker instances are processed in the main thread."""
    threads = []
    monkeypatch.setattr(
        ExtractThumbnail,
        "_main_process",
        _fake_main_process_factory(
            tmp_path, lambda *_: threads.append(threading.current_thread())
        ),
    )
    context = _create_context()
    _add_instance(context, "renderA")
    _add_instance(context, "renderB")
    plugin = ExtractThumbnail()
    plugin.max_workers = 1

    plugin.process(context)

    assert threads == [threading.main_thread()] * 2


def test_process_reports_failed_instance(tmp_path, monkeypatch) -> None:
    """Failure of one instance names it and other instances are applied."""
    error = ValueError("Broken source")

    def _on_process(plugin, instance):
        if instance.name == "renderBroken":
            raise error

    monkeypatch.setattr(
        ExtractThumbnail,
        "_main_process",
        _fake_main_process_factory(tmp_path, _on_process),
    )
    context = _create_context()
    ok_instance = _add_instance(context, "renderOk")
    broken_instance = _add_instance(context, "renderBroken")
    plugin = ExtractThumbnail()
    plugin.max_workers = 2

    with pytest.raises(RuntimeError, match="renderBroken") as exc_info:
        plugin.process(context)

    assert exc_info.value.__cause__ is error
    assert "renderOk" not in str(exc_info.value)
    assert ok_instance.data["representations"]
    assert not broken_instance.data["representations"]
    # Staging directories of both instances are cleaned up
    assert len(context.data["cleanupFullPaths"]) == 2


def test_worker_logs_reach_publish_records(tmp_path, monkeypatch) -> None:
    """Logs from worker threads are captured by pyblish with a prefix."""
    monkeypatch.setattr(
        ExtractThumbnail, "_main_process", _fake_main_process_factory(tmp_path)
    )
    monkeypatch.setattr(ExtractThumbnail, "max_workers", 2)
    context = _create_context()
    _add_instance(context, "renderA", label="Render A")
    _add_instance(context, "renderB")

    result = pyblish.plugin.process(ExtractThumbnail, context)

    assert result["success"], result["error"]
    worker_records = [
        record
        for record in result["records"]
        if record.getMessage().endswith("Creating thumbnail")
    ]
    assert sorted(record.getMessage() for record in worker_records) == [
        "[Render A] Creating thumbnail",
        "[renderB] Creating thumbnail",
    ]
    assert all(
        record.threadName.startswith("ExtractThumbnail")
        for record in worker_records
    )
