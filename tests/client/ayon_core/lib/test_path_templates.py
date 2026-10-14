"""Tests for 'ayon_core.lib.path_templates'."""
from __future__ import annotations

import copy

import pytest

from ayon_core.lib import path_templates
from ayon_core.lib.path_templates import (
    DefaultKeysDict,
    FormatObject,
    StringTemplate,
    TemplateUnsolved,
    get_template_format_specs,
    register_template_format_spec,
)
from ayon_core.lib.plugin_tools import prepare_template_data


class _Root(FormatObject):
    def __init__(self, value: str):
        super().__init__()
        self.value = value


def _get_data() -> dict:
    return {
        "root": {"work": _Root("P:/projects")},
        "project": {"name": "demo", "code": "dm"},
        "hierarchy": "shots/sq01",
        "folder": {"name": "sh010", "type": "Shot"},
        "task": {"name": "animation", "type": "Animation", "short": "anim"},
        "product": {
            "name": "renderAnimationMain",
            "type": "render",
            "basetype": "render",
        },
        "host": {"name": "maya"},
        "variant": "main",
        "family": "render",
        "version": 3,
        "frame": 1001,
        "ext": "exr",
        "udim": [1001, 1002],
        "tags": ["first", "second"],
    }


class TestBackwardsCompatibility:
    """Behavior of templates that existed before named format specs.

    These tests describe templates and data that are already used in
    production. They must keep passing without any change.
    """

    @pytest.mark.parametrize(
        "template, expected",
        [
            ("{project[name]}", "demo"),
            ("{project[name]}_{folder[name]}", "demo_sh010"),
            ("v{version:0>3}", "v003"),
            ("v{version:03d}", "v003"),
            ("{frame:0>6}", "001001"),
            ("{ext:>5}", "  exr"),
            ("{ext!r}", "'exr'"),
            ("{variant!s:_<6}", "main__"),
            ("{root[work]}/{project[name]}", "P:/projects/demo"),
            ("{tags[0]}-{tags[-1]}", "first-second"),
            ("{udim[1]}", "1002"),
            # Optional parts
            ("{ext}<_{output}>", "exr"),
            ("{ext}<_{variant}>", "exr_main"),
            ("{ext}<_{variant}<_{output}>>", "exr_main"),
            ("<{missing}>", ""),
            # Not a formatting key
            ("<just text>", "<just text>"),
            ("a > b", "a > b"),
            ("{{escaped}}", "{escaped}"),
        ],
    )
    def test_format(self, template: str, expected: str):
        result = StringTemplate(template).format(_get_data())
        assert str(result) == expected
        assert result.solved

    def test_publish_path(self):
        template = (
            "{root[work]}/{project[name]}/{hierarchy}/{folder[name]}"
            "/publish/{product[type]}/{product[name]}/v{version:0>3}"
            "/{project[code]}_{folder[name]}_{product[name]}"
            "_v{version:0>3}<_{output}><.{frame:0>4}>.{ext}"
        )
        result = StringTemplate(template).format_strict(_get_data())
        assert str(result) == (
            "P:/projects/demo/shots/sq01/sh010/publish/render"
            "/renderAnimationMain/v003"
            "/dm_sh010_renderAnimationMain_v003.1001.exr"
        )
        assert result.used_values == {
            "root": {"work": "P:/projects"},
            "project": {"name": "demo", "code": "dm"},
            "hierarchy": "shots/sq01",
            "folder": {"name": "sh010"},
            "product": {"type": "render", "name": "renderAnimationMain"},
            "version": 3,
            "frame": 1001,
            "ext": "exr",
        }

    def test_missing_key(self):
        result = StringTemplate("{project[name]}_{missing}_{task[nope]}")
        result = result.format(_get_data())
        assert str(result) == "demo_{missing}_{task[nope]}"
        assert not result.solved
        assert sorted(result.missing_keys) == ["missing", "task[nope]"]
        with pytest.raises(TemplateUnsolved):
            result.validate()

    def test_invalid_type(self):
        result = StringTemplate("{project}").format(_get_data())
        assert str(result) == "{project}"
        assert not result.solved
        assert result.invalid_types == {"project": dict}

    def test_none_value_is_not_solved(self):
        result = StringTemplate("{output}").format({"output": None})
        assert not result.solved

    def test_default_keys_dict(self):
        data = {"folder": DefaultKeysDict("name", {"name": "sh010"})}
        assert StringTemplate("{folder}").format(data) == "sh010"
        assert StringTemplate("{folder[name]}").format(data) == "sh010"

    def test_data_are_not_modified(self):
        data = _get_data()
        data.pop("root")
        src_data = copy.deepcopy(data)
        StringTemplate("{task[name]}{tags[0]}<{output}>").format(data)
        assert data == src_data

    @pytest.mark.parametrize(
        "key", ["AYON_PROJECT_NAME", "Path", "PATH", "X", "MiXeD"]
    )
    def test_exact_key_is_used_as_is(self, key: str):
        """Keys with uppercase characters are used as they are.

        That is important e.g. for environment variables, value of
        '{AYON_PROJECT_NAME}' must not be modified.
        """
        data = {key: "some/Value"}
        result = StringTemplate(f"{{{key}}}").format_strict(data)
        assert str(result) == "some/Value"
        assert result.used_values == data

    @pytest.mark.parametrize(
        "template, expected",
        [
            ("{task[name]}", "animation"),
            ("{Task[name]}", "Animation"),
            ("{TASK[NAME]}", "ANIMATION"),
            ("{family}{Task[name]}{Variant}", "renderAnimationMain"),
            ("{FAMILY}_{Family}_{family}", "RENDER_Render_render"),
            (
                "{product[type]}{Task[short]}<_{Output}>{Variant}",
                "renderAnimMain"
            ),
            ("{Task[name]:>10}", " Animation"),
            ("{VARIANT!r}", "'MAIN'"),
            ("{Version:0>3}/{VERSION}", "003/3"),
        ],
    )
    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_prepared_template_data(self, template: str, expected: str):
        """Data prepared with 'prepare_template_data' work as before."""
        data = _get_data()
        data.pop("root")
        result = StringTemplate(template).format_strict(
            prepare_template_data(data)
        )
        assert str(result) == expected

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_prepared_template_data_used_values(self):
        data = _get_data()
        data.pop("root")
        result = StringTemplate("{Task[name]}_{TASK[NAME]}").format_strict(
            prepare_template_data(data)
        )
        assert result.used_values == {
            "Task": {"name": "Animation"},
            "TASK": {"NAME": "ANIMATION"},
        }


