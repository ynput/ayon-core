"""Tests for the trait manifest and checks of released traits."""
from __future__ import annotations

import copy
import json
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import ClassVar

import pytest
from ayon_core.pipeline.traits.manifest import (
    load_manifest,
    load_manifest_from_git,
    main,
    read_package_info,
    update_manifest,
)
from ayon_core.pipeline.traits.trait import TraitBase
from ayon_core.pipeline.traits.utils import get_core_traits

from .test_schema import (
    Sample,
    SampleBehaviorChanged,
    SampleMetaChanged,
    SampleSchemaChanged,
)

REPO_ROOT = Path(__file__).resolve().parents[5]
CORE_MANIFEST = REPO_ROOT / "server" / "traits.json"
SAMPLE_ID = Sample.id


@dataclass
class SampleV2(TraitBase):
    """Sample trait version 2."""

    name: ClassVar[str] = "Sample"
    description: ClassVar[str] = "Sample Trait"
    id: ClassVar[str] = "test.schema.Sample.v2"
    persistent: ClassVar[bool] = True
    width: int
    height: int


def _release(trait_classes: list) -> dict:
    manifest, report = update_manifest(trait_classes, "test", "1.0.0")
    assert not report.errors
    return manifest


def test_new_manifest() -> None:
    """Test manifest of unreleased traits."""
    manifest, report = update_manifest(
        [Sample, SampleV2], "test", "1.0.0", include_core_hash=True)
    assert not report.errors
    assert not report.warnings
    assert manifest["manifestVersion"] == 1
    assert manifest["addon"] == "test"
    assert manifest["coreHash"].startswith("sha256:")
    assert list(manifest["traits"]) == [SAMPLE_ID, SampleV2.id]

    entry = manifest["traits"][SAMPLE_ID]
    assert entry["definition"]["id"] == SAMPLE_ID
    assert set(entry["hashes"]) == {"schema", "behavior", "meta"}
    assert entry["introducedIn"] == "1.0.0"
    assert entry["behaviorChanges"] == []
    # Older version is deprecated
    assert entry["deprecated"] is True
    assert manifest["traits"][SampleV2.id]["deprecated"] is False
    # Manifest is JSON serializable
    json.dumps(manifest)


def test_unchanged_release() -> None:
    """Test released manifest stays the same if nothing changed."""
    released = _release([Sample])
    manifest, report = update_manifest(
        [Sample], "test", "1.1.0", current=released, released=released)
    assert not report.errors
    assert not report.warnings
    assert manifest == released


def test_schema_change_of_released_trait() -> None:
    """Test data model of a released trait cannot change."""
    released = _release([Sample])
    manifest, report = update_manifest(
        [SampleSchemaChanged], "test", "1.1.0",
        current=released, released=released)
    assert len(report.errors) == 1
    assert "data model" in report.errors[0]
    assert manifest["traits"][SAMPLE_ID] == released["traits"][SAMPLE_ID]

    # It can't be accepted as a behavior change either
    _, report = update_manifest(
        [SampleSchemaChanged], "test", "1.1.0",
        current=released, released=released,
        accepted_behavior_changes={SAMPLE_ID: "compatible"})
    assert report.errors


def test_behavior_change_of_released_trait() -> None:
    """Test code change of a released trait must be acknowledged."""
    released = _release([Sample])
    manifest, report = update_manifest(
        [SampleBehaviorChanged], "test", "1.1.0",
        current=released, released=released)
    assert len(report.errors) == 1
    assert "--accept-behavior-change" in report.errors[0]
    assert manifest["traits"][SAMPLE_ID] == released["traits"][SAMPLE_ID]

    accepted, report = update_manifest(
        [SampleBehaviorChanged], "test", "1.1.0",
        current=released, released=released,
        accepted_behavior_changes={SAMPLE_ID: "fix rounding"})
    assert not report.errors
    entry = accepted["traits"][SAMPLE_ID]
    released_hashes = released["traits"][SAMPLE_ID]["hashes"]
    assert entry["hashes"]["behavior"] != released_hashes["behavior"]
    assert entry["behaviorChanges"] == [{
        "from": released_hashes["behavior"],
        "to": entry["hashes"]["behavior"],
        "addonVersion": "1.1.0",
        "reason": "fix rounding",
    }]
    assert entry["introducedIn"] == "1.0.0"

    # Recorded acknowledgement is kept by following exports and checks
    manifest, report = update_manifest(
        [SampleBehaviorChanged], "test", "1.1.0",
        current=accepted, released=released)
    assert not report.errors
    assert manifest == accepted

    # Reverting the change removes the acknowledgement
    manifest, report = update_manifest(
        [Sample], "test", "1.1.0", current=accepted, released=released)
    assert not report.errors
    assert manifest == released


def test_meta_change_of_released_trait() -> None:
    """Test description change of a released trait is allowed."""
    released = _release([Sample])
    manifest, report = update_manifest(
        [SampleMetaChanged], "test", "1.1.0",
        current=released, released=released)
    assert not report.errors
    assert len(report.warnings) == 1
    entry = manifest["traits"][SAMPLE_ID]
    assert entry["definition"]["description"] == SampleMetaChanged.description
    assert entry["definition"]["ui"] == {"group": "Test"}


