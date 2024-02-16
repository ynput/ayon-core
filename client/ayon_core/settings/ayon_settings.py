"""Helper functionality to convert AYON settings to OpenPype v3 settings.

The settings are converted, so we can use v3 code with AYON settings. Once
the code of and addon is converted to full AYON addon which expect AYON
settings the conversion function can be removed.

The conversion is hardcoded -> there is no other way how to achieve the result.

Main entrypoints are functions:
- convert_project_settings - convert settings to project settings
- convert_system_settings - convert settings to system settings
# Both getters cache values
- get_ayon_project_settings - replacement for 'get_project_settings'
- get_ayon_system_settings - replacement for 'get_system_settings'
"""
import os
import collections
import json
import copy
import time

import six

from ayon_core.client import get_ayon_server_api_connection


def _convert_color(color_value):
    if isinstance(color_value, six.string_types):
        color_value = color_value.lstrip("#")
        color_value_len = len(color_value)
        _color_value = []
        for idx in range(color_value_len // 2):
            _color_value.append(int(color_value[idx:idx + 2], 16))
        for _ in range(4 - len(_color_value)):
            _color_value.append(255)
        return _color_value

    if isinstance(color_value, list):
        # WARNING R,G,B can be 'int' or 'float'
        # - 'float' variant is using 'int' for min: 0 and max: 1
        if len(color_value) == 3:
            # Add alpha
            color_value.append(255)
        else:
            # Convert float alha to int
            alpha = int(color_value[3] * 255)
            if alpha > 255:
                alpha = 255
            elif alpha < 0:
                alpha = 0
            color_value[3] = alpha
    return color_value


def _convert_general(ayon_settings, output, default_settings):
    output["core"] = ayon_settings["core"]
    version_check_interval = (
        default_settings["general"]["version_check_interval"]
    )
    output["general"] = {
        "version_check_interval": version_check_interval
    }


def _convert_deadline_system_settings(
    ayon_settings, output, addon_versions, default_settings
):
    enabled = addon_versions.get("deadline") is not None
    deadline_settings = default_settings["modules"]["deadline"]
    deadline_settings["enabled"] = enabled
    if enabled:
        ayon_deadline = ayon_settings["deadline"]
        deadline_settings["deadline_urls"] = {
            item["name"]: item["value"]
            for item in ayon_deadline["deadline_urls"]
        }

    output["modules"]["deadline"] = deadline_settings


def _convert_royalrender_system_settings(
    ayon_settings, output, addon_versions, default_settings
):
    enabled = addon_versions.get("royalrender") is not None
    rr_settings = default_settings["modules"]["royalrender"]
    rr_settings["enabled"] = enabled
    if enabled:
        ayon_royalrender = ayon_settings["royalrender"]
        rr_settings["rr_paths"] = {
            item["name"]: item["value"]
            for item in ayon_royalrender["rr_paths"]
        }
    output["modules"]["royalrender"] = rr_settings


def _convert_modules_system(
    ayon_settings, output, addon_versions, default_settings
):
    # TODO add all modules
    # TODO add 'enabled' values
    for func in (
        _convert_deadline_system_settings,
        _convert_royalrender_system_settings,
    ):
        func(ayon_settings, output, addon_versions, default_settings)

    for key in {
        "timers_manager",
        "clockify",
    }:
        if addon_versions.get(key):
            output[key] = ayon_settings
        else:
            output.pop(key, None)

    modules_settings = output["modules"]
    for module_name in (
        "sync_server",
        "job_queue",
        "addon_paths",
    ):
        settings = default_settings["modules"][module_name]
        if "enabled" in settings:
            settings["enabled"] = False
        modules_settings[module_name] = settings

    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

        # Make sure addons have access to settings in initialization
        # - AddonsManager passes only modules settings into initialization
        if key not in modules_settings:
            modules_settings[key] = value


def is_dev_mode_enabled():
    """Dev mode is enabled in AYON.

    Returns:
        bool: True if dev mode is enabled.
    """

    return os.getenv("AYON_USE_DEV") == "1"


def convert_system_settings(ayon_settings, default_settings, addon_versions):
    default_settings = copy.deepcopy(default_settings)
    output = {
        "modules": {}
    }
    if "core" in ayon_settings:
        _convert_general(ayon_settings, output, default_settings)

    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

    for key, value in default_settings.items():
        if key not in output:
            output[key] = value

    _convert_modules_system(
        ayon_settings,
        output,
        addon_versions,
        default_settings
    )
    return output


# --------- Project settings ---------
def _convert_nuke_knobs(knobs):
    new_knobs = []
    for knob in knobs:
        knob_type = knob["type"]

        if knob_type == "boolean":
            knob_type = "bool"

        if knob_type != "bool":
            value = knob[knob_type]
        elif knob_type in knob:
            value = knob[knob_type]
        else:
            value = knob["boolean"]

        new_knob = {
            "type": knob_type,
            "name": knob["name"],
        }
        new_knobs.append(new_knob)

        if knob_type == "formatable":
            new_knob["template"] = value["template"]
            new_knob["to_type"] = value["to_type"]
            continue

        value_key = "value"
        if knob_type == "expression":
            value_key = "expression"

        elif knob_type == "color_gui":
            value = _convert_color(value)

        elif knob_type == "vector_2d":
            value = [value["x"], value["y"]]

        elif knob_type == "vector_3d":
            value = [value["x"], value["y"], value["z"]]

        elif knob_type == "box":
            value = [value["x"], value["y"], value["r"], value["t"]]

        new_knob[value_key] = value
    return new_knobs


def _convert_nuke_project_settings(ayon_settings, output):
    if "nuke" not in ayon_settings:
        return

    ayon_nuke = ayon_settings["nuke"]

    # --- Load ---
    ayon_load = ayon_nuke["load"]
    ayon_load["LoadClip"]["_representations"] = (
        ayon_load["LoadClip"].pop("representations_include")
    )
    ayon_load["LoadImage"]["_representations"] = (
        ayon_load["LoadImage"].pop("representations_include")
    )

    # --- Create ---
    ayon_create = ayon_nuke["create"]
    for creator_name in (
        "CreateWritePrerender",
        "CreateWriteImage",
        "CreateWriteRender",
    ):
        create_plugin_settings = ayon_create[creator_name]
        create_plugin_settings["temp_rendering_path_template"] = (
            create_plugin_settings["temp_rendering_path_template"]
            .replace("{product[name]}", "{subset}")
            .replace("{product[type]}", "{family}")
            .replace("{task[name]}", "{task}")
            .replace("{folder[name]}", "{asset}")
        )
        new_prenodes = {}
        for prenode in create_plugin_settings["prenodes"]:
            name = prenode.pop("name")
            prenode["knobs"] = _convert_nuke_knobs(prenode["knobs"])
            new_prenodes[name] = prenode

        create_plugin_settings["prenodes"] = new_prenodes

    # --- Publish ---
    ayon_publish = ayon_nuke["publish"]
    slate_mapping = ayon_publish["ExtractSlateFrame"]["key_value_mapping"]
    for key in tuple(slate_mapping.keys()):
        value = slate_mapping[key]
        slate_mapping[key] = [value["enabled"], value["template"]]

    ayon_publish["ValidateKnobs"]["knobs"] = json.loads(
        ayon_publish["ValidateKnobs"]["knobs"]
    )

    new_review_data_outputs = {}
    outputs_settings = []
    # Check deprecated ExtractReviewDataMov
    # settings for backwards compatibility
    deprecrated_review_settings = ayon_publish["ExtractReviewDataMov"]
    current_review_settings = (
        ayon_publish.get("ExtractReviewIntermediates")
    )
    if deprecrated_review_settings["enabled"]:
        outputs_settings = deprecrated_review_settings["outputs"]
    elif current_review_settings is None:
        pass
    elif current_review_settings["enabled"]:
        outputs_settings = current_review_settings["outputs"]

    for item in outputs_settings:
        item_filter = item["filter"]
        if "product_names" in item_filter:
            item_filter["subsets"] = item_filter.pop("product_names")
            item_filter["families"] = item_filter.pop("product_types")

        reformat_nodes_config = item.get("reformat_nodes_config") or {}
        reposition_nodes = reformat_nodes_config.get(
            "reposition_nodes") or []

        for reposition_node in reposition_nodes:
            if "knobs" not in reposition_node:
                continue
            reposition_node["knobs"] = _convert_nuke_knobs(
                reposition_node["knobs"]
            )

        name = item.pop("name")
        new_review_data_outputs[name] = item

    if deprecrated_review_settings["enabled"]:
        deprecrated_review_settings["outputs"] = new_review_data_outputs
    elif current_review_settings["enabled"]:
        current_review_settings["outputs"] = new_review_data_outputs

    collect_instance_data = ayon_publish["CollectInstanceData"]
    if "sync_workfile_version_on_product_types" in collect_instance_data:
        collect_instance_data["sync_workfile_version_on_families"] = (
            collect_instance_data.pop(
                "sync_workfile_version_on_product_types"))

    # --- ImageIO ---
    # NOTE 'monitorOutLut' is maybe not yet in v3 (ut should be)
    ayon_imageio = ayon_nuke["imageio"]

    # workfile
    imageio_workfile = ayon_imageio["workfile"]
    workfile_keys_mapping = (
        ("color_management", "colorManagement"),
        ("native_ocio_config", "OCIO_config"),
        ("working_space", "workingSpaceLUT"),
        ("thumbnail_space", "monitorLut"),
    )
    for src, dst in workfile_keys_mapping:
        if (
            src in imageio_workfile
            and dst not in imageio_workfile
        ):
            imageio_workfile[dst] = imageio_workfile.pop(src)

    # regex inputs
    if "regex_inputs" in ayon_imageio:
        ayon_imageio["regexInputs"] = ayon_imageio.pop("regex_inputs")

    # nodes
    ayon_imageio_nodes = ayon_imageio["nodes"]
    if "required_nodes" in ayon_imageio_nodes:
        ayon_imageio_nodes["requiredNodes"] = (
            ayon_imageio_nodes.pop("required_nodes"))
    if "override_nodes" in ayon_imageio_nodes:
        ayon_imageio_nodes["overrideNodes"] = (
            ayon_imageio_nodes.pop("override_nodes"))

    for item in ayon_imageio_nodes["requiredNodes"]:
        if "nuke_node_class" in item:
            item["nukeNodeClass"] = item.pop("nuke_node_class")
        item["knobs"] = _convert_nuke_knobs(item["knobs"])

    for item in ayon_imageio_nodes["overrideNodes"]:
        if "nuke_node_class" in item:
            item["nukeNodeClass"] = item.pop("nuke_node_class")
        item["knobs"] = _convert_nuke_knobs(item["knobs"])

    output["nuke"] = ayon_nuke


def _convert_hiero_project_settings(ayon_settings, output):
    if "hiero" not in ayon_settings:
        return

    ayon_hiero = ayon_settings["hiero"]

    new_gui_filters = {}
    for item in ayon_hiero.pop("filters", []):
        subvalue = {}
        key = item["name"]
        for subitem in item["value"]:
            subvalue[subitem["name"]] = subitem["value"]
        new_gui_filters[key] = subvalue
    ayon_hiero["filters"] = new_gui_filters

    ayon_load_clip = ayon_hiero["load"]["LoadClip"]
    if "product_types" in ayon_load_clip:
        ayon_load_clip["families"] = ayon_load_clip.pop("product_types")

    ayon_load_clip = ayon_hiero["load"]["LoadClip"]
    ayon_load_clip["clip_name_template"] = (
        ayon_load_clip["clip_name_template"]
        .replace("{folder[name]}", "{asset}")
        .replace("{product[name]}", "{subset}")
    )

    output["hiero"] = ayon_hiero


def _convert_royalrender_project_settings(ayon_settings, output):
    if "royalrender" not in ayon_settings:
        return
    ayon_royalrender = ayon_settings["royalrender"]
    rr_paths = ayon_royalrender.get("selected_rr_paths", [])

    output["royalrender"] = {
        "publish": ayon_royalrender["publish"],
        "rr_paths": rr_paths,
    }


def _convert_global_project_settings(ayon_settings, output, default_settings):
    if "core" not in ayon_settings:
        return

    ayon_core = ayon_settings["core"]

    # Publish conversion
    ayon_publish = ayon_core["publish"]

    # ExtractThumbnail plugin
    ayon_extract_thumbnail = ayon_publish["ExtractThumbnail"]
    # fix display and view at oiio defaults
    ayon_default_oiio = copy.deepcopy(
        ayon_extract_thumbnail["oiiotool_defaults"])
    display_and_view = ayon_default_oiio.pop("display_and_view")
    ayon_default_oiio["display"] = display_and_view["display"]
    ayon_default_oiio["view"] = display_and_view["view"]
    ayon_extract_thumbnail["oiiotool_defaults"] = ayon_default_oiio
    # fix target size
    ayon_default_resize = copy.deepcopy(ayon_extract_thumbnail["target_size"])
    resize = ayon_default_resize.pop("resize")
    ayon_default_resize["width"] = resize["width"]
    ayon_default_resize["height"] = resize["height"]
    ayon_extract_thumbnail["target_size"] = ayon_default_resize
    # fix background color
    ayon_extract_thumbnail["background_color"] = _convert_color(
        ayon_extract_thumbnail["background_color"]
    )

    # ExtractOIIOTranscode plugin
    extract_oiio_transcode = ayon_publish["ExtractOIIOTranscode"]
    extract_oiio_transcode_profiles = extract_oiio_transcode["profiles"]
    for profile in extract_oiio_transcode_profiles:
        new_outputs = {}
        name_counter = {}
        if "product_names" in profile:
            profile["subsets"] = profile.pop("product_names")
        for profile_output in profile["outputs"]:
            if "name" in profile_output:
                name = profile_output.pop("name")
            else:
                # Backwards compatibility for setting without 'name' in model
                name = profile_output["extension"]
                if name in new_outputs:
                    name_counter[name] += 1
                    name = "{}_{}".format(name, name_counter[name])
                else:
                    name_counter[name] = 0

            new_outputs[name] = profile_output
        profile["outputs"] = new_outputs

    # Extract Burnin plugin
    extract_burnin = ayon_publish["ExtractBurnin"]
    extract_burnin_options = extract_burnin["options"]
    for color_key in ("font_color", "bg_color"):
        extract_burnin_options[color_key] = _convert_color(
            extract_burnin_options[color_key]
        )

    for profile in extract_burnin["profiles"]:
        extract_burnin_defs = profile["burnins"]
        if "product_names" in profile:
            profile["subsets"] = profile.pop("product_names")
            profile["families"] = profile.pop("product_types")

        for burnin_def in extract_burnin_defs:
            for key in (
                "TOP_LEFT",
                "TOP_CENTERED",
                "TOP_RIGHT",
                "BOTTOM_LEFT",
                "BOTTOM_CENTERED",
                "BOTTOM_RIGHT",
            ):
                burnin_def[key] = (
                    burnin_def[key]
                    .replace("{product[name]}", "{subset}")
                    .replace("{Product[name]}", "{Subset}")
                    .replace("{PRODUCT[NAME]}", "{SUBSET}")
                    .replace("{product[type]}", "{family}")
                    .replace("{Product[type]}", "{Family}")
                    .replace("{PRODUCT[TYPE]}", "{FAMILY}")
                    .replace("{folder[name]}", "{asset}")
                    .replace("{Folder[name]}", "{Asset}")
                    .replace("{FOLDER[NAME]}", "{ASSET}")
                )
        profile["burnins"] = {
            extract_burnin_def.pop("name"): extract_burnin_def
            for extract_burnin_def in extract_burnin_defs
        }

    if "IntegrateProductGroup" in ayon_publish:
        subset_group = ayon_publish.pop("IntegrateProductGroup")
        subset_group_profiles = subset_group.pop("product_grouping_profiles")
        for profile in subset_group_profiles:
            profile["families"] = profile.pop("product_types")
        subset_group["subset_grouping_profiles"] = subset_group_profiles
        ayon_publish["IntegrateSubsetGroup"] = subset_group

    # Cleanup plugin
    ayon_cleanup = ayon_publish["CleanUp"]
    if "patterns" in ayon_cleanup:
        ayon_cleanup["paterns"] = ayon_cleanup.pop("patterns")

    # Project root settings - json string to dict
    ayon_core["project_environments"] = json.loads(
        ayon_core["project_environments"]
    )
    ayon_core["project_folder_structure"] = json.dumps(json.loads(
        ayon_core["project_folder_structure"]
    ))

    # Tools settings
    ayon_tools = ayon_core["tools"]
    ayon_create_tool = ayon_tools["creator"]
    if "product_name_profiles" in ayon_create_tool:
        product_name_profiles = ayon_create_tool.pop("product_name_profiles")
        for profile in product_name_profiles:
            profile["families"] = profile.pop("product_types")
        ayon_create_tool["subset_name_profiles"] = product_name_profiles

    for profile in ayon_create_tool["subset_name_profiles"]:
        template = profile["template"]
        profile["template"] = (
            template
            .replace("{task[name]}", "{task}")
            .replace("{Task[name]}", "{Task}")
            .replace("{TASK[NAME]}", "{TASK}")
            .replace("{product[type]}", "{family}")
            .replace("{Product[type]}", "{Family}")
            .replace("{PRODUCT[TYPE]}", "{FAMILY}")
            .replace("{folder[name]}", "{asset}")
            .replace("{Folder[name]}", "{Asset}")
            .replace("{FOLDER[NAME]}", "{ASSET}")
        )

    product_smart_select_key = "families_smart_select"
    if "product_types_smart_select" in ayon_create_tool:
        product_smart_select_key = "product_types_smart_select"

    new_smart_select_families = {
        item["name"]: item["task_names"]
        for item in ayon_create_tool.pop(product_smart_select_key)
    }
    ayon_create_tool["families_smart_select"] = new_smart_select_families

    ayon_loader_tool = ayon_tools["loader"]
    if "product_type_filter_profiles" in ayon_loader_tool:
        product_type_filter_profiles = (
            ayon_loader_tool.pop("product_type_filter_profiles"))
        for profile in product_type_filter_profiles:
            profile["filter_families"] = profile.pop("filter_product_types")

        ayon_loader_tool["family_filter_profiles"] = (
            product_type_filter_profiles)

    ayon_publish_tool = ayon_tools["publish"]
    for profile in ayon_publish_tool["hero_template_name_profiles"]:
        if "product_types" in profile:
            profile["families"] = profile.pop("product_types")

    for profile in ayon_publish_tool["template_name_profiles"]:
        if "product_types" in profile:
            profile["families"] = profile.pop("product_types")

    ayon_core["sync_server"] = (
        default_settings["global"]["sync_server"]
    )
    output["global"] = ayon_core


def convert_project_settings(ayon_settings, default_settings):
    default_settings = copy.deepcopy(default_settings)
    output = {}

    _convert_nuke_project_settings(ayon_settings, output)
    _convert_hiero_project_settings(ayon_settings, output)

    _convert_royalrender_project_settings(ayon_settings, output)

    _convert_global_project_settings(ayon_settings, output, default_settings)

    for key, value in ayon_settings.items():
        if key not in output:
            output[key] = value

    for key, value in default_settings.items():
        if key not in output:
            output[key] = value

    return output


class CacheItem:
    lifetime = 10

    def __init__(self, value, outdate_time=None):
        self._value = value
        if outdate_time is None:
            outdate_time = time.time() + self.lifetime
        self._outdate_time = outdate_time

    @classmethod
    def create_outdated(cls):
        return cls({}, 0)

    def get_value(self):
        return copy.deepcopy(self._value)

    def update_value(self, value):
        self._value = value
        self._outdate_time = time.time() + self.lifetime

    @property
    def is_outdated(self):
        return time.time() > self._outdate_time


class _AyonSettingsCache:
    use_bundles = None
    variant = None
    addon_versions = CacheItem.create_outdated()
    studio_settings = CacheItem.create_outdated()
    cache_by_project_name = collections.defaultdict(
        CacheItem.create_outdated)

    @classmethod
    def _use_bundles(cls):
        if _AyonSettingsCache.use_bundles is None:
            con = get_ayon_server_api_connection()
            major, minor, _, _, _ = con.get_server_version_tuple()
            use_bundles = True
            if (major, minor) < (0, 3):
                use_bundles = False
            _AyonSettingsCache.use_bundles = use_bundles
        return _AyonSettingsCache.use_bundles

    @classmethod
    def _get_variant(cls):
        if _AyonSettingsCache.variant is None:
            from ayon_core.lib import is_staging_enabled

            variant = "production"
            if is_dev_mode_enabled():
                variant = cls._get_bundle_name()
            elif is_staging_enabled():
                variant = "staging"

            # Cache variant
            _AyonSettingsCache.variant = variant

            # Set the variant to global ayon api connection
            con = get_ayon_server_api_connection()
            con.set_default_settings_variant(variant)
        return _AyonSettingsCache.variant

    @classmethod
    def _get_bundle_name(cls):
        return os.environ["AYON_BUNDLE_NAME"]

    @classmethod
    def get_value_by_project(cls, project_name):
        cache_item = _AyonSettingsCache.cache_by_project_name[project_name]
        if cache_item.is_outdated:
            con = get_ayon_server_api_connection()
            if cls._use_bundles():
                value = con.get_addons_settings(
                    bundle_name=cls._get_bundle_name(),
                    project_name=project_name,
                    variant=cls._get_variant()
                )
            else:
                value = con.get_addons_settings(project_name)
            cache_item.update_value(value)
        return cache_item.get_value()

    @classmethod
    def _get_addon_versions_from_bundle(cls):
        con = get_ayon_server_api_connection()
        expected_bundle = cls._get_bundle_name()
        bundles = con.get_bundles()["bundles"]
        bundle = next(
            (
                bundle
                for bundle in bundles
                if bundle["name"] == expected_bundle
            ),
            None
        )
        if bundle is not None:
            return bundle["addons"]
        return {}

    @classmethod
    def get_addon_versions(cls):
        cache_item = _AyonSettingsCache.addon_versions
        if cache_item.is_outdated:
            if cls._use_bundles():
                addons = cls._get_addon_versions_from_bundle()
            else:
                con = get_ayon_server_api_connection()
                settings_data = con.get_addons_settings(
                    only_values=False,
                    variant=cls._get_variant()
                )
                addons = settings_data["versions"]
            cache_item.update_value(addons)

        return cache_item.get_value()


def get_ayon_project_settings(default_values, project_name):
    ayon_settings = _AyonSettingsCache.get_value_by_project(project_name)
    return convert_project_settings(ayon_settings, default_values)


def get_ayon_system_settings(default_values):
    addon_versions = _AyonSettingsCache.get_addon_versions()
    ayon_settings = _AyonSettingsCache.get_value_by_project(None)

    return convert_system_settings(
        ayon_settings, default_values, addon_versions
    )


def get_ayon_settings(project_name=None):
    """AYON studio settings.

    Raw AYON settings values.

    Args:
        project_name (Optional[str]): Project name.

    Returns:
        dict[str, Any]: AYON settings.
    """

    return _AyonSettingsCache.get_value_by_project(project_name)
