import os
import json
import copy

from ayon_server.addons import BaseServerAddon, AddonLibrary
from ayon_server.entities.core import attribute_library
from ayon_server.lib.postgres import Postgres

from .settings import ApplicationsAddonSettings, DEFAULT_VALUES

try:
    import semver
except ImportError:
    semver = None


def sort_versions(addon_versions, reverse=False):
    if semver is None:
        for addon_version in sorted(addon_versions, reverse=reverse):
            yield addon_version
        return

    version_objs = []
    invalid_versions = []
    for addon_version in addon_versions:
        try:
            version_objs.append(
                (addon_version, semver.VersionInfo.parse(addon_version))
            )
        except ValueError:
            invalid_versions.append(addon_version)

    valid_versions = [
        addon_version
        for addon_version, _ in sorted(version_objs, key=lambda x: x[1])
    ]
    sorted_versions = list(sorted(invalid_versions)) + valid_versions
    if reverse:
        sorted_versions = reversed(sorted_versions)
    for addon_version in sorted_versions:
        yield addon_version


def merge_groups(output, new_groups):
    groups_by_name = {
        o_group["name"]: o_group
        for o_group in output
    }
    extend_groups = []
    for new_group in new_groups:
        group_name = new_group["name"]
        if group_name not in groups_by_name:
            extend_groups.append(new_group)
            continue
        existing_group = groups_by_name[group_name]
        existing_variants = existing_group["variants"]
        existing_variants_by_name = {
            variant["name"]: variant
            for variant in existing_variants
        }
        for new_variant in new_group["variants"]:
            if new_variant["name"] not in existing_variants_by_name:
                existing_variants.append(new_variant)

    output.extend(extend_groups)


def get_enum_items_from_groups(groups):
    label_by_name = {}
    for group in groups:
        group_name = group["name"]
        group_label = group["label"] or group_name
        for variant in group["variants"]:
            variant_name = variant["name"]
            if not variant_name:
                continue
            variant_label = variant["label"] or variant_name
            full_name = f"{group_name}/{variant_name}"
            full_label = f"{group_label} {variant_label}"
            label_by_name[full_name] = full_label

    return [
        {"value": full_name, "label": label_by_name[full_name]}
        for full_name in sorted(label_by_name)
    ]


