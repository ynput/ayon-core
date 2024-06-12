import re

from ayon_core.pipeline import LoaderPlugin
from .launch_logic import stub


def get_unique_layer_name(layers, container_name, product_name):
    """Prepare unique layer name.

    Gets all layer names and if '<container_name>_<product_name>' is present,
    it adds suffix '1', or increases the suffix by 1.

    Args:
        layers (list) of dict with layers info (name, id etc.)
        container_name (str):
        product_name (str):

    Returns:
        str: name_00X (without version)
    """
    name = "{}_{}".format(container_name, product_name)
    names = {}
    for layer in layers:
        layer_name = re.sub(r'_\d{3}$', '', layer.name)
        if layer_name in names.keys():
            names[layer_name] = names[layer_name] + 1
        else:
            names[layer_name] = 1
    occurrences = names.get(name, 0)

    return "{}_{:0>3d}".format(name, occurrences + 1)


class PhotoshopLoader(LoaderPlugin):
    @staticmethod
    def get_stub():
        return stub()
