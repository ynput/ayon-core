import copy
import os

import pyblish.api

import ayon_core.plugins.publish.prepare_attach_reviewables as prepare
from ayon_core.plugins.publish.extract_burnin import ExtractBurnin
from ayon_core.plugins.publish.integrate_attach_reviewable import (
    AttachReviewables,
)
from ayon_core.plugins.publish.prepare_attach_reviewables import (
    ATTACH_TARGET_ID_KEY,
    PrepareAttachReviewables,
)


def _create_context():
    context = pyblish.api.Context()
    context.data["projectName"] = "test_project"

    review_instance = context.create_instance("reviewMain")
    review_instance.data.update(
        {
            "active": True,
            "families": ["review"],
            "instance_id": "review-id",
            "publish_attributes": {
                "AttachReviewables": {
                    "attach": ["target-a", "target-b"],
                }
            },
            "version": 2,
            "anatomyData": {
                "product": {"name": "Review"},
                "version": 2,
            },
            "representations": [
                {
                    "name": "review_mov",
                    "files": "review.mov",
                    "stagingDir": "/tmp/review",
                    "tags": ["review", "burnin"],
                }
            ],
        }
    )

    target_a = context.create_instance("modelMain")
    target_a.data.update(
        {
            "active": True,
            "instance_id": "target-a",
            "version": 5,
            "anatomyData": {
                "product": {"name": "Model"},
                "version": 5,
            },
        }
    )

    target_b = context.create_instance("renderMain")
    target_b.data.update(
        {
            "active": True,
            "instance_id": "target-b",
            "version": 8,
            "anatomyData": {
                "product": {"name": "Render"},
                "version": 8,
            },
        }
    )

    return context, review_instance, target_a, target_b


def test_prepare_creates_one_instance_per_target():
    context, review_instance, target_a, target_b = _create_context()

    PrepareAttachReviewables().process(context)

    prepared_instances = [
        instance
        for instance in context
        if instance.data.get(ATTACH_TARGET_ID_KEY)
    ]
    assert len(prepared_instances) == 2
    assert review_instance.data["publish"] is False

    prepared_by_target = {
        instance.data[ATTACH_TARGET_ID_KEY]: instance
        for instance in prepared_instances
    }
    assert prepared_by_target["target-a"].data["version"] == 5
    assert (
        prepared_by_target["target-a"].data["anatomyData"]["version"] == 5
    )
    assert prepared_by_target["target-b"].data["version"] == 8
    assert (
        prepared_by_target["target-b"].data["anatomyData"]["version"] == 8
    )
    assert all(
        instance.data["integrate"] is False
        for instance in prepared_instances
    )
    assert all(
        instance.data["publish_attributes"] == {}
        for instance in prepared_instances
    )
    assert len({
        instance.data["instance_id"] for instance in prepared_instances
    }) == 2
    assert target_a.data.get("representations") is None
    assert target_b.data.get("representations") is None


def test_prepare_deep_copies_representations():
    context, _, _, _ = _create_context()

    PrepareAttachReviewables().process(context)

    prepared_instances = [
        instance
        for instance in context
        if instance.data.get(ATTACH_TARGET_ID_KEY)
    ]
    prepared_instances[0].data["representations"][0]["tags"].append(
        "target-specific"
    )

    assert "target-specific" not in prepared_instances[1].data[
        "representations"
    ][0]["tags"]


def test_attach_prepared_instance_to_target():
    context, _, target_a, _ = _create_context()

    PrepareAttachReviewables().process(context)
    prepared_instance = next(
        instance
        for instance in context
        if instance.data.get(ATTACH_TARGET_ID_KEY) == "target-a"
    )
    expected_representations = copy.deepcopy(
        prepared_instance.data["representations"]
    )

    AttachReviewables().process(prepared_instance)

    assert target_a.data["representations"] == expected_representations
    assert prepared_instance.data["integrate"] is False


def test_burnin_uses_target_version_when_review_is_stale():
    context, _, _, target_b = _create_context()
    context.data["version"] = 2

    PrepareAttachReviewables().process(context)
    prepared_instance = next(
        instance
        for instance in context
        if instance.data.get(ATTACH_TARGET_ID_KEY) == "target-b"
    )
    prepared_instance.data.update(
        {
            "comment": "",
            "frameStart": 1,
            "frameEnd": 1,
            "version": 2,
        }
    )

    burnin_data, _ = ExtractBurnin().prepare_basic_data(prepared_instance)

    assert target_b.data["version"] == 8
    assert burnin_data["version"] == 8


def test_prepare_copies_files_to_unique_staging_dirs(tmp_path, monkeypatch):
    context, _, _, _ = _create_context()
    source_file = tmp_path / "review.mov"
    source_file.write_text("review")
    context.data["cleanupFullPaths"] = []
    context[0].data["representations"] = [
        {
            "name": "review_mov",
            "files": source_file.name,
            "stagingDir": str(tmp_path),
        }
    ]

    staging_dirs = iter(
        [str(tmp_path / "prepared-a"), str(tmp_path / "prepared-b")]
    )
    monkeypatch.setattr(
        prepare,
        "get_temp_dir",
        lambda **kwargs: next(staging_dirs),
    )

    PrepareAttachReviewables().process(context)

    prepared_instances = [
        instance
        for instance in context
        if instance.data.get(ATTACH_TARGET_ID_KEY)
    ]
    prepared_paths = [
        os.path.join(
            instance.data["representations"][0]["stagingDir"],
            instance.data["representations"][0]["files"],
        )
        for instance in prepared_instances
    ]

    assert prepared_paths == [
        str(tmp_path / "prepared-a" / "review.mov"),
        str(tmp_path / "prepared-b" / "review.mov"),
    ]
    assert all(os.path.isfile(path) for path in prepared_paths)
    assert prepared_paths[0] != prepared_paths[1]
    assert context.data["cleanupFullPaths"] == prepared_paths