class TestLegacyKeys:
    """'StringTemplate' does not resolve legacy '{Key}' and '{KEY}' keys."""

    @pytest.mark.parametrize(
        "template, missing_key",
        [
            ("{Task[name]}", "Task"),
            ("{TASK[NAME]}", "TASK"),
            ("{Variant}", "Variant"),
        ],
    )
    def test_not_resolved_from_lowercase_key(
        self, template: str, missing_key: str
    ):
        result = StringTemplate(template).format(_get_data())
        assert str(result) == template
        assert not result.solved
        assert result.missing_keys == [missing_key]

    def test_prepare_template_data_is_deprecated(self):
        with pytest.deprecated_call():
            output = prepare_template_data({"host": "maya"})
        assert output == {"host": "maya", "Host": "Maya", "HOST": "MAYA"}


class TestNamedFormatSpecs:
    """Named format specs, e.g. '{key:upper}'."""

    @pytest.mark.parametrize(
        "template, expected",
        [
            ("{task[name]:upper}", "ANIMATION"),
            ("{task[type]:lower}", "animation"),
            ("{variant:upperfirst}", "Main"),
            ("{task[type]:lowerfirst}", "animation"),
            ("{product[name]:upper}", "RENDERANIMATIONMAIN"),
            ("{product[name]:snake}", "render_animation_main"),
            ("{product[name]:pascal}", "RenderAnimationMain"),
            ("{hierarchy:camel}", "shotsSq01"),
            ("{hierarchy:title}", "Shots/Sq01"),
            ("{product[name]:title}", "Renderanimationmain"),
            ("{product[name]:camel}", "renderAnimationMain"),
            ("{hierarchy:pascal}", "ShotsSq01"),
            ("{hierarchy:snake}", "shots_sq01"),
            # Mixed with python format specs
            ("{folder[name]:upper}_v{version:0>3}", "SH010_v003"),
            # Optional parts
            ("{ext}<_{output:upper}>", "exr"),
            ("{ext}<_{variant:upper}>", "exr_MAIN"),
            # List items
            ("{tags[0]:upper}_{tags[-1]:upperfirst}", "FIRST_Second"),
            # Not string values are converted to string
            ("{version:upper}", "3"),
            ("{root[work]:lower}", "p:/projects"),
            # Conversion is applied before the format spec
            ("{variant!r:upper}", "'MAIN'"),
        ],
    )
    def test_format(self, template: str, expected: str):
        result = StringTemplate(template).format_strict(_get_data())
        assert str(result) == expected

    @pytest.mark.parametrize(
        "value, spec, expected",
        [
            ("char_SuperHero", "upper", "CHAR_SUPERHERO"),
            ("char_SuperHero", "lower", "char_superhero"),
            ("char_SuperHero", "upperfirst", "Char_SuperHero"),
            ("Char_SuperHero", "lowerfirst", "char_SuperHero"),
            ("char_SuperHero", "title", "Char_Superhero"),
            ("light rig-main", "title", "Light Rig-Main"),
            ("sh010_MAIN", "title", "Sh010_Main"),
            ("char_SuperHero", "camel", "charSuperHero"),
            ("light rig-main", "camel", "lightRigMain"),
            ("Light Rig", "camel", "lightRig"),
            ("char_SuperHero", "pascal", "CharSuperHero"),
            ("char_SuperHero", "snake", "char_super_hero"),
            ("_shot", "upperfirst", "_Shot"),
            ("01_shot", "upperfirst", "01_Shot"),
            ("", "upperfirst", ""),
            ("__", "upperfirst", "__"),
            ("renderHTTPServer", "snake", "render_http_server"),
            ("renderHTTPServer", "camel", "renderHttpServer"),
            ("render main-beauty.v2", "pascal", "RenderMainBeautyV2"),
            ("sh010", "snake", "sh010"),
            ("sh010", "pascal", "Sh010"),
            ("main01Beauty", "snake", "main01_beauty"),
            ("", "camel", ""),
            ("--", "snake", ""),
        ],
    )
    def test_specs(self, value: str, spec: str, expected: str):
        template = StringTemplate(f"{{value:{spec}}}")
        assert str(template.format_strict({"value": value})) == expected

    def test_used_values_are_source_values(self):
        """Format spec does not change the used values."""
        result = StringTemplate(
            "{task[name]:upper}_{variant:upperfirst}_{version:upper}"
        ).format_strict(_get_data())
        assert str(result) == "ANIMATION_Main_3"
        assert result.used_values == {
            "task": {"name": "animation"},
            "variant": "main",
            "version": 3,
        }

    def test_missing_key(self):
        result = StringTemplate("{missing:upper}_{task[nope]:lower}")
        result = result.format(_get_data())
        assert str(result) == "{missing:upper}_{task[nope]:lower}"
        assert not result.solved
        assert sorted(result.missing_keys) == ["missing", "task[nope]"]

    def test_invalid_type(self):
        result = StringTemplate("{project:upper}").format(_get_data())
        assert str(result) == "{project:upper}"
        assert result.invalid_types == {"project": dict}

    def test_unknown_format_spec(self):
        """Unknown spec is handled by python formatting as before."""
        with pytest.raises(ValueError):
            StringTemplate("{variant:unknown}").format(_get_data())

    def test_remove_optional_parts(self):
        template = StringTemplate("{ext:upper}<_{output:upper}><_{variant}>")
        assert template.remove_optional_parts_for_data(_get_data()) == (
            "{ext:upper}_{variant}"
        )

    def test_data_are_not_modified(self):
        data = _get_data()
        data.pop("root")
        src_data = copy.deepcopy(data)
        StringTemplate("{task[name]:upper}{tags[0]:camel}").format(data)
        assert data == src_data


