"""Trait manifest exposing trait definitions to the AYON server.

The manifest is a JSON file shipped with the server part of an addon
(``server/traits.json``). The server reads it and serves definitions
of all installed addon versions at ``/api/traits``.

Released trait versions are immutable. Every entry carries hashes of
the trait (see `ayon_core.pipeline.traits.schema`) and the manifest is
compared with the released manifest (the one on the base branch):

    * ``schema`` change is an error. Create a new trait version instead.
    * ``behavior`` change is an error unless it is acknowledged with
      a reason (``--accept-behavior-change``), which is recorded
      in ``behaviorChanges`` of the entry.
    * ``meta`` change (descriptions, UI hints) is allowed with
      a warning.

Entries are never removed. An entry is marked as deprecated if a newer
version of the trait exists or its class was removed.

Usage::

    python -m ayon_core.pipeline.traits.manifest export \\
        --module ayon_core.pipeline.traits \\
        --output server/traits.json \\
        --base-ref origin/develop

    python -m ayon_core.pipeline.traits.manifest check \\
        --module ayon_core.pipeline.traits \\
        --output server/traits.json \\
        --base-ref origin/develop

"""
from __future__ import annotations

import argparse
import ast
import copy
import json
import logging
import os
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .schema import (
    collect_trait_classes,
    get_core_hash,
    get_trait_definition,
    get_trait_hashes,
)
from .trait import TraitBase

MANIFEST_VERSION = 1
MANIFEST_FILENAME = "traits.json"

log = logging.getLogger(__name__)


