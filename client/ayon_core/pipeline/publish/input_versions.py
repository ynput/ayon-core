from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional, Sequence, Union


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
    input_versions: Optional[Sequence[Any]],
) -> list[SerializedInputVersion]:
    if not input_versions:
        return []

    return [
        InputVersion.from_value(input_version).to_json_data()
        for input_version in input_versions
    ]


def deserialize_input_versions(
    input_versions: Optional[Sequence[Any]],
) -> list[InputVersion]:
    if not input_versions:
        return []

    return [
        InputVersion.from_value(input_version)
        for input_version in input_versions
    ]