def test_unreleased_trait_can_change() -> None:
    """Test traits not in the released manifest can change."""
    current = _release([Sample])
    manifest, report = update_manifest(
        [SampleSchemaChanged], "test", "1.1.0",
        current=current, released={})
    assert not report.errors
    entry = manifest["traits"][SAMPLE_ID]
    assert entry["hashes"] != current["traits"][SAMPLE_ID]["hashes"]
    # Version which introduced the trait is kept
    assert entry["introducedIn"] == "1.0.0"


def test_current_manifest_is_released_without_base() -> None:
    """Test all traits are immutable if released manifest is not known."""
    current = _release([Sample])
    _, report = update_manifest(
        [SampleSchemaChanged], "test", "1.1.0", current=current)
    assert report.errors


def test_removed_trait_is_kept() -> None:
    """Test released trait is kept as deprecated when its class is gone."""
    released = _release([Sample])
    manifest, report = update_manifest(
        [SampleV2], "test", "2.0.0", current=released, released=released)
    assert not report.errors
    assert len(report.warnings) == 1
    entry = manifest["traits"][SAMPLE_ID]
    assert entry["deprecated"] is True
    assert entry["hashes"] == released["traits"][SAMPLE_ID]["hashes"]

    # Unreleased trait can be removed
    manifest, _ = update_manifest(
        [SampleV2], "test", "2.0.0", current=released, released={})
    assert SAMPLE_ID not in manifest["traits"]


def test_hand_edited_manifest() -> None:
    """Test hand edits of released entries are reverted by the export."""
    released = _release([Sample])
    edited = copy.deepcopy(released)
    edited["traits"][SAMPLE_ID]["hashes"]["schema"] = "sha256:edited"
    edited["traits"][SAMPLE_ID]["introducedIn"] = "0.1.0"
    manifest, report = update_manifest(
        [Sample], "test", "1.1.0", current=edited, released=released)
    assert not report.errors
    assert manifest == released
    assert manifest != edited


def test_unknown_accepted_trait() -> None:
    """Test accepting a change of unknown trait is an error."""
    _, report = update_manifest(
        [Sample], "test", "1.0.0",
        accepted_behavior_changes={"test.unknown.v1": "reason"})
    assert report.errors


def test_core_manifest_is_up_to_date() -> None:
    """Test manifest of ayon-core matches core traits."""
    current = load_manifest(str(CORE_MANIFEST))
    assert current is not None, "Run the export of the trait manifest."
    addon_name, addon_version = read_package_info(
        str(REPO_ROOT / "package.py"))
    manifest, report = update_manifest(
        get_core_traits(),
        addon_name,
        addon_version,
        current=current,
        include_core_hash=True,
    )
    assert not report.errors
    assert manifest == current, (
        "server/traits.json is not up to date, run: python -m"
        " ayon_core.pipeline.traits.manifest export"
        " --module ayon_core.pipeline.traits --core-hash"
    )


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def addon_repo(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Git repository of an addon with package.py."""
    tmp_path = tmp_path_factory.mktemp("addon")
    _git(tmp_path, "init", "-q")
    _git(tmp_path, "config", "user.email", "test@example.com")
    _git(tmp_path, "config", "user.name", "Test")
    _git(tmp_path, "config", "commit.gpgsign", "false")
    (tmp_path / "package.py").write_text(
        'name = "test"\nversion = "1.0.0"\n', encoding="utf-8")
    (tmp_path / "server").mkdir()
    _git(tmp_path, "add", "package.py")
    _git(tmp_path, "commit", "-q", "-m", "init")
    return tmp_path


def test_load_manifest_from_git(addon_repo: Path) -> None:
    """Test released manifest is read from a git revision."""
    path = addon_repo / "server" / "traits.json"
    # Not committed yet - nothing is released
    assert load_manifest_from_git(str(path), "HEAD") == {}

    path.write_text(json.dumps({"traits": {}}), encoding="utf-8")
    _git(addon_repo, "add", "server/traits.json")
    _git(addon_repo, "commit", "-q", "-m", "manifest")
    assert load_manifest_from_git(str(path), "HEAD") == {"traits": {}}

    with pytest.raises(RuntimeError):
        load_manifest_from_git(str(path), "missing-branch")


def test_cli(addon_repo: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test export and check commands."""
    monkeypatch.chdir(addon_repo)
    args = [
        "--module", "ayon_core.pipeline.traits.lifecycle",
        "--base-ref", "HEAD",
    ]
    output = addon_repo / "server" / "traits.json"

    assert main(["check", *args]) == 1
    assert main(["export", *args]) == 0
    manifest = json.loads(output.read_text(encoding="utf-8"))
    assert manifest["addon"] == "test"
    assert "ayon.lifecycle.Persistent.v1" in manifest["traits"]
    assert main(["check", *args]) == 0

    # Released hash edited by hand is caught
    _git(addon_repo, "add", "server/traits.json")
    _git(addon_repo, "commit", "-q", "-m", "release")
    entry = manifest["traits"]["ayon.lifecycle.Persistent.v1"]
    entry["hashes"]["behavior"] = "sha256:edited"
    output.write_text(json.dumps(manifest), encoding="utf-8")
    assert main(["check", *args]) == 1
    assert main(["export", *args]) == 0
    assert main(["check", *args]) == 0

    with pytest.raises(SystemExit):
        main(["export", *args, "--accept-behavior-change", "a.b.v1"])
