"""Tests for product-name guard in CollectAnatomyInstanceData."""

from unittest.mock import MagicMock, patch

import pytest

from ayon_core.pipeline.publish import PublishXmlValidationError
from ayon_core.plugins.publish.collect_anatomy_instance_data import (
    CollectAnatomyInstanceData,
)


class FakeInstance:
    def __init__(self, data):
        self.data = data


class FakeContext(list):
    def __init__(self, instances, project_name="test_project"):
        super().__init__(instances)
        self.data = {"projectName": project_name}


def test_raise_if_invalid_product_names_before_graphql():
    context = FakeContext(
        [
            FakeInstance(
                {
                    "folderEntity": {"id": "folder-1"},
                    "productType": "workfile",
                    "productName": "Main_Smoke B - long_Fx_workfile",
                    "workfileSubversion": "Smoke B - long",
                }
            ),
        ]
    )
    plugin = CollectAnatomyInstanceData()
    plugin.log = MagicMock()

    with patch("ayon_core.plugins.publish.collect_anatomy_instance_data.ayon_api") as mock_api:
        with pytest.raises(PublishXmlValidationError) as exc_info:
            plugin._raise_if_invalid_product_names(context)

        mock_api.get_products.assert_not_called()
        assert exc_info.value.title == "Workfile name not allowed"
        assert "Main_Smoke B - long_Fx_workfile" in exc_info.value.description
        assert "Smoke_B_-_long" in exc_info.value.description


def test_process_raises_before_folder_queries():
    context = FakeContext(
        [
            FakeInstance(
                {
                    "folderEntity": {"id": "folder-1"},
                    "productType": "workfile",
                    "productName": "Main_Smoke B - long_Fx_workfile",
                    "workfileSubversion": "Smoke B - long",
                }
            ),
        ]
    )
    plugin = CollectAnatomyInstanceData()
    plugin.log = MagicMock()

    with patch.object(plugin, "fill_missing_folder_entities") as mock_folders:
        with pytest.raises(PublishXmlValidationError):
            plugin.process(context)

        mock_folders.assert_not_called()
