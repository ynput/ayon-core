import unittest

from ayon_core.lib.transcoding import (
    get_review_info_by_layer_name
)


class GetReviewInfoByLayerName(unittest.TestCase):
    """Test responses from `get_review_info_by_layer_name`"""
    def test_rgba_channels(self):

        # RGB is supported
        info = get_review_info_by_layer_name(["R", "G", "B"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "R",
                "G": "G",
                "B": "B",
                "A": None,
            }
        }])

        # rgb is supported
        info = get_review_info_by_layer_name(["r", "g", "b"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "r",
                "G": "g",
                "B": "b",
                "A": None,
            }
        }])

        # diffuse.[RGB] is supported
        info = get_review_info_by_layer_name(
            ["diffuse.R", "diffuse.G", "diffuse.B"]
        )
        self.assertEqual(info, [{
            "name": "diffuse",
            "review_channels": {
                "R": "diffuse.R",
                "G": "diffuse.G",
                "B": "diffuse.B",
                "A": None,
            }
        }])

        info = get_review_info_by_layer_name(["R", "G", "B", "A"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "R",
                "G": "G",
                "B": "B",
                "A": "A",
            }
        }])

    def test_z_channel(self):

        info = get_review_info_by_layer_name(["Z"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "Z",
                "G": "Z",
                "B": "Z",
                "A": None,
            }
        }])

        info = get_review_info_by_layer_name(["Z", "A"])
        self.assertEqual(info, [{
            "name": "",
            "review_channels": {
                "R": "Z",
                "G": "Z",
                "B": "Z",
                "A": "A",
            }
        }])


    def test_unknown_channels(self):
        info = get_review_info_by_layer_name(["hello", "world"])
        self.assertEqual(info, [])

    def test_rgba_priority(self):
        """Ensure main layer, and RGB channels are prioritized

        If both Z and RGB channels are present for a layer name, then RGB
        should be prioritized and the Z channel should be ignored.

        Also, the alpha channel from another "layer name" is not used. Note
        how the diffuse response does not take A channel from the main layer.

        """

        info = get_review_info_by_layer_name([
            "Z",
            "diffuse.R", "diffuse.G", "diffuse.B",
            "R", "G", "B", "A",
            "specular.R", "specular.G", "specular.B", "specular.A",
        ])
        self.assertEqual(info, [
            {
                "name": "",
                "review_channels": {
                    "R": "R",
                    "G": "G",
                    "B": "B",
                    "A": "A",
                },
            },
            {
                "name": "diffuse",
                "review_channels": {
                    "R": "diffuse.R",
                    "G": "diffuse.G",
                    "B": "diffuse.B",
                    "A": None,
                },
            },
            {
                "name": "specular",
                "review_channels": {
                    "R": "specular.R",
                    "G": "specular.G",
                    "B": "specular.B",
                    "A": "specular.A",
                },
            },
        ])