class TestFirstLetterSpecs:
    """'upperfirst' and 'lowerfirst' change the first alphabetical character.
    """

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("main", "Main"),
            ("mainBeauty", "MainBeauty"),
            ("_shot", "_Shot"),
            ("01_shot", "01_Shot"),
            ("{aa}", "{Aa}"),
            ("{aa}_bb", "{Aa}_bb"),
            ("\u00e9cole", "\u00c9cole"),
            ("123", "123"),
            ("__", "__"),
            ("", ""),
        ],
    )
    def test_upperfirst(self, value: str, expected: str):
        assert get_template_format_specs()["upperfirst"](value) == expected

    @pytest.mark.parametrize(
        "value, expected",
        [
            ("Main", "main"),
            ("MainBeauty", "mainBeauty"),
            ("_Shot", "_shot"),
            ("01_Shot", "01_shot"),
            ("{Aa}", "{aa}"),
            ("123", "123"),
            ("", ""),
        ],
    )
    def test_lowerfirst(self, value: str, expected: str):
        assert get_template_format_specs()["lowerfirst"](value) == expected


class TestPlaceholderValues:
    """Value that is a template key keeps it, the spec is transferred.

    Some integrations pass e.g. '{composition}' as a value to fill it later,
    the named format spec must be applied on the later formatting.
    """

    @pytest.mark.parametrize(
        "spec",
        [
            "upper",
            "lower",
            "upperfirst",
            "lowerfirst",
            "title",
            "camel",
            "pascal",
            "snake",
        ],
    )
    def test_spec_is_transferred(self, spec: str):
        result = StringTemplate(f"{{key:{spec}}}").format_strict(
            {"key": "{aaa}"}
        )
        assert str(result) == f"{{aaa:{spec}}}"

    @pytest.mark.parametrize(
        "template, value, expected",
        [
            ("{key:upper}", "{aaa}", "{aaa:upper}"),
            ("{key:upper}", "{folder[name]}", "{folder[name]:upper}"),
            (
                "{product[type]}{key:upperfirst}{variant:upperfirst}",
                "{composition}",
                "render{composition:upperfirst}Main",
            ),
            ("<_{key:upper}>", "{aaa}", "_{aaa:upper}"),
            # Placeholder that already has format spec is kept
            ("{key:upper}", "{aaa:lower}", "{aaa:lower}"),
            ("{key:upper}", "{aaa:0>3}", "{aaa:0>3}"),
            ("{key:upper}", "{aaa!r}", "{aaa!r}"),
            # Not only a placeholder, spec is applied on the value
            ("{key:upper}", "{aaa}_bbb", "{AAA}_BBB"),
            ("{key:upper}", "{aaa}{bbb}", "{AAA}{BBB}"),
            ("{key:upper}", "{{aaa}}", "{{AAA}}"),
            # Conversion is applied first, the result is not a placeholder
            ("{key!r:upper}", "{aaa}", "'{AAA}'"),
        ],
    )
    def test_placeholder(self, template: str, value: str, expected: str):
        data = _get_data()
        data["key"] = value
        assert str(StringTemplate(template).format_strict(data)) == expected

    def test_used_values(self):
        result = StringTemplate("{key:upper}").format_strict({"key": "{aaa}"})
        assert result.used_values == {"key": "{aaa}"}

    @pytest.mark.parametrize(
        "spec, expected",
        [
            ("upper", "MAINCOMP"),
            ("lower", "maincomp"),
            ("upperfirst", "MainComp"),
            ("camel", "mainComp"),
            ("snake", "main_comp"),
        ],
    )
    def test_format_later(self, spec: str, expected: str):
        """Placeholder is filled with the spec applied in second step."""
        first = StringTemplate(f"render_{{key:{spec}}}").format_strict(
            {"key": "{composition}"}
        )
        second = StringTemplate(str(first)).format_strict(
            {"composition": "mainComp"}
        )
        assert str(second) == f"render_{expected}"

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    @pytest.mark.parametrize(
        "spec, expected",
        [
            ("upper", "MAINCOMP"),
            ("upperfirst", "MainComp"),
            ("pascal", "MainComp"),
        ],
    )
    def test_format_later_with_python_formatting(
        self, spec: str, expected: str
    ):
        """Integrations fill the placeholder with python formatting.

        Values from 'prepare_template_data' support named format specs in
        python formatting.
        """
        first = StringTemplate(f"render_{{key:{spec}}}").format_strict(
            {"key": "{composition}"}
        )
        fill_data = prepare_template_data({"composition": "mainComp"})

        assert str(first).format(**fill_data) == f"render_{expected}"
        assert str(first).format_map(fill_data) == f"render_{expected}"


