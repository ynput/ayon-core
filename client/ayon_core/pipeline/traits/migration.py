"""Upgrade of trait data stored with representations on the server.

Trait data are stored under the trait id, which includes the version of
the trait (e.g. ``ayon.time.FrameRanged.v1``). When a new version of
a trait is created, data published before stay with the old id. They are
upgraded on load by ``upgrade()`` of the newer trait version (see
`Representation.from_dict()`), but the server and other consumers still
see the old version.

Functions in this module rewrite the stored data to the latest trait
versions, so stored data match the current trait definitions.

Traits that can't be restored (e.g. defined by an addon which is not
available) are kept unchanged.

"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from .publishing import prepare_for_json
from .representation import Representation
from .trait import UpgradableTraitError

log = logging.getLogger(__name__)

# Number of representations updated in one server request
_COMMIT_CHUNK_SIZE = 100


@dataclass
class TraitsUpgradeResult:
    """Result of upgrade of trait data of one representation.

    Attributes:
        traits (dict[str, Any]): Upgraded trait data.
        upgraded (dict[str, str]): New trait id by old trait id.
        skipped (dict[str, str]): Reason by trait id of traits that were
            kept unchanged although a newer version may exist.

    """

    traits: dict[str, Any]
    upgraded: dict[str, str] = field(default_factory=dict)
    skipped: dict[str, str] = field(default_factory=dict)

    @property
    def changed(self) -> bool:
        """Trait data changed."""
        return bool(self.upgraded)

    def get_patch_data(self) -> dict[str, Any]:
        """Trait data to patch the representation entity with.

        Server merges patched traits with the stored ones, data of old
        trait versions are removed by `None` values.

        Returns:
            dict[str, Any]: Upgraded traits and old trait ids set to None.

        """
        patch_data: dict[str, Any] = dict.fromkeys(self.upgraded)
        for new_id in self.upgraded.values():
            patch_data[new_id] = self.traits[new_id]
        return patch_data


@dataclass
class TraitsUpgradeReport:
    """Summary of upgrade of representation traits in a project.

    Attributes:
        project_name (str): Project name.
        dry_run (bool): Data were not written to the server.
        checked (int): Number of representations with traits.
        updated (list[str]): Ids of upgraded representations.
        upgraded_traits (dict[str, int]): Count of upgrades by
            ``"<old id> -> <new id>"``.
        skipped (dict[str, dict[str, str]]): Skipped traits with reason
            by representation id.

    """

    project_name: str
    dry_run: bool = False
    checked: int = 0
    updated: list[str] = field(default_factory=list)
    upgraded_traits: dict[str, int] = field(default_factory=dict)
    skipped: dict[str, dict[str, str]] = field(default_factory=dict)

    def summary(self) -> str:
        """Human readable summary of the upgrade."""
        action = "would be upgraded" if self.dry_run else "upgraded"
        lines = [
            f"Project '{self.project_name}': {len(self.updated)} of"
            f" {self.checked} representations with traits {action}.",
        ]
        lines.extend(
            f"    {label}: {count}"
            for label, count in sorted(self.upgraded_traits.items())
        )
        if self.skipped:
            lines.append(
                f"Traits of {len(self.skipped)} representations"
                " were skipped:"
            )
            for repre_id, reasons in self.skipped.items():
                lines.extend(
                    f"    {repre_id} {trait_id}: {reason}"
                    for trait_id, reason in reasons.items()
                )
        return "\n".join(lines)


def upgrade_traits_data(traits_data: dict[str, Any]) -> TraitsUpgradeResult:
    """Upgrade trait data to the latest versions of the traits.

    Only data of older trait versions are changed, data of current
    versions and of traits that can't be restored are kept as they are.

    Args:
        traits_data (dict[str, Any]): Trait data by trait id, as stored
            on the representation entity.

    Returns:
        TraitsUpgradeResult: Upgraded data.

    """
    result = TraitsUpgradeResult(traits={})
    upgraded_data: dict[str, Any] = {}
    for trait_id, trait_data in traits_data.items():
        try:
            Representation.get_trait_class_by_trait_id(trait_id)
        except UpgradableTraitError as exc:
            try:
                trait = exc.trait.upgrade(trait_data)
            except Exception as upgrade_exc:  # noqa: BLE001
                result.skipped[trait_id] = f"upgrade failed: {upgrade_exc}"
                result.traits[trait_id] = trait_data
                continue
            new_id = str(trait.id)
            upgraded_data[new_id] = prepare_for_json(
                trait.as_persistent_dict())
            result.upgraded[trait_id] = new_id
            continue
        except Exception as exc:  # noqa: BLE001
            result.skipped[trait_id] = str(exc)
        result.traits[trait_id] = trait_data

    for new_id, trait_data in upgraded_data.items():
        if new_id not in result.traits:
            result.traits[new_id] = trait_data
            continue
        # Data of the new version are already stored - keep them and
        #   the old data as they are
        for old_id, upgraded_id in list(result.upgraded.items()):
            if upgraded_id != new_id:
                continue
            result.upgraded.pop(old_id)
            result.skipped[old_id] = f"data of {new_id} already exist"
            result.traits[old_id] = traits_data[old_id]
    return result


def upgrade_representation_traits(
        project_name: str,
        version_ids: Optional[Iterable[str]] = None,
        dry_run: bool = False,
) -> TraitsUpgradeReport:
    """Upgrade trait data of representations on the server.

    Args:
        project_name (str): Project name.
        version_ids (Optional[Iterable[str]]): Upgrade only
            representations of these versions. All representations of
            the project are upgraded if not passed.
        dry_run (bool): Only report what would be upgraded.

    Returns:
        TraitsUpgradeReport: Summary of the upgrade.

    """
    import ayon_api  # noqa: PLC0415
    from ayon_api.operations import OperationsSession  # noqa: PLC0415

    report = TraitsUpgradeReport(project_name=project_name, dry_run=dry_run)
    if version_ids is not None:
        version_ids = set(version_ids)
        if not version_ids:
            return report

    repre_entities = ayon_api.get_representations(
        project_name,
        version_ids=version_ids,
        active=None,
        fields={"id", "traits"},
    )
    op_session = OperationsSession()
    pending = 0
    for repre_entity in repre_entities:
        traits_data = repre_entity.get("traits")
        if isinstance(traits_data, str):
            traits_data = json.loads(traits_data)
        if not traits_data:
            continue

        report.checked += 1
        repre_id = repre_entity["id"]
        result = upgrade_traits_data(traits_data)
        if result.skipped:
            report.skipped[repre_id] = result.skipped
        if not result.changed:
            continue

        report.updated.append(repre_id)
        for old_id, new_id in result.upgraded.items():
            label = f"{old_id} -> {new_id}"
            report.upgraded_traits[label] = (
                report.upgraded_traits.get(label, 0) + 1)
        if dry_run:
            continue

        op_session.update_entity(
            project_name,
            "representation",
            repre_id,
            {"traits": result.get_patch_data()},
        )
        pending += 1
        if pending >= _COMMIT_CHUNK_SIZE:
            op_session.commit()
            pending = 0

    if pending:
        op_session.commit()
    return report
