from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import Any, Optional, Iterable, Union

import ayon_api

SerializedInputVersion = Union[str, dict[str, Any]]


@dataclass(frozen=True)
class InputVersion:
    """Input version used for dependency links.

    The version id always points to the active real version.
    When the source was a hero version, the original hero metadata is stored
    separately so it can be persisted to farm metadata JSON and link data.
    """

    version_id: str
    hero: bool = False
    hero_version_id: Optional[str] = None

    @property
    def data(self) -> dict[str, Any]:
        output = {}
        if self.hero:
            output["hero"] = True
        if self.hero_version_id:
            output["hero_version_id"] = self.hero_version_id
        return output

    def to_json_data(self) -> SerializedInputVersion:
        data = self.data
        if not data:
            return self.version_id
        return {
            "version_id": self.version_id,
            "data": data,
        }

    @classmethod
    def from_value(
        cls,
        value: Union["InputVersion", SerializedInputVersion, str]
    ) -> "InputVersion":
        if isinstance(value, cls):
            return value

        if isinstance(value, dict):
            version_id = (
                value.get("version_id")
                or value.get("versionId")
                or value.get("id")
            )
            if not version_id:
                raise ValueError(
                    "Serialized input version is missing 'version_id'."
                )

            data = value.get("data") or {}
            hero = value.get("hero")
            hero_version_id = value.get("hero_version_id")
            if isinstance(data, dict):
                if hero is None:
                    hero = data.get("hero")
                if hero_version_id is None:
                    hero_version_id = data.get("hero_version_id")

            hero = bool(hero or hero_version_id)
            if hero_version_id is not None:
                hero_version_id = str(hero_version_id)

            return cls(
                version_id=str(version_id),
                hero=hero,
                hero_version_id=hero_version_id,
            )

        return cls(version_id=str(value))


def serialize_input_versions(
    input_versions: Optional[Iterable[Any]],
) -> list[SerializedInputVersion]:
    if not input_versions:
        return []

    return [
        InputVersion.from_value(input_version).to_json_data()
        for input_version in input_versions
    ]


def deserialize_input_versions(
    input_versions: Optional[Iterable[Any]],
) -> list[InputVersion]:
    if not input_versions:
        return []

    return [
        InputVersion.from_value(input_version)
        for input_version in input_versions
    ]


def _hero_versions_to_versions(
    version_info_by_version_id: dict[str, InputVersion],
    project_name: str,
    log: logging.Logger,
) -> dict[str, InputVersion]:
    """Remap hero versions to their 'real' version ids"""
    # Get all hero version ids among the versions
    hero_versions: list[dict] = list(ayon_api.get_hero_versions(
        project_name=project_name,
        version_ids=set(version_info_by_version_id.keys()),
        fields={"id", "productId"},
    ))
    if not hero_versions:
        return version_info_by_version_id

    product_ids = {hv["productId"] for hv in hero_versions}
    hero_version_ids: set[str] = {hv["id"] for hv in hero_versions}

    # TODO: When backend supports it filter directly to only versions
    #  where hero version id matches our list of versions or skip those
    #  that have no hero version id
    versions = ayon_api.get_versions(
        project_name,
        product_ids=product_ids,
        fields={"id", "heroVersionId"}
    )
    # Mapping from hero version id to real version id
    real_version_id_by_hero_version_id: dict[str, str] = {
        v["heroVersionId"]: v["id"] for v in versions
        # Disregard versions with irrelevant hero version id
        if v["heroVersionId"] in hero_version_ids
    }
    log.debug(
        f"Hero version to version id map: {real_version_id_by_hero_version_id}"
    )

    for hero_version_id in hero_version_ids:
        real_version_id: str = real_version_id_by_hero_version_id.get(
            hero_version_id
        )
        if not real_version_id:
            log.debug(
                "Could not find real version for hero version: %s.",
                hero_version_id,
            )
            continue

        version_info_by_version_id[hero_version_id] = (
            InputVersion(
                version_id=real_version_id,
                hero=True,
                hero_version_id=hero_version_id,
            )
        )

    return version_info_by_version_id


def version_ids_to_input_versions(
    project_name: str,
    version_ids: Iterable[str],
    log: logging.Logger,
) -> dict[str, InputVersion]:
    version_info_by_version_id = {
        version_id: InputVersion(version_id=version_id)
        for version_id in version_ids
    }

    # Replace hero versions with their real versions with metadata preserving
    # info about the hero version ids
    version_info_by_version_id = _hero_versions_to_versions(
        version_info_by_version_id,
        project_name,
        log=log,
    )
    return version_info_by_version_id
