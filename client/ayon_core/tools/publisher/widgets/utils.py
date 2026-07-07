from __future__ import annotations

from typing import Literal

from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend


class PreCreateButtonCallback:
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        key: str,
        plugin_id: str
    ) -> None:
        self.controller = controller
        self.key = key
        self.plugin_id = plugin_id

    def __call__(self) -> None:
        self.controller.trigger_pre_create_button_callback(
            self.plugin_id,
            self.key,
        )


class CreateButtonCallback:
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        key: str,
        instance_ids: list[str],
    ) -> None:
        self.controller = controller
        self.key = key
        self.instance_ids = instance_ids

    def __call__(self) -> None:
        self.controller.trigger_create_button_callback(
            self.key,
            self.instance_ids,
        )


class PublishButtonCallback:
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        key: str,
        plugin_id: str,
        instance_ids: list[str | None],
    ) -> None:
        self.plugin_id = plugin_id
        self.key = key
        self.instance_ids = instance_ids

        self.controller = controller

    def __call__(self) -> None:
        self.controller.trigger_publish_button_callback(
            self.plugin_id,
            self.key,
            self.instance_ids,
        )
