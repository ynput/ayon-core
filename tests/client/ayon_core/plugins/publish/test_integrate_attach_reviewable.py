import os

import pyblish.api
import pyblish.util
import pytest

from ayon_core.pipeline import PublishError
from ayon_core.plugins.publish.extract_burnin import ExtractBurnin
from ayon_core.plugins.publish.extract_review import is_sequence_output
from ayon_core.plugins.publish.integrate_attach_reviewable import (
    AttachReviewables,
    FinalizeAttachReviewables,
)


def _create_context(tmp_path):
    context = pyblish.api.Context()
    context.data.update({
        "cleanupFullPaths": [],
        "projectName": "test_project",
        "version": 99,
    })

    source_dir = tmp_path / "source"
    source_dir.mkdir(exist_ok=True)
    source_file = source_dir / "review.mov"
    source_file.write_bytes(b"review")

    source = context.create_instance("reviewMain")
    source.data.update({
        "active": True,
        "families": ["review"],
        "instance_id": "review-id",
        "publish_attributes": {
            "AttachReviewables": {"attach": ["target-a", "target-b"]}
        },
        "version": 2,
        "frameStart": 1001,
        "frameEnd": 1100,
        "handleStart": 10,
        "handleEnd": 12,
        "fps": 24,
        "slateFrames": {"*": "slate.png"},
        "anatomyData": {"product": {"name": "Review"}, "version": 2},
        "representations": [{
            "name": "review_mov",
            "files": "review.mov",
            "stagingDir": str(source_dir),
            "tags": ["review", "burnin", "slate-frame"],
        }],
    })

    target_a = context.create_instance("modelMain")
    target_a.data.update({
        "active": True,
        "families": ["model"],
        "instance_id": "target-a",
        "version": 5,
        "anatomyData": {"product": {"name": "Model"}, "version": 5},
    })

    target_b = context.create_instance("renderMain")
    target_b.data.update({
        "active": True,
        "families": ["render"],
        "instance_id": "target-b",
        "version": 8,
        "anatomyData": {"product": {"name": "Render"}, "version": 8},
    })
    return context, source, target_a, target_b, source_file


def test_attach_copies_files_and_representation_metadata(tmp_path):
    context, source, target_a, target_b, source_file = _create_context(
        tmp_path
    )

    AttachReviewables().process(source)

    assert source.data["representations"] == []
    assert source.data["integrate"] is False
    target_repres = [
        target_a.data["representations"][0],
        target_b.data["representations"][0],
    ]
    assert target_repres[0]["reviewData"]["frameStart"] == 1001
    assert target_repres[0]["reviewData"]["frameEnd"] == 1100
    assert target_repres[0]["slateFrames"] == {"*": "slate.png"}
    assert all(repre["files"] == "review.mov" for repre in target_repres)
    assert target_repres[0]["stagingDir"] != target_repres[1]["stagingDir"]
    assert all(
        os.path.isfile(os.path.join(repre["stagingDir"], repre["files"]))
        for repre in target_repres
    )
    assert all(
        repre["stagingDir"] in context.data["cleanupFullPaths"]
        for repre in target_repres
    )
    assert source_file.read_bytes() == b"review"


def test_attach_does_not_change_unattached_reviewable(tmp_path):
    context, source, _, _, _ = _create_context(tmp_path)
    source.data["publish_attributes"]["AttachReviewables"]["attach"] = []
    original_representations = source.data["representations"]

    AttachReviewables().process(source)

    assert source.data["representations"] is original_representations
    assert "integrate" not in source.data
    assert not context.data["cleanupFullPaths"]


def test_attach_reports_missing_source_file(tmp_path):
    context, source, _, _, source_file = _create_context(tmp_path)
    source_file.unlink()

    with pytest.raises(PublishError, match="source file is missing"):
        AttachReviewables().process(source)

    assert not context.data["cleanupFullPaths"]


def test_attach_keeps_non_review_source_representations(tmp_path):
    context, source, target_a, _, _ = _create_context(tmp_path)
    source.data["representations"].append({
        "name": "render_frames",
        "files": "render.exr",
        "tags": ["render"],
    })

    AttachReviewables().process(source)

    assert len(source.data["representations"]) == 1
    assert source.data["representations"][0]["name"] == "render_frames"
    assert "integrate" not in source.data
    assert len(target_a.data["representations"]) == 1
    assert context.data["cleanupFullPaths"]


