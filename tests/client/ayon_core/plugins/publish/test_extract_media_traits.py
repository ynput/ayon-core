"""Tests for trait-based review, transcode, burnin, thumbnail and slate."""
from __future__ import annotations

import logging
from pathlib import Path

import pyblish.api
import pytest

from ayon_core.pipeline.publish import (
    PublishError,
    add_trait_representation_files_for_cleanup,
    convert_legacy_representations,
    get_trait_representations,
    set_trait_representations,
)
from ayon_core.pipeline.publish.trait_conversion import (
    legacy_dict_to_representation,
    representation_to_legacy_dict,
)
from ayon_core.pipeline.publish.trait_utils import (
    copy_representation,
    get_ocio_config_path,
    is_staging_persistent,
    set_files,
    set_staging_directory,
    update_persistence,
)
from ayon_core.pipeline.traits import (
    ColorManaged,
    CustomTags,
    FileLocation,
    FileLocations,
    FrameRanged,
    Handles,
    Image,
    MimeType,
    Persistent,
    PixelBased,
    Representation,
    ReviewOutput,
    Sequence,
    Slate,
    StagingDirectory,
    Tagged,
    Variant,
    get_frame_range_data,
)
from ayon_core.plugins.publish import (
    extract_burnin_traits,
    extract_color_transcode_traits,
    extract_review_traits,
    extract_thumbnail_traits,
)
from ayon_core.plugins.publish.extract_burnin_traits import (
    ExtractBurninTraits,
)
from ayon_core.plugins.publish.extract_color_transcode_traits import (
    ExtractOIIOTranscodeTraits,
)
from ayon_core.plugins.publish.extract_review_slate_traits import (
    ExtractReviewSlateTraits,
)
from ayon_core.plugins.publish.extract_review_traits import (
    TraitReviewRenderer,
)
from ayon_core.plugins.publish.extract_slate_data_traits import (
    ExtractSlateDataTraits,
)
from ayon_core.plugins.publish.extract_thumbnail import ThumbnailDef
from ayon_core.plugins.publish.extract_thumbnail_traits import (
    ExtractThumbnailTraits,
)

LOG = logging.getLogger("test")


def _instance(representations: list[Representation]) -> pyblish.api.Instance:
    context = pyblish.api.Context()
    context.data["cleanupFullPaths"] = []
    instance = context.create_instance("test")
    set_trait_representations(instance, representations)
    return instance


def _plugin(plugin_class):
    plugin = plugin_class()
    plugin.log = LOG
    return plugin


def _frames(directory: Path, name: str, frames: range) -> list[Path]:
    directory.mkdir(parents=True, exist_ok=True)
    paths = []
    for frame in frames:
        path = directory / f"{name}.{frame:04d}.exr"
        path.write_bytes(b"")
        paths.append(path)
    return paths


def _review_representation(tmp_path: Path) -> Representation:
    frame_ranged = FrameRanged(frame_start=998, frame_end=1012)
    frame_ranged.frame_rate = 25
    return Representation(name="h264", traits=[
        FileLocation(file_path=tmp_path / "review.mp4"),
        Tagged(tags=["review", "burnin", "slate-frame"]),
        Variant(variant="h264"),
        Slate(frames=1),
        ReviewOutput(
            burnins=["burnin"],
            ffmpeg_cmd="ffmpeg -i input output",
        ),
        ColorManaged(color_space="sRGB"),
        frame_ranged,
        Handles(inclusive=True, frame_start_handle=2, frame_end_handle=2),
        Persistent(),
    ])


def _sequence_representation(paths: list[Path], tags: list[str]):
    representation = Representation(name="exr", traits=[
        Tagged(tags=tags),
        ColorManaged(color_space="ACEScg", config_path="config.ocio"),
        Persistent(),
    ])
    set_files(representation, paths, sequence=True, frame_rate=25)
    return representation


def test_frame_range_data(tmp_path: Path) -> None:
    """Content frame range is without slate and handles."""
    frame_range = get_frame_range_data(_review_representation(tmp_path))

    # 998 slate, 999-1000 handles, 1001-1010 content, 1011-1012 handles
    assert frame_range.content_frame_start == 1001
    assert frame_range.content_frame_end == 1010
    assert (frame_range.handle_start, frame_range.handle_end) == (2, 2)

    no_frames = Representation(name="mov", traits=[
        FileLocation(file_path=tmp_path / "file.mov")])
    assert get_frame_range_data(no_frames) is None


