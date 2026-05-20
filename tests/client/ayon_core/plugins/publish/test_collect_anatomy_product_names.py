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


def test_fill_latest_versions_raises_before_get_products():
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
            plugin.fill_latest_versions(context, "test_project")

        mock_api.get_products.assert_not_called()
        assert "Main_Smoke B - long_Fx_workfile" in str(exc_info.value)
