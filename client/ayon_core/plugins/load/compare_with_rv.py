import qargparse

from ayon_core.pipeline import load


class CompareWithRV(load.LoaderPlugin):
    """Compare Containers in RV."""
    enabled=False

    product_types = ["render", "review", "plate"]
    representations = ["*"]
    extensions = ["*"]

    label = "Compare with RV"
    order = -10
    icon = "play-circle"
    color = "orange"

    options = [
        qargparse.Choice(
            "version_to_compare",
            label="Select version to compare to",
            items=["1", "2", "3", "4"],
            default="1",
            help="Which version to you want to compare to?"
        ),
        qargparse.Boolean(
            "shall_load_plate",
            label="Load Plate",
            default=False,
            help="Loads the main plate aswell"
        ),
    ]

    def load(self, context, name, namespace, data):
        raise NotImplementedError("Sorry not done yet :/")
