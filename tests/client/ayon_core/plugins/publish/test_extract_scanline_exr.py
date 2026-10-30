"""Tests for the ExtractScanlineExr publish plugin."""
from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from ayon_core.plugins.publish import extract_scanline_exr

PLUGIN_MODULE = extract_scanline_exr
OIIO_ARGS = ["oiiotool"]


@pytest.fixture
def tmp_path(tmp_path_factory):
    """Give every test its own directory.

    The `pytest-ayon` plugin (installed in CI) replaces the built-in
    `tmp_path` fixture with a session-scoped one, which would let
    temporary files from one test leak into the checks of another. A
    module-level fixture takes precedence over plugin fixtures.
    """
    return tmp_path_factory.mktemp("scanline")


def _write(path, data=b"tiled"):
    path.write_bytes(data)


def _read(path):
    return path.read_bytes()


def _make_instance(staging_dir, files, tags=("toScanline",), ext="exr"):
    representaion = {
        "name": "exr_tiled",
        "ext": ext,
        "files": files,
        "tags": list(tags),
        "stagingDir": str(staging_dir),
    }
    instance = SimpleNamespace(
        data={"representations": [representaion]}
    )
    return instance, representaion


def _run_plugin(monkeypatch, instance, run_subprocess):
    monkeypatch.setattr(
        PLUGIN_MODULE, "get_oiio_tool_args", lambda _tool: list(OIIO_ARGS)
    )
    monkeypatch.setattr(PLUGIN_MODULE, "run_subprocess", run_subprocess)
    PLUGIN_MODULE.ExtractScanlineExr().process(instance)


def _success_run(calls):
    def run_subprocess(args, logger=None):
        calls.append(args)
        with open(args[-1], "wb") as stream:
            stream.write(b"scanline")

    return run_subprocess


def _failing_run(calls):
    def run_subprocess(args, logger=None):
        calls.append(args)
        raise RuntimeError("oiiotool exited with 1")

    return run_subprocess


def _fail_on_second_frame(calls):
    def run_subprocess(args, logger=None):
        calls.append(args)
        if "1002" in args[1]:
            raise RuntimeError("oiiotool exited with 1")
        with open(args[-1], "wb") as stream:
            stream.write(b"scanline")

    return run_subprocess


def _no_output_run(calls):
    def run_subprocess(args, logger=None):
        calls.append(args)

    return run_subprocess


def _zero_byte_run(calls):
    def run_subprocess(args, logger=None):
        calls.append(args)
        with open(args[-1], "wb"):
            pass

    return run_subprocess


def _temp_files(directory):
    return sorted(
        path.name for path in directory.iterdir()
        if path.name.startswith(".")
    )


def _assert_no_temp_files(directory):
    assert _temp_files(directory) == []


def _assert_publish_error(excinfo, path_fragment=None):
    """Assert a PublishError with an optional file path in the message."""
    error = excinfo.value
    assert isinstance(error, PLUGIN_MODULE.PublishError)
    if path_fragment is not None:
        assert path_fragment in str(error)


def _assert_sources_unchanged(directory, files):
    for name in files:
        assert _read(directory / name) == b"tiled", name


def test_single_frame_success(tmp_path, monkeypatch):
    """A single frame is converted, tags updated and no temp file remains."""
    path = tmp_path / "a.1001.exr"
    _write(path)
    instance, repre = _make_instance(tmp_path, "a.1001.exr")
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    assert repre["name"] == "exr"
    assert repre["tags"] == []
    # The representation is updated in place, not duplicated
    assert instance.data["representations"] == [repre]
    _assert_no_temp_files(tmp_path)
    assert isinstance(calls[0], list)


def test_sequence_success(tmp_path, monkeypatch):
    """Every frame of a sequence is converted."""
    files = ["b.1001.exr", "b.1002.exr", "b.1003.exr"]
    for name in files:
        _write(tmp_path / name)
    instance, _repre = _make_instance(tmp_path, files)
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    for name in files:
        assert _read(tmp_path / name) == b"scanline"
    assert len(calls) == len(files)
    _assert_no_temp_files(tmp_path)