def test_attach_rejects_review_representation_without_files(tmp_path):
    context, source, _, _, _ = _create_context(tmp_path)
    source.data["representations"][0]["files"] = []

    with pytest.raises(PublishError, match="without files"):
        AttachReviewables().process(source)

    assert source.data["representations"][0]["files"] == []
    assert not context.data["cleanupFullPaths"]


def test_finalize_attach_copies_late_thumbnail(tmp_path):
    context, source, target_a, _, source_file = _create_context(tmp_path)
    AttachReviewables().process(source)
    source.data["representations"].append({
        "name": "thumbnail",
        "files": source_file.name,
        "stagingDir": source_file.parent.as_posix(),
        "tags": ["thumbnail"],
    })

    FinalizeAttachReviewables().process(context)

    assert len(target_a.data["representations"]) == 2
    assert source.data["representations"] == []


def test_burnin_prefers_representation_frame_range():
    context = pyblish.api.Context()
    context.data.update({"version": 3, "handleStart": 1, "handleEnd": 2})
    instance = context.create_instance("target")
    instance.data.update({
        "families": ["model"],
        "version": 5,
        "comment": "",
        "anatomyData": {"version": 5},
        "frameStart": 1,
        "frameEnd": 2,
    })

    burnin_data, temp_data = ExtractBurnin().prepare_basic_data(
        instance,
        {
            "frameStart": 1001,
            "frameEnd": 1100,
            "handleStart": 10,
            "handleEnd": 12,
        },
    )

    assert burnin_data["version"] == 5
    assert temp_data["frame_start"] == 1001
    assert temp_data["frame_end"] == 1100
    assert temp_data["frame_start_handle"] == 991
    assert temp_data["frame_end_handle"] == 1112


def test_burnin_uses_review_metadata_but_target_version():
    context = pyblish.api.Context()
    context.data.update({"version": 3, "handleStart": 1, "handleEnd": 2})
    instance = context.create_instance("target")
    instance.data.update({
        "families": ["model"],
        "version": 5,
        "comment": "target comment",
        "anatomyData": {"version": 5, "source": "target"},
    })

    burnin_data, temp_data = ExtractBurnin().prepare_basic_data(
        instance,
        {
            "frameStart": 1001,
            "frameEnd": 1100,
            "handleStart": 10,
            "handleEnd": 12,
            "reviewData": {
                "frameStart": 2001,
                "frameEnd": 2100,
                "handleStart": 20,
                "handleEnd": 22,
                "anatomyData": {"source": "review"},
                "comment": "source comment",
            },
        },
    )

    assert burnin_data["version"] == 5
    assert burnin_data["source"] == "review"
    assert burnin_data["comment"] == "source comment"
    assert temp_data["frame_start"] == 2001
    assert temp_data["frame_end"] == 2100
    assert temp_data["frame_start_handle"] == 1981
    assert temp_data["frame_end_handle"] == 2122


@pytest.mark.parametrize(
    "files, input_ext, output_ext, expected",
    [
        (["frame.0001.exr"], "exr", "png", True),
        ("movie.mov", "mov", "png", True),
        ("frame.exr", "exr", "png", False),
    ],
)
def test_review_sequence_output_detection(
    files, input_ext, output_ext, expected
):
    assert is_sequence_output(
        files, input_ext, output_ext, {"png", "exr"}
    ) is expected


def test_extraction_is_shared_and_target_plugin_still_runs(tmp_path):
    context, source, target_a, target_b, _ = _create_context(tmp_path)
    processed = []

    class FakeExtractReview(pyblish.api.InstancePlugin):
        families = ["review"]
        order = pyblish.api.ExtractorOrder + 0.02

        def process(self, instance):
            context.data["review_extractions"] = (
                context.data.get("review_extractions", 0) + 1
            )

    class TargetPlugin(pyblish.api.InstancePlugin):
        order = pyblish.api.ExtractorOrder + 0.03

        def process(self, instance):
            processed.append((
                instance.name,
                len(instance.data.get("representations") or []),
            ))

    pyblish.util.publish(
        context,
        plugins=[FakeExtractReview, AttachReviewables, TargetPlugin],
    )

    assert not [
        result
        for result in context.data["results"]
        if result["error"] is not None
    ]
    assert context.data["review_extractions"] == 1
    assert (target_a.name, 1) in processed
    assert (target_b.name, 1) in processed
    assert (source.name, 0) in processed


def test_attachment_plugin_runs_before_burnin_and_without_family_filter():
    assert AttachReviewables.order < ExtractBurnin.order
    assert AttachReviewables.families == ["render", "review"]
    assert ExtractBurnin.families == ["*"]
