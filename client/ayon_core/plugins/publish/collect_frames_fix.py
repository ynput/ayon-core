from __future__ import annotations

import typing

import pyblish.api
import ayon_api

from ayon_core.lib.attribute_definitions import (
    TextDef,
    BoolDef,
)
from ayon_core.pipeline.publish import AYONPyblishPluginMixin

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.create import CreatedInstance, CreateContext
    from ayon_core.lib.attribute_definitions import AbstractAttrDef


class CollectFramesFixDef(
    pyblish.api.InstancePlugin,
    AYONPyblishPluginMixin
):
    """Provides text field to insert frame(s) to be rerendered.

    Published files of last version of an instance product are collected into
    instance.data["last_version_published_files"]. All these but frames
    mentioned in text field will be reused for new version.
    """
    order = pyblish.api.CollectorOrder + 0.495
    label = "Collect Frames to Fix"
    targets = ["local"]
    hosts = ["nuke"]
    families = ["render", "prerender"]
    settings_category = "core"

    rewrite_version_enable = False

    def process(self, instance):
        attribute_values = self.get_attr_values_from_data(instance.data)
        frames_to_fix = attribute_values.get("frames_to_fix")

        rewrite_version = attribute_values.get("rewrite_version")

        if not frames_to_fix:
            return

        instance.data["frames_to_fix"] = frames_to_fix

        product_name = instance.data["productName"]
        folder_entity = instance.data["folderEntity"]

        project_entity = instance.data["projectEntity"]
        project_name = project_entity["name"]

        version_entity = ayon_api.get_last_version_by_product_name(
            project_name,
            product_name,
            folder_entity["id"]
        )
        if not version_entity:
            self.log.warning(
                "No last version found, re-render not possible"
            )
            return

        product_entity = ayon_api.get_product_by_id(
            project_name, version_entity["productId"]
        )
        product_base_type = product_entity["productBaseType"]
        published_files = []
        if product_base_type in self.families:
            representations = ayon_api.get_representations(
                project_name, version_ids={version_entity["id"]}
            )
            for repre in representations:
                published_files.extend(
                    file_info["path"]
                    for file_info in repre["files"]
                )

        instance.data["last_version_published_files"] = published_files
        self.log.debug("last_version_published_files::{}".format(
            instance.data["last_version_published_files"]))

        if self.rewrite_version_enable and rewrite_version:
            instance.data["version"] = version_entity["version"]
            # limits triggering version validator
            instance.data.pop("latestVersion")

    @classmethod
    def get_attr_defs_for_instance(
        cls, create_context: CreateContext, instance: CreatedInstance
    ) -> list[AbstractAttrDef]:
        # Future compatibility: if CollectFramesFixDefNuke is used, do not
        #   show this plugin's attributes it means nuke integration is
        #   responsible for frames fix.
        # TODO bump compatible 'nuke' version when this is removed. Don't
        #   forget to remove settings.
        for plugin in create_context.plugins_with_defs:
            if plugin.__class__.__name__ == "CollectFramesFixDefNuke":
                return []

        attributes: list[AbstractAttrDef] = [
            TextDef(
                "frames_to_fix",
                label="Frames to fix",
                placeholder="5,10-15",
                regex="[0-9,-]+",
            )
        ]

        if cls.rewrite_version_enable:
            attributes.append(
                BoolDef(
                    "rewrite_version",
                    label="Rewrite latest version",
                    default=False
                )
            )

        return attributes