def test_legacy_conversion(tmp_path: Path) -> None:
    """Review output, frame rate and slate survive conversion."""
    legacy = representation_to_legacy_dict(_review_representation(tmp_path))

    assert legacy["outputName"] == "h264"
    assert legacy["burnins"] == ["burnin"]
    assert legacy["ffmpeg_cmd"] == "ffmpeg -i input output"
    assert legacy["fps"] == 25.0
    assert "source_resolution_width" not in legacy
    assert legacy["data"] == {"slateFrames": 1}

    restored = legacy_dict_to_representation(legacy)
    review_output = restored.get_trait(ReviewOutput)
    assert review_output.burnins == ["burnin"]
    assert review_output.ffmpeg_cmd == "ffmpeg -i input output"
    assert restored.get_trait(Slate).frames == 1


class _RootAnatomy:
    """Anatomy filling "{root[work]}" with a directory."""

    def __init__(self, root: Path) -> None:
        self.root = root

    def fill_root(self, template: str) -> str:
        return template.replace("{root[work]}", self.root.as_posix())


def test_legacy_staging_dir_to_traits(tmp_path: Path) -> None:
    """Staging directory of legacy dict becomes `StagingDirectory`."""
    representation = legacy_dict_to_representation(
        {
            "name": "exr",
            "ext": "exr",
            "files": ["left/tex.1001.exr", "right/tex.1002.exr"],
            "stagingDir": "{root[work]}/stage",
            "stagingDir_persistent": True,
        },
        anatomy=_RootAnatomy(tmp_path),
    )

    staging_directory = representation.get_trait(StagingDirectory)
    assert staging_directory.path == tmp_path / "stage"
    assert staging_directory.is_persistent
    assert list(representation.get_trait(FileLocations).get_files()) == [
        tmp_path / "stage" / "left" / "tex.1001.exr",
        tmp_path / "stage" / "right" / "tex.1002.exr",
    ]
    # staging directory is used only during publishing
    assert StagingDirectory.id not in representation.traits_as_dict(
        persistent_only=True)

    # files are relative to the staging directory, with subdirectories
    legacy = representation_to_legacy_dict(representation)
    assert Path(legacy["stagingDir"]) == tmp_path / "stage"
    assert legacy["files"] == ["left/tex.1001.exr", "right/tex.1002.exr"]
    assert legacy["stagingDir_persistent"] is True


def test_legacy_staging_dir_fallback(tmp_path: Path) -> None:
    """Representation dict without staging dir uses passed default."""
    legacy = {"name": "mov", "ext": "mov", "files": "review.mov"}
    with pytest.raises(PublishError):
        legacy_dict_to_representation(dict(legacy))

    representation = legacy_dict_to_representation(
        dict(legacy), default_staging_dir=str(tmp_path))
    assert representation.get_trait(FileLocation).file_path == (
        tmp_path / "review.mov")
    assert not representation.get_trait(StagingDirectory).is_persistent


def test_convert_legacy_representations(tmp_path: Path) -> None:
    """Instance staging directory and anatomy are used for conversion."""
    instance = _instance([])
    instance.context.data["anatomy"] = _RootAnatomy(tmp_path)
    instance.data["stagingDir"] = "{root[work]}/instance"

    representations = convert_legacy_representations(instance, [
        {"name": "mov", "ext": "mov", "files": "review.mov"},
        {"name": "exr", "ext": "exr", "files": "render.exr",
         "stagingDir": "{root[work]}/own"},
    ])

    assert [
        r.get_trait(FileLocation).file_path for r in representations
    ] == [
        tmp_path / "instance" / "review.mov",
        tmp_path / "own" / "render.exr",
    ]


def test_trait_files_outside_staging_dir(tmp_path: Path) -> None:
    """Files must be in the staging directory of representation."""
    representation = Representation(name="exr", traits=[
        FileLocation(file_path=tmp_path / "a" / "file.exr"),
        StagingDirectory(path=tmp_path / "b"),
    ])
    with pytest.raises(PublishError):
        representation_to_legacy_dict(representation)


