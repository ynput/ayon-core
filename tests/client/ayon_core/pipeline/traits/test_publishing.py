"""Unit tests for publishing-related trait helpers."""
from __future__ import annotations

import re
from pathlib import Path

import pyblish.api
import pytest

from ayon_core.pipeline.publish import PublishError
from ayon_core.pipeline.traits import (
    Bundle,
    FileLocation,
    FileLocations,
    FrameRanged,
    Representation,
    Sequence,
    TemplatePath,
    UDIM,
    Variant,
)
from ayon_core.pipeline.traits.publishing import (
    get_transfers_from_representations,
)


class _DummyFormattedTemplate(str):
    def __new__(cls, value: str, used_values: dict):
        obj = super().__new__(cls, value)
        obj.used_values = used_values
        return obj


class _DummyPathTemplate(str):
    def __new__(cls, value: str):
        return super().__new__(cls, value)

    def format_strict(self, data: dict) -> _DummyFormattedTemplate:
        return _DummyFormattedTemplate(
            self.format(**data),
            {
                key: value
                for key, value in data.items()
                if key in {"representation", "output", "ext", "frame", "udim"}
            },
        )


class _DummyAnatomy:
    def __init__(self, frame_padding: int = 4):
        self.templates_obj = type(
            "TemplatesObj", (), {"frame_padding": frame_padding}
        )()


@pytest.fixture
def instance(tmp_path: Path) -> pyblish.api.Instance:
    """Create a minimal pyblish instance for unit tests."""
    context = pyblish.api.Context()
    context.data["anatomy"] = _DummyAnatomy()

    instance = context.create_instance("test_instance")
    instance.data["anatomyData"] = {}
    instance.data["version"] = 1
    instance.data["publish_root"] = tmp_path / "publish"
    return instance


def _create_file(file_path: Path, content: bytes = b"content") -> Path:
    file_path.parent.mkdir(parents=True, exist_ok=True)
    file_path.write_bytes(content)
    return file_path


def _make_template(
        instance: pyblish.api.Instance,
        pattern: str) -> dict[str, _DummyPathTemplate]:
    """Create template based on instance and pattern.

    Args:
        instance: pyblish.api.Instance
        pattern: str

    Returns:
        dict[str, str]: Template data with path template.
    """
    publish_root = instance.data["publish_root"]
    return {
        "path": _DummyPathTemplate((publish_root / pattern).as_posix())
    }


def test_get_transfers_from_representations_single_file_uses_variant(
    instance: pyblish.api.Instance,
    tmp_path: Path,
) -> None:
    """Single-file representations should use Variant as template output."""
    source = _create_file(tmp_path / "source" / "beauty.exr")
    representation = Representation(name="beauty", traits=[
        FileLocation(file_path=source),
        Variant(variant="preview"),
    ])

    transfers = get_transfers_from_representations(
        instance,
        _make_template(
            instance,
            "{representation}/{output}/publish.{ext}"),
        [representation],
    )

    assert len(transfers) == 1
    assert transfers[0].source == source
    assert transfers[0].destination == (
        instance.data["publish_root"] / "beauty" / "preview" / "publish.exr"
    )
    assert transfers[0].template_data["output"] == "preview"

    template_path = representation.get_trait(TemplatePath)
    assert template_path.data["ext"] == "exr"
    assert template_path.data["output"] == "preview"


def test_get_transfers_from_representations_sequence_dispatches_file_locations(
    instance: pyblish.api.Instance,
    tmp_path: Path,
) -> None:
    """Sequence representations should generate one transfer per frame."""
    files = [
        _create_file(tmp_path / "source" / f"img.{frame:04d}.png")
        for frame in (1, 2)
    ]
    representation = Representation(name="sequence", traits=[
        FrameRanged(frame_start=1, frame_end=2, frames_per_second="24"),
        Sequence(
            frame_padding=4,
            frame_regex=re.compile(
                r"img\.(?P<index>(?P<padding>0*)\d{4})\.png$"),
        ),
        FileLocations(file_paths=[
            FileLocation(file_path=file_path)
            for file_path in files
        ]),
    ])

    transfers = get_transfers_from_representations(
        instance,
        _make_template(instance, "{representation}/{frame:04d}.{ext}"),
        [representation],
    )

    assert len(transfers) == 2
    assert {transfer.source for transfer in transfers} == set(files)
    assert {transfer.destination for transfer in transfers} == {
        instance.data["publish_root"] / "sequence" / "0001.png",
        instance.data["publish_root"] / "sequence" / "0002.png",
    }
    assert representation.get_trait(TemplatePath).data["frame"] == 2