@dataclass
class ManifestReport:
    """Problems found while updating the manifest.

    Attributes:
        errors (list[str]): Changes of released traits which are not
            allowed. Manifest must not be written if there are any.
        warnings (list[str]): Allowed changes worth reviewing.

    """

    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _get_entries(manifest: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not manifest:
        return {}
    return manifest.get("traits") or {}


def _get_hashes(entry: Optional[dict[str, Any]]) -> dict[str, Any]:
    if not entry:
        return {}
    return entry.get("hashes") or {}


def _get_version(entry: dict[str, Any]) -> int:
    version = (entry.get("definition") or {}).get("version")
    return version if isinstance(version, int) else 0


def _update_released_entry(  # noqa: PLR0913, PLR0917
        trait_id: str,
        definition: dict[str, Any],
        hashes: dict[str, str],
        released: dict[str, Any],
        current: Optional[dict[str, Any]],
        addon_version: str,
        accepted_reason: Optional[str],
        report: ManifestReport) -> dict[str, Any]:
    """Create entry of a released trait, validating changes."""
    released_hashes = _get_hashes(released)
    if hashes["schema"] != released_hashes.get("schema"):
        report.errors.append(
            f"{trait_id}: data model of a released trait changed."
            " Create a new version of the trait instead."
        )
        return copy.deepcopy(released)

    released_changes = list(released.get("behaviorChanges") or [])
    recorded_changes = []
    if current:
        recorded_changes = list(
            current.get("behaviorChanges") or []
        )[len(released_changes):]

    behavior_changes = released_changes
    released_behavior = released_hashes.get("behavior")
    if hashes["behavior"] != released_behavior:
        if accepted_reason:
            behavior_changes = released_changes + [
                change for change in recorded_changes
                if change.get("to") != hashes["behavior"]
            ]
            previous = (
                behavior_changes[-1]["to"]
                if len(behavior_changes) > len(released_changes)
                else released_behavior
            )
            behavior_changes.append({
                "from": previous,
                "to": hashes["behavior"],
                "addonVersion": addon_version,
                "reason": accepted_reason,
            })
        elif (
            recorded_changes
            and recorded_changes[-1].get("to") == hashes["behavior"]
        ):
            behavior_changes = released_changes + recorded_changes
        else:
            report.errors.append(
                f"{trait_id}: code of a released trait changed. If the"
                " data are still compatible, acknowledge the change with"
                f" '--accept-behavior-change {trait_id} --reason ...',"
                " otherwise create a new version of the trait."
            )
            return copy.deepcopy(released)
    elif accepted_reason:
        report.warnings.append(
            f"{trait_id}: code did not change, nothing to accept."
        )

    if hashes["meta"] != released_hashes.get("meta"):
        report.warnings.append(
            f"{trait_id}: description or UI hints of a released trait"
            " changed."
        )

    return {
        "definition": definition,
        "hashes": hashes,
        "introducedIn": released.get("introducedIn"),
        "deprecated": False,
        "behaviorChanges": behavior_changes,
    }


def update_manifest(  # noqa: C901, PLR0913
        trait_classes: Iterable[type[TraitBase]],
        addon_name: str,
        addon_version: str,
        current: Optional[dict[str, Any]] = None,
        released: Optional[dict[str, Any]] = None,
        accepted_behavior_changes: Optional[dict[str, str]] = None,
        include_core_hash: bool = False,
) -> tuple[dict[str, Any], ManifestReport]:
    """Create manifest for trait classes.

    Args:
        trait_classes (Iterable[type[TraitBase]]): Traits of the addon.
        addon_name (str): Addon name.
        addon_version (str): Addon version, stored as ``introducedIn``
            of new trait versions.
        current (Optional[dict[str, Any]]): Manifest currently stored
            in the addon, it keeps acknowledged behavior changes and
            ``introducedIn`` of unreleased traits.
        released (Optional[dict[str, Any]]): Released manifest (from
            the base branch). Traits in it are immutable, other traits
            can still change. If not passed, all traits in `current`
            are handled as released.
        accepted_behavior_changes (Optional[dict[str, str]]): Reasons
            of acknowledged behavior changes by trait id.
        include_core_hash (bool): Add ``coreHash`` (hash of `TraitBase`),
            used for the manifest of ayon-core.

    Returns:
        tuple[dict[str, Any], ManifestReport]: Manifest and report.
            Released entries with errors are kept unchanged.

    """
    if released is None:
        released = current
    current_entries = _get_entries(current)
    released_entries = _get_entries(released)
    accepted = dict(accepted_behavior_changes or {})
    report = ManifestReport()

    entries: dict[str, dict[str, Any]] = {}
    for trait_class in trait_classes:
        trait_id = str(trait_class.id)
        if trait_id in entries:
            report.errors.append(f"{trait_id}: defined more than once.")
            continue
        definition = get_trait_definition(trait_class)
        hashes = get_trait_hashes(trait_class, definition)
        accepted_reason = accepted.pop(trait_id, None)
        released_entry = released_entries.get(trait_id)
        current_entry = current_entries.get(trait_id)
        if released_entry is not None:
            entries[trait_id] = _update_released_entry(
                trait_id,
                definition,
                hashes,
                released_entry,
                current_entry,
                addon_version,
                accepted_reason,
                report,
            )
            continue

        if accepted_reason:
            report.warnings.append(
                f"{trait_id}: trait is not released, nothing to accept."
            )
        introduced_in = addon_version
        if current_entry and current_entry.get("introducedIn"):
            introduced_in = current_entry["introducedIn"]
        entries[trait_id] = {
            "definition": definition,
            "hashes": hashes,
            "introducedIn": introduced_in,
            "deprecated": False,
            "behaviorChanges": [],
        }

    for trait_id in accepted:
        report.errors.append(
            f"{trait_id}: unknown trait in accepted behavior changes."
        )

    # Released traits are never removed - published representations
    # may still use them.
    removed = set()
    for trait_id, entry in released_entries.items():
        if trait_id in entries:
            continue
        report.warnings.append(
            f"{trait_id}: trait class not found, the trait is kept"
            " as deprecated."
        )
        entries[trait_id] = copy.deepcopy(entry)
        removed.add(trait_id)

    latest_versions: dict[str, int] = {}
    for entry in entries.values():
        versionless_id = str((entry.get("definition") or {}).get(
            "versionlessId"))
        version = _get_version(entry)
        if version > latest_versions.get(versionless_id, -1):
            latest_versions[versionless_id] = version

    for trait_id, entry in entries.items():
        versionless_id = str((entry.get("definition") or {}).get(
            "versionlessId"))
        entry["deprecated"] = (
            trait_id in removed
            or _get_version(entry) < latest_versions[versionless_id]
        )

    manifest: dict[str, Any] = {
        "manifestVersion": MANIFEST_VERSION,
        "addon": addon_name,
    }
    if include_core_hash:
        core_hash = get_core_hash()
        released_core_hash = (released or {}).get("coreHash")
        if released_core_hash and released_core_hash != core_hash:
            report.warnings.append(
                "Code of TraitBase changed. It affects every trait,"
                " make sure stored trait data can still be loaded."
            )
        manifest["coreHash"] = core_hash
    manifest["traits"] = {
        trait_id: entries[trait_id] for trait_id in sorted(entries)
    }
    return manifest, report


def load_manifest(path: str) -> Optional[dict[str, Any]]:
    """Load manifest from file.

    Args:
        path (str): Path to the manifest.

    Returns:
        Optional[dict[str, Any]]: Manifest or None if the file
            does not exist.

    """
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as stream:
        return json.load(stream)


def load_manifest_from_git(path: str, ref: str) -> dict[str, Any]:
    """Load manifest from a git revision.

    Args:
        path (str): Path to the manifest in the working tree.
        ref (str): Git revision, e.g. ``origin/develop``.

    Returns:
        dict[str, Any]: Manifest, empty if the file is not in
            the revision.

    Raises:
        RuntimeError: If the revision does not exist.

    """
    dirpath, filename = os.path.split(os.path.abspath(path))
    verify = subprocess.run(
        ["git", "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}"],
        cwd=dirpath,
        capture_output=True,
        text=True,
        check=False,
    )
    if verify.returncode != 0:
        msg = f"Git revision '{ref}' not found."
        raise RuntimeError(msg)

    result = subprocess.run(
        ["git", "show", f"{ref}:./{filename}"],
        cwd=dirpath,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode != 0:
        # The manifest is not in the revision yet - nothing is released
        return {}
    return json.loads(result.stdout)


def dump_manifest(manifest: dict[str, Any]) -> str:
    """Serialize manifest to text stored in the file.

    Args:
        manifest (dict[str, Any]): Manifest.

    Returns:
        str: JSON text.

    """
    return json.dumps(manifest, indent=2, ensure_ascii=False) + "\n"


def write_manifest(path: str, manifest: dict[str, Any]) -> None:
    """Write manifest to file.

    Args:
        path (str): Path to the manifest.
        manifest (dict[str, Any]): Manifest.

    """
    dirpath = os.path.dirname(os.path.abspath(path))
    os.makedirs(dirpath, exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(dump_manifest(manifest))


def read_package_info(path: str) -> tuple[Optional[str], Optional[str]]:
    """Read addon name and version from ``package.py``.

    Args:
        path (str): Path to ``package.py``.

    Returns:
        tuple[Optional[str], Optional[str]]: Addon name and version.

    """
    if not os.path.exists(path):
        return None, None
    with open(path, encoding="utf-8") as stream:
        tree = ast.parse(stream.read())
    values: dict[str, Any] = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (
                isinstance(target, ast.Name)
                and target.id in ("name", "version")
                and isinstance(node.value, ast.Constant)
                and isinstance(node.value.value, str)
            ):
                values[target.id] = node.value.value
    return values.get("name"), values.get("version")


def _parse_args(argv: Optional[list[str]]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="python -m ayon_core.pipeline.traits.manifest",
        description="Export trait definitions to the addon trait manifest.",
    )
    parser.add_argument(
        "command",
        choices=("export", "check"),
        help=(
            "'export' writes the manifest, 'check' fails if the manifest"
            " is not up to date or released traits changed."
        ),
    )
    parser.add_argument(
        "--module",
        dest="modules",
        action="append",
        required=True,
        help="Module or package with trait classes, can be repeated.",
    )
    parser.add_argument(
        "--output",
        default=os.path.join("server", MANIFEST_FILENAME),
        help="Path to the manifest (default: server/traits.json).",
    )
    parser.add_argument(
        "--package",
        default="package.py",
        help="Path to package.py with addon name and version.",
    )
    parser.add_argument("--addon-name", help="Overrides package.py name.")
    parser.add_argument(
        "--addon-version", help="Overrides package.py version.")
    parser.add_argument(
        "--base-ref",
        help=(
            "Git revision with the released manifest, e.g. origin/develop."
            " Without it all traits in the current manifest are handled"
            " as released."
        ),
    )
    parser.add_argument(
        "--accept-behavior-change",
        dest="accepted",
        action="append",
        default=[],
        metavar="TRAIT_ID",
        help="Acknowledge compatible code change of a released trait.",
    )
    parser.add_argument(
        "--reason",
        help="Reason of acknowledged behavior changes.",
    )
    parser.add_argument(
        "--core-hash",
        action="store_true",
        help="Store hash of TraitBase (manifest of ayon-core).",
    )
    args = parser.parse_args(argv)
    if args.accepted and not args.reason:
        parser.error("--reason is required with --accept-behavior-change")
    if args.accepted and args.command == "check":
        parser.error("--accept-behavior-change can be used only with export")
    return args


def main(argv: Optional[list[str]] = None) -> int:
    """Run manifest command line interface.

    Args:
        argv (Optional[list[str]]): Arguments, `sys.argv` if not passed.

    Returns:
        int: Exit code.

    """
    logging.basicConfig(
        level=logging.INFO, format="%(levelname)s: %(message)s")
    args = _parse_args(argv)

    package_name, package_version = read_package_info(args.package)
    addon_name = args.addon_name or package_name
    addon_version = args.addon_version or package_version
    if not addon_name or not addon_version:
        log.error(
            "Addon name and version are not known. Use --package"
            " or --addon-name and --addon-version."
        )
        return 2

    current = load_manifest(args.output)
    released = None
    if args.base_ref:
        try:
            released = load_manifest_from_git(args.output, args.base_ref)
        except RuntimeError as exc:
            log.error(str(exc))
            return 2

    trait_classes = collect_trait_classes(args.modules)
    manifest, report = update_manifest(
        trait_classes,
        addon_name,
        addon_version,
        current=current,
        released=released,
        accepted_behavior_changes={
            trait_id: args.reason for trait_id in args.accepted
        },
        include_core_hash=args.core_hash,
    )
    for warning in report.warnings:
        log.warning(warning)
    for error in report.errors:
        log.error(error)
    if report.errors:
        return 1

    if args.command == "check":
        if current != manifest:
            log.error(
                f"{args.output} is not up to date. Run the export command"
                " and commit the result."
            )
            return 1
        log.info(f"{args.output} is up to date ({len(trait_classes)} traits).")
        return 0

    if current == manifest:
        log.info(f"{args.output} is up to date ({len(trait_classes)} traits).")
        return 0
    write_manifest(args.output, manifest)
    log.info(f"Written {args.output} ({len(trait_classes)} traits).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