class TestPreparedTemplateData:
    """Values of 'prepare_template_data' in python formatting."""

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    @pytest.mark.parametrize(
        "template, expected",
        [
            ("{composition}", "mainComp"),
            ("{Composition}", "MainComp"),
            ("{COMPOSITION}", "MAINCOMP"),
            ("{composition:upperfirst}", "MainComp"),
            ("{composition:snake}", "main_comp"),
            ("{Composition:lower}", "maincomp"),
            ("{composition:>10}", "  mainComp"),
            ("{composition!r}", "'mainComp'"),
            ("{task[name]:upper}", "ANIMATION"),
            ("{version:0>3}", "003"),
        ],
    )
    def test_python_format(self, template: str, expected: str):
        data = prepare_template_data({
            "composition": "mainComp",
            "task": {"name": "animation"},
            "version": 3,
        })
        assert template.format(**data) == expected
        assert template.format_map(data) == expected

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_unknown_spec_fails_as_before(self):
        data = prepare_template_data({"composition": "mainComp"})
        with pytest.raises(ValueError):
            "{composition:unknown}".format(**data)

    @pytest.mark.filterwarnings("ignore::DeprecationWarning")
    def test_values_are_strings(self):
        data = prepare_template_data({"composition": "mainComp"})
        assert data == {
            "composition": "mainComp",
            "Composition": "MainComp",
            "COMPOSITION": "MAINCOMP",
        }
        assert all(isinstance(value, str) for value in data.values())


