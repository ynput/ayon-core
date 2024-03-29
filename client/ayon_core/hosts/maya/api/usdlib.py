from openpype.pipeline.constants import AVALON_CONTAINER_ID
from pxr import Sdf

from maya import cmds


def remove_spec(spec):
    """Delete Sdf.PrimSpec or Sdf.PropertySpec

    Also see:
        https://forum.aousd.org/t/api-basics-for-designing-a-manage-edits-editor-for-usd/676/1  # noqa
        https://gist.github.com/BigRoy/4d2bf2eef6c6a83f4fda3c58db1489a5

    """
    if spec.expired:
        return

    if isinstance(spec, Sdf.PrimSpec):
        # PrimSpec
        parent = spec.nameParent
        if parent:
            view = parent.nameChildren
        else:
            # Assume PrimSpec is root prim
            view = spec.layer.rootPrims
        del view[spec.name]

    elif isinstance(spec, Sdf.PropertySpec):
        # Relationship and Attribute specs
        del spec.owner.properties[spec.name]
    else:
        raise TypeError(f"Unsupported spec type: {spec}")


def iter_ufe_usd_selection():
    """Yield Maya USD Proxy Shape related UFE paths in selection.

    The returned path are the Maya node name joined by a command to the
    USD prim path.

    Yields:
        str: Path to UFE path in USD stage in selection.

    """
    for path in cmds.ls(selection=True, ufeObjects=True, long=True,
                        absoluteName=True):
        if "," not in path:
            continue

        node, ufe_path = path.split(",", 1)
        if cmds.nodeType(node) != "mayaUsdProxyShape":
            continue

        yield path


def containerise_prim(prim,
                      name,
                      namespace,
                      context,
                      loader):
    """Containerise a USD prim.

    Arguments:
        prim (pxr.Usd.Prim): The prim to containerise.
        name (str): Name to containerize.
        namespace (str): Name to containerize.
        context (dict): Name to containerize.
        name (str): Name to containerize.
        name (str): Name to containerize.

    """
    for key, value in {
        "ayon:schema": "openpype:container-2.0",
        "ayon:id": AVALON_CONTAINER_ID,
        "ayon:name": name,
        "ayon:namespace": namespace,
        "ayon:loader": loader,
        "ayon:representation": context["representation"]["id"],
    }.items():
        prim.SetCustomDataByKey(key, str(value))