def test_multiple_representations_are_converted(tmp_path, monkeypatch):
    """Every tagged representation of an instance is converted."""
    files = ["aa.1001.exr", "bb.1001.exr"]
    for name in files:
        _write(tmp_path / name)
    representations = [
        {"name": "aa", "ext": "exr", "files": "aa.1001.exr",
         "tags": ["toScanline"], "stagingDir": str(tmp_path)},
        {"name": "bb", "ext": "exr", "files": "bb.1001.exr",
         "tags": ["toScanline"], "stagingDir": str(tmp_path)},
    ]
    instance = SimpleNamespace(
        data={"representations": representations}
    )
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    for name in files:
        assert _read(tmp_path / name) == b"scanline"
    assert [rep["tags"] for rep in representations] == [[], []]
    _assert_no_temp_files(tmp_path)


def test_uppercase_exr_extension_is_converted(tmp_path, monkeypatch):
    """An upper-case EXR extension is converted as well."""
    path = tmp_path / "u.1001.EXR"
    _write(path)
    instance, repre = _make_instance(
        tmp_path, "u.1001.EXR", ext="EXR"
    )
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    assert repre["tags"] == []
    _assert_no_temp_files(tmp_path)


def test_staging_dir_with_spaces(tmp_path, monkeypatch):
    """A staging directory containing spaces is handled."""
    staging = tmp_path / "staging dir with spaces"
    staging.mkdir()
    path = staging / "l.1001.exr"
    _write(path)
    instance, _repre = _make_instance(staging, "l.1001.exr")
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    assert isinstance(calls[0], list)
    _assert_no_temp_files(staging)


def test_relative_staging_dir(tmp_path, monkeypatch):
    """A relative stagingDir is resolved against the current directory."""
    staging = tmp_path / "rel"
    staging.mkdir()
    path = staging / "m.1001.exr"
    _write(path)
    monkeypatch.chdir(tmp_path)
    instance, _repre = _make_instance("rel", "m.1001.exr")
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    _assert_no_temp_files(staging)


def test_file_in_subdirectory(tmp_path, monkeypatch):
    """Files in a subdirectory get their temporary output next to them."""
    sub = tmp_path / "sub"
    sub.mkdir()
    path = sub / "n.1001.exr"
    _write(path)
    instance, _repre = _make_instance(tmp_path, "sub/n.1001.exr")
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    _assert_no_temp_files(sub)
    _assert_no_temp_files(tmp_path)


def test_absolute_file_path(tmp_path, monkeypatch):
    """Absolute entries in the files list are converted in place."""
    path = tmp_path / "v.1001.exr"
    _write(path)
    instance, _repre = _make_instance(tmp_path, str(path))
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    _assert_no_temp_files(tmp_path)


def test_missing_to_scanline_tag_is_skipped(tmp_path, monkeypatch):
    """Representations without the tag are not processed."""
    path = tmp_path / "h.1001.exr"
    _write(path)
    instance, repre = _make_instance(
        tmp_path, "h.1001.exr", tags=()
    )
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert calls == []
    assert _read(path) == b"tiled"
    assert repre["tags"] == []


def test_non_exr_representation_is_skipped(tmp_path, monkeypatch):
    """Non-EXR files are not passed to oiiotool."""
    path = tmp_path / "i.1001.jpg"
    _write(path, b"image")
    instance, _repre = _make_instance(
        tmp_path, "i.1001.jpg", ext="jpg"
    )
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert calls == []
    assert _read(path) == b"image"


def test_missing_staging_dir_is_skipped(tmp_path, monkeypatch):
    """A representation without stagingDir is skipped."""
    instance, repre = _make_instance(tmp_path, "o.1001.exr")
    repre["stagingDir"] = None
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert calls == []
    _assert_no_temp_files(tmp_path)