def test_files_for_cleanup_persistence(tmp_path: Path) -> None:
    """Files are kept if representation or instance staging persists."""
    representation = Representation(name="mov", traits=[
        FileLocation(file_path=tmp_path / "review.mov"),
    ])
    instance = _instance([])
    cleanup = instance.context.data["cleanupFullPaths"]

    add_trait_representation_files_for_cleanup(instance, representation)
    assert cleanup == [str(tmp_path / "review.mov")]

    cleanup.clear()
    set_staging_directory(representation, tmp_path, is_persistent=True)
    assert is_staging_persistent(representation)
    add_trait_representation_files_for_cleanup(instance, representation)
    assert cleanup == []

    # persistence is kept when staging directory changes
    set_staging_directory(representation, tmp_path / "other")
    assert is_staging_persistent(representation)

    set_staging_directory(representation, tmp_path, is_persistent=False)
    instance.data["stagingDir_persistent"] = True
    add_trait_representation_files_for_cleanup(instance, representation)
    assert cleanup == []


def test_persistent_traits_dict(tmp_path: Path) -> None:
    """Non-persistent traits are not stored."""
    traits = _review_representation(tmp_path).traits_as_dict(
        persistent_only=True)

    assert ReviewOutput.id not in traits
    assert Slate.id in traits
    assert Variant.id in traits
    # processing tags are not stored
    assert traits[Tagged.id] == {"tags": ["review"]}
    # but they are kept for publish plugins
    assert _review_representation(tmp_path).traits_as_dict()[
        Tagged.id] == {"tags": ["review", "burnin", "slate-frame"]}


def test_set_files(tmp_path: Path) -> None:
    """File traits describe the new files, frame rate is kept."""
    paths = _frames(tmp_path, "render", range(1001, 1004))
    representation = _sequence_representation(paths, ["review"])

    assert representation.get_trait(FileLocations).file_paths[0].file_path \
        == paths[0]
    assert representation.get_trait(Sequence).frame_padding == 4
    frame_ranged = representation.get_trait(FrameRanged)
    assert (frame_ranged.frame_start, frame_ranged.frame_end) == (1001, 1003)
    assert frame_ranged.frame_rate == 25
    assert representation.contains_trait(Image)

    # single file replaces sequence traits, frame range is kept
    set_files(representation, [tmp_path / "review.mp4"], sequence=False)
    assert not representation.contains_trait(FileLocations)
    assert not representation.contains_trait(Sequence)
    assert not representation.contains_trait(Image)
    assert representation.get_trait(FileLocation).file_path == (
        tmp_path / "review.mp4")
    assert representation.get_trait(MimeType).mime_type == "video/mp4"
    assert representation.get_trait(FrameRanged).frame_start == 1001


def test_copy_and_persistence(tmp_path: Path) -> None:
    """Copy has its own traits, "delete" tag is not persistent."""
    source = _review_representation(tmp_path)
    copied = copy_representation(source, name="copy")

    copied.get_trait(Tagged).tags.append("delete")
    update_persistence(copied)

    assert copied.name == "copy"
    assert copied.representation_id != source.representation_id
    assert not copied.contains_trait(Persistent)
    assert source.contains_trait(Persistent)
    assert "delete" not in source.get_trait(Tagged).tags

    only_color = copy_representation(source, traits=[ColorManaged, Image])
    assert list(only_color.get_traits()) == [ColorManaged.id]


def test_get_ocio_config_path(tmp_path: Path) -> None:
    """Config path is used if it exists, template otherwise."""
    config = tmp_path / "config.ocio"
    config.write_text("")

    class _Anatomy:
        @staticmethod
        def fill_root(template: str) -> str:
            return template.replace("{root[work]}", tmp_path.as_posix())

    found = get_ocio_config_path(
        ColorManaged(color_space="sRGB", config_path=str(config)),
        _Anatomy(),
    )
    assert found == str(config)

    found = get_ocio_config_path(
        ColorManaged(
            color_space="sRGB",
            config_path="/other/machine/config.ocio",
            config_template="{root[work]}/config.ocio",
        ),
        _Anatomy(),
    )
    assert Path(found) == config

    assert get_ocio_config_path(
        ColorManaged(color_space="sRGB"), _Anatomy()) is None


def test_extract_slate_data_traits(tmp_path: Path) -> None:
    """Slate trait is added only to representations with slate frame."""
    slated = Representation(name="exr", traits=[
        FileLocation(file_path=tmp_path / "file.exr"),
        Tagged(tags=["review", "slate-frame"]),
    ])
    plain = Representation(name="mov", traits=[
        FileLocation(file_path=tmp_path / "file.mov"),
        Tagged(tags=["review"]),
    ])
    instance = _instance([slated, plain])

    ExtractSlateDataTraits().process(instance)

    assert slated.get_trait(Slate).frames == 1
    assert not plain.contains_trait(Slate)