def test_get_transfers_from_representations_udim_dispatches_file_locations(
    instance: pyblish.api.Instance,
    tmp_path: Path,
) -> None:
    """UDIM representations should add one transfer per tile."""
    files = [
        _create_file(tmp_path / "source" / f"texture.{udim}.exr")
        for udim in (1001, 1002)
    ]
    representation = Representation(name="tiles", traits=[
        FileLocations(file_paths=[
            FileLocation(file_path=file_path)
            for file_path in files
        ]),
        UDIM(udim=[1001, 1002]),
    ])

    transfers = get_transfers_from_representations(
        instance,
        _make_template(instance, "{representation}/{udim}.{ext}"),
        [representation],
    )

    assert len(transfers) == 2
    assert {transfer.destination for transfer in transfers} == {
        instance.data["publish_root"] / "tiles" / "1001.exr",
        instance.data["publish_root"] / "tiles" / "1002.exr",
    }
    assert representation.get_trait(TemplatePath).data["udim"] == 1002


def test_get_transfers_from_representations_preserves_common_root_hierarchy(
    instance: pyblish.api.Instance,
    tmp_path: Path,
) -> None:
    """Grouped FileLocations should preserve their relative hierarchy."""
    common_root = tmp_path / "source" / "textures"
    file_paths = [
        _create_file(common_root / "diffuse" / "beauty.png"),
        _create_file(common_root / "masks" / "crypto" / "object.png"),
    ]
    representation = Representation(name="hierarchy", traits=[
        FileLocations(file_paths=[
            FileLocation(file_path=file_path)
            for file_path in file_paths
        ]),
    ])

    transfers = get_transfers_from_representations(
        instance,
        _make_template(instance, "{representation}/placeholder.png"),
        [representation],
    )

    assert len(transfers) == 2
    assert {
        transfer.destination.relative_to(
            instance.data["publish_root"] / "hierarchy"
        )
        for transfer in transfers
    } == {
        file_path.relative_to(common_root)
        for file_path in file_paths
    }
    assert representation.contains_trait(TemplatePath)


def test_get_transfers_from_representations_recurses_into_bundles(
    instance: pyblish.api.Instance,
    tmp_path: Path,
) -> None:
    """Bundle items should be traversed recursively."""
    first_file = _create_file(tmp_path / "source" / "first.txt")
    second_file = _create_file(tmp_path / "source" / "second.json")
    representation = Representation(name="bundle", traits=[
        Bundle(items=[
            [FileLocation(file_path=first_file)],
            [Bundle(items=[
                [FileLocation(file_path=second_file)],
            ])],
        ]),
    ])

    transfers = get_transfers_from_representations(
        instance,
        _make_template(instance, "{representation}/publish.{ext}"),
        [representation],
    )

    assert len(transfers) == 2
    assert {
        transfer.source for transfer in transfers
    } == {first_file, second_file}
    assert {transfer.destination.name for transfer in transfers} == {
        "publish.txt",
        "publish.json",
    }


def test_get_transfers_from_representations_raises_publish_error_on_invalid_representation(  # noqa: E501
    instance: pyblish.api.Instance,
) -> None:
    """Invalid repres should be rejected before transfers are built."""
    representation = Representation(
        name="broken",
        traits=[FileLocations(file_paths=[])],
    )

    with pytest.raises(
        PublishError,
        match=r"Representation 'broken' is invalid"):
        get_transfers_from_representations(
            instance,
            _make_template(instance, "{representation}/publish.dat"),
            [representation],
        )