def test_oiiotool_failure_keeps_sources(tmp_path, monkeypatch):
    """A failing oiiotool keeps sources and raises PublishError."""
    path = tmp_path / "c.1001.exr"
    _write(path)
    instance, repre = _make_instance(tmp_path, "c.1001.exr")
    calls = []

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _failing_run(calls))

    _assert_publish_error(excinfo, str(path))
    # The original tool error must be preserved as the cause
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    assert _read(path) == b"tiled"
    assert repre["tags"] == ["toScanline"]
    assert repre["name"] == "exr_tiled"
    _assert_no_temp_files(tmp_path)


def test_second_frame_failure_keeps_all_sources(tmp_path, monkeypatch):
    """A failure on the second frame does not convert the first one."""
    files = ["e.1001.exr", "e.1002.exr", "e.1003.exr"]
    for name in files:
        _write(tmp_path / name)
    instance, repre = _make_instance(tmp_path, files)
    calls = []

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _fail_on_second_frame(calls))

    _assert_publish_error(excinfo, "e.1002.exr")
    assert isinstance(excinfo.value.__cause__, RuntimeError)
    _assert_sources_unchanged(tmp_path, files)
    assert repre["tags"] == ["toScanline"]
    _assert_no_temp_files(tmp_path)


def test_empty_output_keeps_sources(tmp_path, monkeypatch):
    """A missing output is treated as a failure."""
    path = tmp_path / "f.1001.exr"
    _write(path)
    instance, _repre = _make_instance(tmp_path, "f.1001.exr")
    calls = []

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _no_output_run(calls))

    _assert_publish_error(excinfo, str(path))
    assert _read(path) == b"tiled"
    _assert_no_temp_files(tmp_path)


def test_zero_byte_output_keeps_sources(tmp_path, monkeypatch):
    """A zero-byte output file is treated as a failed conversion."""
    path = tmp_path / "k.1001.exr"
    _write(path)
    instance, _repre = _make_instance(tmp_path, "k.1001.exr")
    calls = []

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _zero_byte_run(calls))

    _assert_publish_error(excinfo, str(path))
    assert _read(path) == b"tiled"
    _assert_no_temp_files(tmp_path)


def test_missing_source_keeps_other_files(tmp_path, monkeypatch):
    """A missing source file raises PublishError without converting others."""
    present = tmp_path / "g.1001.exr"
    _write(present)
    instance, _repre = _make_instance(
        tmp_path, ["g.1001.exr", "g.1002.exr"]
    )
    calls = []

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _success_run(calls))

    _assert_publish_error(excinfo, "g.1002.exr")
    assert _read(present) == b"tiled"
    _assert_no_temp_files(tmp_path)


def test_tool_not_found_raises_publish_error(tmp_path, monkeypatch):
    """A missing OIIO tool raises PublishError and keeps the sources."""
    path = tmp_path / "j.1001.exr"
    _write(path)
    instance, _repre = _make_instance(tmp_path, "j.1001.exr")

    def _missing_tool(_tool):
        raise PLUGIN_MODULE.ToolNotFoundError("oiiotool missing")

    monkeypatch.setattr(PLUGIN_MODULE, "get_oiio_tool_args", _missing_tool)
    monkeypatch.setattr(PLUGIN_MODULE, "run_subprocess", _success_run([]))

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        PLUGIN_MODULE.ExtractScanlineExr().process(instance)

    _assert_publish_error(excinfo, "OIIO tool not found")
    assert _read(path) == b"tiled"


def test_keyboard_interrupt_cleans_temp_outputs(tmp_path, monkeypatch):
    """An interrupt cleans temporary outputs and keeps every source."""
    files = ["p.1001.exr", "p.1002.exr"]
    for name in files:
        _write(tmp_path / name)
    instance, repre = _make_instance(tmp_path, files)
    calls = []

    def run_subprocess(args, logger=None):
        calls.append(args)
        if len(calls) == 1:
            with open(args[-1], "wb") as stream:
                stream.write(b"scanline")
            return
        raise KeyboardInterrupt

    with pytest.raises(KeyboardInterrupt):
        _run_plugin(monkeypatch, instance, run_subprocess)

    _assert_sources_unchanged(tmp_path, files)
    assert repre["tags"] == ["toScanline"]
    _assert_no_temp_files(tmp_path)


