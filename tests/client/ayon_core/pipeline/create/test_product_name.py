"""Tests for product_name helpers."""
import pytest
from unittest.mock import patch

from ayon_core.pipeline.create.product_name import (
    get_product_name_template,
    get_product_name,
)
from ayon_core.pipeline.create.constants import DEFAULT_PRODUCT_TEMPLATE
from ayon_core.pipeline.create.exceptions import (
    TaskNotSetError,
    TemplateFillError,
)


class TestGetProductNameTemplate:
    @patch("ayon_core.pipeline.create.product_name.get_project_settings")
    @patch("ayon_core.pipeline.create.product_name.filter_profiles")
    @patch("ayon_core.pipeline.create.product_name."
           "is_product_base_type_supported")
    def test_matching_profile_with_replacements(
        self,
        mock_filter_profiles,
        mock_get_settings,
    ):
        """Matching profile applies legacy replacement tokens."""
        mock_get_settings.return_value = {
            "core": {"tools": {"creator": {"product_name_profiles": []}}}
        }
        # The function should replace {task}/{family}/{asset} variants
        mock_filter_profiles.return_value = {
            "template": ("{task}-{Task}-{TASK}-{family}-{Family}"
                        "-{FAMILY}-{asset}-{Asset}-{ASSET}")
        }

        result = get_product_name_template(
            project_name="proj",
            product_type="model",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
        )
        assert result == (
            "{task[name]}-{Task[name]}-{TASK[NAME]}-"
            "{product[type]}-{Product[type]}-{PRODUCT[TYPE]}-"
            "{folder[name]}-{Folder[name]}-{FOLDER[NAME]}"
        )

    @patch("ayon_core.pipeline.create.product_name.get_project_settings")
    @patch("ayon_core.pipeline.create.product_name.filter_profiles")
    @patch("ayon_core.pipeline.create.product_name."
           "is_product_base_type_supported")
    def test_no_matching_profile_uses_default(
        self,
        mock_filter_profiles,
        mock_get_settings,
    ):
        mock_get_settings.return_value = {
            "core": {"tools": {"creator": {"product_name_profiles": []}}}
        }
        mock_filter_profiles.return_value = None

        assert (
            get_product_name_template(
                project_name="proj",
                product_type="model",
                task_name="modeling",
                task_type="Modeling",
                host_name="maya",
            )
            == DEFAULT_PRODUCT_TEMPLATE
        )

    @patch("ayon_core.pipeline.create.product_name.get_project_settings")
    @patch("ayon_core.pipeline.create.product_name.filter_profiles")
    @patch("ayon_core.pipeline.create.product_name."
           "is_product_base_type_supported")
    def test_custom_default_template_used(
        self,
        mock_filter_profiles,
        mock_get_settings,
    ):
        mock_get_settings.return_value = {
            "core": {"tools": {"creator": {"product_name_profiles": []}}}
        }
        mock_filter_profiles.return_value = None

        custom_default = "{variant}_{family}"
        assert (
            get_product_name_template(
                project_name="proj",
                product_type="model",
                task_name="modeling",
                task_type="Modeling",
                host_name="maya",
                default_template=custom_default,
            )
            == custom_default
        )

    @patch("ayon_core.pipeline.create.product_name.warn")
    @patch("ayon_core.pipeline.create.product_name.get_project_settings")
    @patch("ayon_core.pipeline.create.product_name.filter_profiles")
    @patch("ayon_core.pipeline.create.product_name."
           "is_product_base_type_supported")
    def test_product_base_type_warns_when_supported_and_missing(
        self,
        mock_filter_profiles,
        mock_get_settings,
        mock_warn,
    ):
        mock_get_settings.return_value = {
            "core": {"tools": {"creator": {"product_name_profiles": []}}}
        }
        mock_filter_profiles.return_value = None

        get_product_name_template(
            project_name="proj",
            product_type="model",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
        )
        mock_warn.assert_called_once()

    @patch("ayon_core.pipeline.create.product_name.get_project_settings")
    @patch("ayon_core.pipeline.create.product_name.filter_profiles")
    @patch("ayon_core.pipeline.create.product_name."
           "is_product_base_type_supported")
    def test_product_base_type_added_to_filtering_when_provided(
        self,
        mock_filter_profiles,
        mock_get_settings,
    ):
        mock_get_settings.return_value = {
            "core": {"tools": {"creator": {"product_name_profiles": []}}}
        }
        mock_filter_profiles.return_value = None

        get_product_name_template(
            project_name="proj",
            product_type="model",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_base_type="asset",
        )
        args, kwargs = mock_filter_profiles.call_args
        # args[1] is filtering_criteria
        assert args[1]["product_base_types"] == "asset"