def _review_instance(tmp_path, representation, **data):
    instance = _instance([representation])
    instance.context.data.update({
        "handleStart": 0,
        "handleEnd": 0,
    })
    instance.data.update({
        "fps": 24.0,
        "frameStart": 1,
        "frameEnd": 2,
        "handleStart": 0,
        "handleEnd": 0,
        **data,
    })
    return instance


def test_review_temp_data_from_traits(tmp_path: Path) -> None:
    """Frame range, handles and frame rate are used from traits."""
    # slate 1000, handles 1001-1002 and 1013-1014, content 1003-1012
    paths = _frames(tmp_path, "render", range(1000, 1015))
    source = _sequence_representation(paths, ["review"])
    source.add_traits([
        Slate(frames=1),
        Handles(inclusive=True, frame_start_handle=2, frame_end_handle=2),
    ])
    instance = _review_instance(tmp_path, source)
    renderer = TraitReviewRenderer(LOG)
    frame_range = get_frame_range_data(source)

    temp_data = renderer.prepare_trait_temp_data(
        instance, source, str(tmp_path), {"tags": []}, frame_range)
    assert temp_data.fps == 25.0
    assert (temp_data.frame_start, temp_data.frame_end) == (1003, 1012)
    # output contains all frames of the files - with slate and handles
    assert (temp_data.output_frame_start, temp_data.output_frame_end) == (
        1000, 1014)
    assert temp_data.first_sequence_frame == 1000
    assert temp_data.input_is_sequence
    assert temp_data.input_allow_bg

    # slate and handles in files are skipped for output without handles
    temp_data = renderer.prepare_trait_temp_data(
        instance, source, str(tmp_path), {"tags": ["no-handles"]},
        frame_range)
    assert (temp_data.output_frame_start, temp_data.output_frame_end) == (
        1003, 1012)
    # ffmpeg arguments of `ReviewRenderer` add the start handle
    assert temp_data.first_sequence_frame + temp_data.handle_start == 1003


def test_review_output_paths(tmp_path: Path) -> None:
    """Output file names are created from source file names."""
    paths = _frames(tmp_path / "src", "render", range(1001, 1004))
    source = _sequence_representation(paths, ["review"])
    instance = _review_instance(tmp_path, source)
    renderer = TraitReviewRenderer(LOG)
    temp_data = renderer.prepare_trait_temp_data(
        instance, source, str(tmp_path / "src"), {"tags": []},
        get_frame_range_data(source))

    output = extract_review_traits._OutputFiles(
        tags=[], staging_dir=str(tmp_path / "src"))
    renderer.input_output_paths(
        output, {"filename_suffix": "h264", "ext": "mp4", "tags": []},
        temp_data)
    assert output.files == ["render_h264.mp4"]
    assert not output.is_sequence
    # clique does not see not zero-padded frames as padded
    assert temp_data.full_input_path == str(
        tmp_path / "src" / "render.%d.exr")

    output = extract_review_traits._OutputFiles(
        tags=[], staging_dir=str(tmp_path / "src"))
    renderer.input_output_paths(
        output,
        {"filename_suffix": "png", "ext": "png", "tags": ["sequence"]},
        temp_data)
    assert output.is_sequence
    assert output.files[0] == "render_png.1001.png"
    assert Path(output.staging_dir) == tmp_path / "src" / "render_png"


