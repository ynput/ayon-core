from __future__ import annotations

from typing import Literal

from ayon_core.tools.publisher.abstract import AbstractPublisherFrontend


class ButtonCallback:
    def __init__(
        self,
        controller: AbstractPublisherFrontend,
        callback_source: Literal["precreate", "create", "publish"],
        key: str,
        plugin_id: str | None,
        instance_ids: list[str | None],
    ) -> None:
        self.callback_source = callback_source
        self.plugin_id = plugin_id
        self.key = key
        self.instance_ids = instance_ids

        self._controller = controller

    def __call__(self) -> None:
        self._controller.trigger_button_attribute_callback(
            self.callback_source,
            self.plugin_id,
            self.key,
            self.instance_ids,
        )