class TestGetProductName:
    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name."
           "StringTemplate.format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_empty_product_type_returns_empty(
        self, mock_prepare, mock_format, mock_get_tmpl
    ):
        assert (
            get_product_name(
                project_name="proj",
                task_name="modeling",
                task_type="Modeling",
                host_name="maya",
                product_type="",
                variant="Main",
            )
            == ""
        )
        mock_get_tmpl.assert_not_called()
        mock_format.assert_not_called()
        mock_prepare.assert_not_called()

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name."
           "StringTemplate.format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_happy_path(
        self, mock_prepare, mock_format, mock_get_tmpl
    ):
        mock_get_tmpl.return_value = "{task[name]}_{product[type]}_{variant}"
        mock_prepare.return_value = {
            "task": {"name": "modeling"},
            "product": {"type": "model"},
            "variant": "Main",
            "family": "model",
        }
        mock_format.return_value = "modeling_model_Main"

        result = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            variant="Main",
        )
        assert result == "modeling_model_Main"
        mock_get_tmpl.assert_called_once()
        mock_prepare.assert_called_once()
        mock_format.assert_called_once()

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name."
           "StringTemplate.format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_product_name_with_base_type(
        self, mock_prepare, mock_format, mock_get_tmpl
    ):
        mock_get_tmpl.return_value = (
            "{task[name]}_{product[basetype]}_{variant}"
        )
        mock_prepare.return_value = {
            "task": {"name": "modeling"},
            "product": {"type": "model"},
            "variant": "Main",
            "family": "model",
        }
        mock_format.return_value = "modeling_modelBase_Main"

        result = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            product_base_type="modelBase",
            variant="Main",
        )
        assert result == "modeling_modelBase_Main"
        mock_get_tmpl.assert_called_once()
        mock_prepare.assert_called_once()
        mock_format.assert_called_once()

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    def test_task_required_but_missing_raises(self, mock_get_tmpl):
        mock_get_tmpl.return_value = "{task[name]}_{variant}"
        with pytest.raises(TaskNotSetError):
            get_product_name(
                project_name="proj",
                task_name="",
                task_type="Modeling",
                host_name="maya",
                product_type="model",
                variant="Main",
            )

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name.ayon_api.get_project")
    @patch("ayon_core.pipeline.create.product_name.StringTemplate."
           "format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_task_short_name_is_used(
        self, mock_prepare, mock_format, mock_get_project, mock_get_tmpl
    ):
        mock_get_tmpl.return_value = "{task[short]}_{variant}"
        mock_get_project.return_value = {
            "taskTypes": [{"name": "Modeling", "shortName": "mdl"}]
        }
        mock_prepare.return_value = {
            "task": {
                "short": "mdl"
            },
            "variant": "Main"
        }
        mock_format.return_value = "mdl_Main"

        result = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            variant="Main",
        )
        assert result == "mdl_Main"

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name.StringTemplate."
           "format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_template_fill_error_translated(
        self, mock_prepare, mock_format, mock_get_tmpl
    ):
        mock_get_tmpl.return_value = "{missing_key}_{variant}"
        mock_prepare.return_value = {"variant": "Main"}
        mock_format.side_effect = KeyError("missing_key")
        with pytest.raises(TemplateFillError):
            get_product_name(
                project_name="proj",
                task_name="modeling",
                task_type="Modeling",
                host_name="maya",
                product_type="model",
                variant="Main",
            )

    @patch("ayon_core.pipeline.create.product_name.warn")
    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name."
           "StringTemplate.format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_warns_when_template_needs_base_type_but_missing(
        self,
        mock_prepare,
        mock_format,
        mock_get_tmpl,
        mock_warn,
    ):
        mock_get_tmpl.return_value = "{product[basetype]}_{variant}"

        mock_prepare.return_value = {
            "product": {"type": "model"},
            "variant": "Main",
            "family": "model",
        }
        mock_format.return_value = "asset_Main"

        _ = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            variant="Main",
        )
        mock_warn.assert_called_once()

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    @patch("ayon_core.pipeline.create.product_name."
           "StringTemplate.format_strict_template")
    @patch("ayon_core.pipeline.create.product_name.prepare_template_data")
    def test_dynamic_data_overrides_defaults(
        self, mock_prepare, mock_format, mock_get_tmpl
    ):
        mock_get_tmpl.return_value = "{custom}_{variant}"
        mock_prepare.return_value = {"custom": "overridden", "variant": "Main"}
        mock_format.return_value = "overridden_Main"

        result = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            variant="Main",
            dynamic_data={"custom": "overridden"},
        )
        assert result == "overridden_Main"

    @patch("ayon_core.pipeline.create.product_name.get_product_name_template")
    def test_product_type_filter_is_used(self, mock_get_tmpl):
        mock_get_tmpl.return_value = DEFAULT_PRODUCT_TEMPLATE
        _ = get_product_name(
            project_name="proj",
            task_name="modeling",
            task_type="Modeling",
            host_name="maya",
            product_type="model",
            variant="Main",
            product_type_filter="look",
        )
        args, kwargs = mock_get_tmpl.call_args
        assert kwargs["product_type"] == "look"