class _OsWithFailingReplace:
    """os proxy whose replace fails, used to test swap failure cleanup."""

    def __getattr__(self, name):
        return getattr(os, name)

    @staticmethod
    def replace(_source, _destination):
        raise OSError("disk full")


def test_replace_failure_keeps_source_and_cleans_temps(tmp_path, monkeypatch):
    """A failed os.replace keeps the source and removes temp outputs."""
    path = tmp_path / "w.1001.exr"
    _write(path)
    instance, repre = _make_instance(tmp_path, "w.1001.exr")

    monkeypatch.setattr(PLUGIN_MODULE, "os", _OsWithFailingReplace())

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, _success_run([]))

    _assert_publish_error(excinfo, str(path))
    assert isinstance(excinfo.value.__cause__, OSError)
    assert _read(path) == b"tiled"
    assert repre["tags"] == ["toScanline"]
    _assert_no_temp_files(tmp_path)


def test_stale_temp_file_does_not_block_retry(tmp_path, monkeypatch):
    """A leftover temp file from an earlier run does not break a new run."""
    path = tmp_path / "x.1001.exr"
    _write(path)
    stale = tmp_path / ".x.1001.deadbeefdeadbeefdeadbeefdeadbeef.exr"
    stale.write_bytes(b"stale")
    instance, _repre = _make_instance(tmp_path, "x.1001.exr")
    calls = []

    _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(path) == b"scanline"
    assert stale.exists()
    assert _temp_files(tmp_path) == [stale.name]


def test_existing_exr_representation_logs_warning(
    tmp_path, monkeypatch, caplog
):
    """Converting to the generic 'exr' name warns about a collision."""
    converted = tmp_path / "y.1001.exr"
    existing = tmp_path / "z.1001.exr"
    _write(converted)
    _write(existing)
    representations = [
        {"name": "exr", "ext": "exr", "files": "z.1001.exr",
         "tags": [], "stagingDir": str(tmp_path)},
        {"name": "converted", "ext": "exr", "files": "y.1001.exr",
         "tags": ["toScanline"], "stagingDir": str(tmp_path)},
    ]
    instance = SimpleNamespace(
        data={"representations": representations}
    )
    calls = []

    with caplog.at_level("WARNING"):
        _run_plugin(monkeypatch, instance, _success_run(calls))

    assert _read(converted) == b"scanline"
    assert "already named 'exr'" in caplog.text
    _assert_no_temp_files(tmp_path)


def test_multi_representation_failure_semantics(tmp_path, monkeypatch):
    """A later representation failing keeps the earlier one converted."""
    good = tmp_path / "q.1001.exr"
    bad = tmp_path / "r.1001.exr"
    _write(good)
    _write(bad)
    representations = [
        {"name": "good", "ext": "exr", "files": "q.1001.exr",
         "tags": ["toScanline"], "stagingDir": str(tmp_path)},
        {"name": "bad", "ext": "exr", "files": "r.1001.exr",
         "tags": ["toScanline"], "stagingDir": str(tmp_path)},
    ]
    instance = SimpleNamespace(
        data={"representations": representations}
    )

    def run_subprocess(args, logger=None):
        if "r.1001" in args[1]:
            raise RuntimeError("oiiotool exited with 1")
        with open(args[-1], "wb") as stream:
            stream.write(b"scanline")

    with pytest.raises(PLUGIN_MODULE.PublishError) as excinfo:
        _run_plugin(monkeypatch, instance, run_subprocess)

    _assert_publish_error(excinfo, "r.1001.exr")
    assert _read(good) == b"scanline"
    assert _read(bad) == b"tiled"
    assert representations[0]["tags"] == []
    assert representations[1]["tags"] == ["toScanline"]
    _assert_no_temp_files(tmp_path)