def test_review_output_representation(tmp_path: Path, monkeypatch) -> None:
    """Review output is a new trait representation."""
    paths = _frames(tmp_path, "render", range(1001, 1004))
    source = _sequence_representation(paths, ["review", "delete"])
    source.add_trait(Variant(variant="main"))
    source.add_trait(CustomTags(tags=["custom"]))
    source.add_trait(StagingDirectory(path=tmp_path, is_persistent=True))
    instance = _review_instance(tmp_path, source, anatomyData={})

    def ffmpeg_arguments(self, output_def, _instance, output, temp_data,
                         fill_data, layer_name):
        self.input_output_paths(output, output_def, temp_data)
        output.resolution = (1920, 1080)
        output.source_resolution = (2048, 1152)
        return ["ffmpeg", "args"]

    monkeypatch.setattr(
        TraitReviewRenderer, "_ffmpeg_arguments", ffmpeg_arguments)
    monkeypatch.setattr(
        extract_review_traits, "run_subprocess", lambda *_a, **_k: None)
    output_def = {
        "filename_suffix": "h264",
        "ext": "mp4",
        "tags": ["burnin", "ftrackreview"],
        "burnins": ["burnin_def"],
        "fill_missing_frames": "only_rendered",
    }
    outputs = TraitReviewRenderer(LOG)._render_output(
        instance, source, str(tmp_path), str(tmp_path), output_def, "")

    assert len(outputs) == 1
    output = outputs[0]
    assert output.name == "main_h264_exr"
    assert output.get_trait(Variant).variant == "main_h264"
    assert output.get_trait(Tagged).tags == [
        "review", "burnin", "ftrackreview"]
    assert output.get_trait(FileLocation).file_path == (
        tmp_path / "render_h264.mp4")
    assert output.get_trait(PixelBased).display_window_width == 1920
    assert output.get_trait(CustomTags).tags == ["custom"]
    assert output.get_trait(ColorManaged).color_space == "ACEScg"
    assert output.contains_trait(Persistent)
    review_output = output.get_trait(ReviewOutput)
    assert review_output.burnins == ["burnin_def"]
    assert review_output.ffmpeg_cmd == "ffmpeg args"
    assert review_output.source_resolution_width == 2048
    frame_ranged = output.get_trait(FrameRanged)
    assert (frame_ranged.frame_start, frame_ranged.frame_end) == (1001, 1003)
    assert frame_ranged.frame_rate == 25
    assert output.get_trait(Handles).inclusive
    # output is staged next to the source, persistence is kept
    assert output.get_trait(StagingDirectory).path == tmp_path
    assert output.get_trait(StagingDirectory).is_persistent
    # source is not changed
    assert source.get_trait(Tagged).tags == ["review", "delete"]


def _burnin_plugin(monkeypatch, scripts: list[dict]):
    def run_burnin_script(self, script_data):
        scripts.append(script_data)
        output = Path(script_data["output"])
        if script_data["first_frame"] is None:
            output.write_bytes(b"")

    monkeypatch.setattr(
        ExtractBurninTraits, "_run_burnin_script", run_burnin_script)
    monkeypatch.setattr(
        ExtractBurninTraits, "_get_profile", lambda *_: {"burnins": []})
    monkeypatch.setattr(
        ExtractBurninTraits, "prepare_basic_data",
        lambda *_: ({}, {
            "frame_start": 1, "frame_end": 2,
            "frame_start_handle": 1, "frame_end_handle": 2,
        }))
    monkeypatch.setattr(
        ExtractBurninTraits, "_fill_instance_burnin_data", lambda *_: None)
    monkeypatch.setattr(
        extract_burnin_traits, "should_convert_for_ffmpeg",
        lambda *_a, **_k: False)
    monkeypatch.setattr(
        extract_burnin_traits, "get_default_reviewable_layers",
        lambda *_: [])
    monkeypatch.setattr(
        ExtractBurninTraits, "filter_burnins_defs",
        lambda *_: [
            {"name": "burnin", "filter": {"tags": []}, "top_left": "a"},
            {"name": "other", "filter": {"tags": []}, "top_left": "b"},
        ])
    monkeypatch.setattr(ExtractBurninTraits, "profiles", [{}])
    return _plugin(ExtractBurninTraits)


def test_extract_burnin_traits(tmp_path: Path, monkeypatch) -> None:
    """Burnin output replaces its source and keeps source traits."""
    source = _review_representation(tmp_path)
    (tmp_path / "review.mp4").write_bytes(b"")
    other = Representation(name="exr", traits=[
        FileLocation(file_path=tmp_path / "file.exr"),
        Tagged(tags=["review"]),
        Persistent(),
    ])
    instance = _instance([other, source])
    instance.data["families"] = ["review"]
    instance.context.data["project_settings"] = {}
    scripts = []

    _burnin_plugin(monkeypatch, scripts).process(instance)

    result = get_trait_representations(instance)
    # only linked burnin definition is used
    assert [r.name for r in result] == ["exr", "h264"]
    assert len(scripts) == 1
    script_data = scripts[0]
    assert script_data["ffmpeg_cmd"] == "ffmpeg -i input output"
    assert script_data["options"]["fps"] == 25.0
    assert script_data["values"] == {"top_left": "a"}
    # content 1001-1010, handles 2, slate frame before
    assert script_data["burnin_data"]["frame_start"] == 999
    assert script_data["burnin_data"]["slate_frame_start"] == 999
    burnin_repre = result[1]
    assert burnin_repre is not source
    assert burnin_repre.get_trait(FileLocation).file_path == (
        tmp_path / "reviewburnin.mp4")
    assert burnin_repre.get_trait(ColorManaged).color_space == "sRGB"
    assert burnin_repre.contains_trait(Persistent)
    assert burnin_repre.get_trait(FrameRanged).frame_start == 998
    assert burnin_repre.get_trait(Handles).frame_start_handle == 2
    # source input is removed
    assert not (tmp_path / "review.mp4").exists()