class TestOptionalParts:
    """Optional parts with named format specs and legacy keys."""

    @staticmethod
    def _get_data() -> dict:
        data = _get_data()
        data.pop("root")
        data["nothing"] = None
        data["task"]["short"] = None
        return data

    @pytest.mark.parametrize(
        "template, expected, used_values",
        [
            # Missing key
            ("{ext}<_{output:upper}>", "exr", {"ext": "exr"}),
            # Available key
            (
                "{ext}<_{variant:upper}>",
                "exr_MAIN",
                {"ext": "exr", "variant": "main"},
            ),
            # Whole part is skipped if one of keys is missing
            ("{ext}<_{variant:upper}_{output:lower}>", "exr", {"ext": "exr"}),
            ("{ext}<_{output:lower}_{variant:upper}>", "exr", {"ext": "exr"}),
            # Nested parts
            (
                "{ext}<_{variant:upper}<_{output:lower}>>",
                "exr_MAIN",
                {"ext": "exr", "variant": "main"},
            ),
            (
                "{ext}<_{output:lower}<_{variant:upper}>>",
                "exr",
                {"ext": "exr"},
            ),
            (
                "{ext}<_{variant:upper}<_{task[name]:pascal}<_{output}>>>",
                "exr_MAIN_Animation",
                {
                    "ext": "exr",
                    "variant": "main",
                    "task": {"name": "animation"},
                },
            ),
            # Value that cannot be formatted
            ("<{nothing:upper}_>{ext}", "exr", {"ext": "exr"}),
            ("<{task[short]:upper}_>{ext}", "exr", {"ext": "exr"}),
            ("<{project:upper}_>{ext}", "exr", {"ext": "exr"}),
            # List items
            (
                "<{tags[0]:upper}_><{tags[5]:upper}_>{ext}",
                "FIRST_exr",
                {"tags": ["first", "second"], "ext": "exr"},
            ),
            # Mixed with python format spec
            (
                "<v{version:0>3}_{variant:camel}>",
                "v003_main",
                {"version": 3, "variant": "main"},
            ),
            ("<v{version:0>3}_{output:camel}>", "", {}),
        ],
    )
    def test_named_format_specs(
        self, template: str, expected: str, used_values: dict
    ):
        result = StringTemplate(template).format_strict(self._get_data())
        assert str(result) == expected
        assert result.used_values == used_values
        assert result.missing_keys == []
        assert result.invalid_types == {}

    @pytest.mark.parametrize(
        "template, missing_keys",
        [
            ("{output:upper}<_{variant:upper}>", ["output"]),
            ("{Output}<_{Variant}>", ["Output"]),
            ("<{variant:upper}>_{task[nope]:lower}", ["task[nope]"]),
        ],
    )
    def test_required_key_is_missing(
        self, template: str, missing_keys: list
    ):
        """Filled optional part does not make the template solved."""
        result = StringTemplate(template).format(self._get_data())
        assert not result.solved
        assert result.missing_keys == missing_keys
        with pytest.raises(TemplateUnsolved):
            result.validate()


class TestRegisterFormatSpec:
    @pytest.fixture
    def registered_specs(self, monkeypatch):
        specs = dict(path_templates._FORMAT_SPECS)
        monkeypatch.setattr(path_templates, "_FORMAT_SPECS", specs)
        return specs

    def test_default_specs(self):
        assert set(get_template_format_specs()) == {
            "upper",
            "lower",
            "upperfirst",
            "lowerfirst",
            "title",
            "camel",
            "pascal",
            "snake",
        }

    def test_register(self, registered_specs):
        # Template created before the registration can use the spec
        template = StringTemplate("{variant:reverse}")
        register_template_format_spec("reverse", lambda value: value[::-1])

        assert "reverse" in get_template_format_specs()
        assert str(template.format_strict(_get_data())) == "niam"

    def test_override(self, registered_specs):
        register_template_format_spec("upper", lambda value: "overridden")
        result = StringTemplate("{variant:upper}").format(_get_data())
        assert str(result) == "overridden"

    @pytest.mark.parametrize(
        "name", ["", "s", "d", "03d", ">10", "0>3", "a b", "up:per", None]
    )
    def test_invalid_name(self, name, registered_specs):
        with pytest.raises(ValueError):
            register_template_format_spec(name, str.upper)

    def test_returned_specs_are_copy(self):
        get_template_format_specs().clear()
        assert get_template_format_specs()