class ApplicationsAddon(BaseServerAddon):
    settings_model = ApplicationsAddonSettings

    async def get_default_settings(self):
        server_dir = os.path.join(self.addon_dir, "server")
        applications_path = os.path.join(server_dir, "applications.json")
        tools_path = os.path.join(server_dir, "tools.json")
        default_values = copy.deepcopy(DEFAULT_VALUES)
        with open(applications_path, "r") as stream:
            default_values.update(json.load(stream))

        with open(tools_path, "r") as stream:
            default_values.update(json.load(stream))

        return self.get_settings_model()(**default_values)

    async def pre_setup(self):
        """Make sure older version of addon use the new way of attributes."""

        instance = AddonLibrary.getinstance()
        app_defs = instance.data.get(self.name)
        old_addon = app_defs.versions.get("0.1.0")
        if old_addon is not None:
            # Override 'create_applications_attribute' for older versions
            #   - avoid infinite server restart loop
            old_addon.create_applications_attribute = (
                self.create_applications_attribute
            )

    async def setup(self):
        need_restart = await self.create_required_attributes()
        if need_restart:
            self.request_server_restart()
        await self._update_enums()

    def _get_applications_def(self):
        return {
            "name": "applications",
            "type": "list_of_strings",
            "title": "Applications",
            "scope": ["project"],
            "enum":[],
        }

    def _get_tools_def(self):
        return {
            "name": "tools",
            "type": "list_of_strings",
            "title": "Tools",
            "scope": ["project", "folder", "task"],
            "enum":[],
        }

    async def create_applications_attribute(self) -> bool:
        """Make sure there are required attributes which ftrack addon needs.

        Returns:
            bool: 'True' if an attribute was created or updated.
        """

        need_restart = await self.create_required_attributes()
        await self._update_enums()
        return need_restart

    async def create_required_attributes(self) -> bool:
        """Make sure there are required 'applications' and 'tools' attributes.
        This only checks for the existence of the attributes, it does not populate
        them with any data. When an attribute is added, server needs to be restarted,
        while adding enum data to the attribute does not require a restart.
        Returns:
            bool: 'True' if an attribute was created or updated.
        """

        # keep track of the last attribute position (for adding new attributes)
        apps_attribute_data = self._get_applications_def()
        tools_attribute_data = self._get_tools_def()

        apps_attrib_name = apps_attribute_data["name"]
        tools_attrib_name = tools_attribute_data["name"]

        async with Postgres.acquire() as conn, conn.transaction():
            query = "SELECT BOOL_OR(name = 'applications') AS has_applications, BOOL_OR(name = 'tools') AS has_tools FROM attributes;"
            result = (await conn.fetch(query))[0]

            attributes_to_create = {}
            if not result["has_applications"]:
                attributes_to_create[apps_attrib_name] = {
                    "scope": apps_attribute_data["scope"],
                    "data": {
                        "title": apps_attribute_data["title"],
                        "type": apps_attribute_data["type"],
                        "enum": [],
                    }
                }

            if not result["has_tools"]:
                attributes_to_create[tools_attrib_name] = {
                    "scope": tools_attribute_data["scope"],
                    "data": {
                        "title": tools_attribute_data["title"],
                        "type": tools_attribute_data["type"],
                        "enum": [],
                    },
                }

            needs_restart = False
            # when any of the required attributes are not present, add them
            # and return 'True' to indicate that server needs to be restarted
            for name, payload in attributes_to_create.items():
                insert_query = "INSERT INTO attributes (name, scope, data, position) VALUES ($1, $2, $3, (SELECT COALESCE(MAX(position), 0) + 1 FROM attributes)) ON CONFLICT DO NOTHING"
                await conn.execute(
                    insert_query,
                    name,
                    payload["scope"],
                    payload["data"],
                )
                needs_restart = True

        return needs_restart

    async def _update_enums(self):
        """Updates applications and tools enums based on the addon settings.
        This method is called when the addon is started (after we are sure that the
        'applications' and 'tools' attributes exist) and when the addon settings are
        updated (using on_settings_updated method).
        """

        instance = AddonLibrary.getinstance()
        app_defs = instance.data.get(self.name)
        all_applications = []
        all_tools = []
        for addon_version in sort_versions(
            app_defs.versions.keys(), reverse=True
        ):
            addon = app_defs.versions[addon_version]
            for variant in ("production", "staging"):
                settings_model = await addon.get_studio_settings(variant)
                studio_settings = settings_model.dict()
                application_settings = studio_settings["applications"]
                app_groups = application_settings.pop("additional_apps")
                for group_name, value in application_settings.items():
                    value["name"] = group_name
                    app_groups.append(value)
                merge_groups(all_applications, app_groups)
                merge_groups(all_tools, studio_settings["tool_groups"])

        apps_attrib_name = "applications"
        tools_attrib_name = "tools"

        apps_enum = get_enum_items_from_groups(all_applications)
        tools_enum = get_enum_items_from_groups(all_tools)

        apps_attribute_data = {
            "type": "list_of_strings",
            "title": "Applications",
            "enum": apps_enum,
        }
        tools_attribute_data = {
            "type": "list_of_strings",
            "title": "Tools",
            "enum": tools_enum,
        }

        apps_scope = ["project"]
        tools_scope = ["project", "folder", "task"]

        apps_matches = False
        tools_matches = False

        async for row in Postgres.iterate(
            "SELECT name, position, scope, data from public.attributes"
        ):
            if row["name"] == apps_attrib_name:
                # Check if scope is matching ftrack addon requirements
                if (
                    set(row["scope"]) == set(apps_scope)
                    and row["data"].get("enum") == apps_enum
                ):
                    apps_matches = True

            elif row["name"] == tools_attrib_name:
                if (
                    set(row["scope"]) == set(tools_scope)
                    and row["data"].get("enum") == tools_enum
                ):
                    tools_matches = True

        if apps_matches and tools_matches:
            return

        if not apps_matches:
            await Postgres.execute(
                """
                UPDATE attributes SET
                    scope = $1,
                    data = $2
                WHERE 
                    name = $3
                """,
                apps_scope,
                apps_attribute_data,
                apps_attrib_name,
            )

        if not tools_matches:
            await Postgres.execute(
                """
                UPDATE attributes SET
                    scope = $1,
                    data = $2
                WHERE 
                    name = $3
                """,
                tools_scope,
                tools_attribute_data,
                tools_attrib_name,
            )

        # Reset attributes cache on server
        await attribute_library.load()

    async def on_settings_changed(self, *args, **kwargs):
        _ = args, kwargs
        await self._update_enums()