def test_extract_burnin_traits_sequence(tmp_path: Path, monkeypatch) -> None:
    """Burnins of sequence use frame pattern of the files."""
    paths = _frames(tmp_path, "review", range(1001, 1004))
    source = _sequence_representation(paths, ["review", "burnin"])
    source.add_trait(Variant(variant="png"))
    instance = _instance([source])
    instance.data["families"] = ["review"]
    instance.context.data["project_settings"] = {}
    scripts = []

    _burnin_plugin(monkeypatch, scripts).process(instance)

    result = get_trait_representations(instance)
    assert [r.name for r in result] == ["png_burnin", "png_other"]
    assert scripts[0]["input"].endswith("review.%04d.exr")
    assert scripts[0]["output"].endswith("review.%04dburnin.exr")
    assert scripts[0]["first_frame"] == 1001
    output = result[0]
    assert output.get_trait(Variant).variant == "png_burnin"
    assert output.get_trait(FileLocations).file_paths[0].file_path.name == (
        "review.1001burnin.exr")
    # frames of the source
    assert output.get_trait(FrameRanged).frame_rate == 25


def test_extract_review_slate_traits_update(tmp_path: Path) -> None:
    """Video with slate replaces files of its representation."""
    review = _review_representation(tmp_path)
    review.remove_trait(Slate)
    review.remove_trait(Persistent)
    review.get_trait(Tagged).tags.append("delete")
    review.get_trait(FileLocation).file_size = 1024

    ExtractReviewSlateTraits._update_representation(
        review, tmp_path / "review_slate.mp4")

    file_location = review.get_trait(FileLocation)
    assert file_location.file_path == tmp_path / "review_slate.mp4"
    assert file_location.file_size is None
    assert "delete" not in review.get_trait(Tagged).tags
    assert review.contains_trait(Persistent)
    # added slate frame is part of the frame range
    assert review.get_trait(FrameRanged).frame_start == 997
    assert review.get_trait(Slate).frames == 1


def test_extract_review_slate_traits_skips_without_slates(
        tmp_path: Path) -> None:
    """Representations are not changed without slate data."""
    review = _review_representation(tmp_path)
    instance = _instance([review])

    _plugin(ExtractReviewSlateTraits).process(instance)

    assert get_trait_representations(instance) == [review]
    assert review.get_trait(FileLocation).file_path == (
        tmp_path / "review.mp4")


def test_thumbnail_source_file_skips_slate(tmp_path: Path) -> None:
    """Thumbnail of sequence is from the middle of the content."""
    paths = _frames(tmp_path, "render", range(1000, 1011))
    source = _sequence_representation(paths, ["review"])
    source.add_trait(Slate(frames=1))
    plugin = _plugin(ExtractThumbnailTraits)

    path = plugin._get_source_file(
        source, str(tmp_path), ThumbnailDef(duration_split=0.5))

    # content 1001-1010
    assert Path(path).name == "render.1006.exr"


def test_extract_thumbnail_traits(tmp_path: Path, monkeypatch) -> None:
    """Thumbnail is added and thumbnail-only sources are removed."""
    (tmp_path / "file.exr").write_bytes(b"")
    source = Representation(name="exr", traits=[
        FileLocation(file_path=tmp_path / "file.exr"),
        Tagged(tags=["need_thumbnail", "delete"]),
        Variant(variant="main"),
        ColorManaged(color_space="ACEScg"),
    ])
    instance = _instance([source])
    instance.data.update({"productName": "renderMain", "review": True})
    instance.context.data.update({"project_settings": {}, "anatomy": None})

    def create_thumbnail(self, src_path, dst_path, *_args):
        Path(dst_path).write_bytes(b"")
        return True

    monkeypatch.setattr(ExtractThumbnailTraits, "profiles", [{}])
    monkeypatch.setattr(
        ExtractThumbnailTraits, "_get_config_from_profile",
        lambda *_: ThumbnailDef())
    monkeypatch.setattr(
        ExtractThumbnailTraits, "_create_thumbnail_ffmpeg", create_thumbnail)
    monkeypatch.setattr(
        extract_thumbnail_traits, "is_oiio_supported", lambda: False)
    monkeypatch.setattr(
        extract_thumbnail_traits, "get_default_reviewable_layers",
        lambda *_: [])
    _plugin(ExtractThumbnailTraits).process(instance)

    result = get_trait_representations(instance)
    assert [r.name for r in result] == ["thumbnail"]
    thumbnail = result[0]
    assert thumbnail.get_trait(Tagged).tags == ["thumbnail", "delete"]
    assert not thumbnail.contains_trait(Persistent)
    assert thumbnail.get_trait(Variant).variant == "main"
    assert thumbnail.get_trait(MimeType).mime_type == "image/jpeg"
    # thumbnail jpg is not in the colorspace of the source
    assert not thumbnail.contains_trait(ColorManaged)
    assert instance.data["thumbnailPath"] == str(
        thumbnail.get_trait(FileLocation).file_path)


@pytest.mark.parametrize("extension", ["png", ""])
def test_transcode_traits(tmp_path: Path, monkeypatch, extension) -> None:
    """Transcoded output is a copy of the source in target colorspace."""
    tmp_path = tmp_path / f"transcode_{extension}"
    paths = _frames(tmp_path / "src", "render", range(1001, 1004))
    source = _sequence_representation(paths, ["review"])
    instance = _instance([source])
    instance.context.data.update({
        "anatomy": None,
        "projectName": "test",
        "project_settings": {},
    })
    instance.data["families"] = []
    calls = []
    output_dir = tmp_path / "out"
    output_dir.mkdir()

    monkeypatch.setattr(
        extract_color_transcode_traits, "get_ocio_config_path",
        lambda *_a, **_k: "config.ocio")
    monkeypatch.setattr(
        extract_color_transcode_traits, "get_temp_dir",
        lambda **_: str(output_dir))
    monkeypatch.setattr(
        extract_color_transcode_traits, "get_default_reviewable_layers",
        lambda *_: [])
    monkeypatch.setattr(
        extract_color_transcode_traits, "oiio_color_convert",
        lambda **kwargs: calls.append(kwargs))
    plugin = _plugin(ExtractOIIOTranscodeTraits)
    plugin.profiles = [{}]
    profile = {
        "representation_names": [],
        "delete_original": True,
        "outputs": [{
            "name": "srgb",
            "extension": extension,
            "transcoding_type": "colorspace",
            "colorspace": "sRGB",
            "oiiotool_args": {"additional_command_args": []},
            "tags": ["review"],
            "custom_tags": ["custom"],
        }],
    }
    monkeypatch.setattr(
        extract_color_transcode_traits, "get_profile_for_instance",
        lambda *_: profile)

    plugin.main_process(instance)

    assert len(calls) == 1
    assert calls[0]["frames"] == "1001-1003"
    assert calls[0]["source_colorspace"] == "ACEScg"
    assert calls[0]["target_colorspace"] == "sRGB"
    ext = extension or "exr"
    assert calls[0]["output_path"].endswith(f"render.#.{ext}")

    result = get_trait_representations(instance)
    # original is deleted, it passed review to the output
    assert [r.name for r in result] == ["srgb"]
    output = result[0]
    assert output.get_trait(ColorManaged).color_space == "sRGB"
    assert output.get_trait(CustomTags).tags == ["custom"]
    assert output.get_trait(Tagged).tags == ["review"]
    assert output.contains_trait(Persistent)
    files = output.get_trait(FileLocations).file_paths
    assert files[0].file_path == output_dir / f"render.1001.{ext}"
    assert output.get_trait(FrameRanged).frame_rate == 25
    assert output.get_trait(StagingDirectory).path == output_dir
    if extension:
        assert output.get_trait(Variant).variant == "srgb"
    else:
        assert not output.contains_trait(Variant)
    assert "review" in instance.data["families"]
    # source is not changed by its outputs
    assert source.get_trait(ColorManaged).color_space == "ACEScg"
