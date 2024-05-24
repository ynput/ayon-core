from typing import List

from maya import cmds


def get_yeti_user_variables(yeti_shape_node: str) -> List[str]:
    """Get user defined yeti user variables for a `pgYetiMaya` shape node.

    Arguments:
        yeti_shape_node (str): The `pgYetiMaya` shape node.

    Returns:
        list: Attribute names (for a vector attribute it only lists the top
            parent attribute, not the attribute per axis)
    """

    attrs = cmds.listAttr(yeti_shape_node,
                          userDefined=True,
                          string=("yetiVariableV_*",
                                  "yetiVariableF_*")) or []
    valid_attrs = []
    for attr in attrs:
        attr_type = cmds.attributeQuery(attr, node=yeti_shape_node,
                                        attributeType=True)
        if attr.startswith("yetiVariableV_") and attr_type == "double3":
            # vector
            valid_attrs.append(attr)
        elif attr.startswith("yetiVariableF_") and attr_type == "double":
            valid_attrs.append(attr)

    return valid_attrs


def create_yeti_variable(yeti_shape_node: str,
                         attr_name: str,
                         value=None,
                         force_value: bool = False) -> bool:
    """Get user defined yeti user variables for a `pgYetiMaya` shape node.

    Arguments:
        yeti_shape_node (str): The `pgYetiMaya` shape node.
        attr_name (str): The fully qualified yeti variable name, e.g.
            "yetiVariableF_myfloat" or "yetiVariableV_myvector"
        value (object): The value to set (must match the type of the attribute)
            When value is None it will ignored and not be set.
        force_value (bool): Whether to set the value if the attribute already
            exists or not.

    Returns:
        bool: Whether the attribute value was set or not.

    """
    exists = cmds.attributeQuery(attr_name, node=yeti_shape_node, exists=True)
    if not exists:
        if attr_name.startswith("yetiVariableV_"):
            _create_vector_yeti_user_variable(yeti_shape_node, attr_name)
        if attr_name.startswith("yetiVariableF_"):
            _create_float_yeti_user_variable(yeti_shape_node, attr_name)

    if value is not None and (not exists or force_value):
        plug = "{}.{}".format(yeti_shape_node, attr_name)
        if (
                isinstance(value, (list, tuple))
                and attr_name.startswith("yetiVariableV_")
        ):
            cmds.setAttr(plug, *value, type="double3")
        else:
            cmds.setAttr(plug, value)

        return True
    return False


def _create_vector_yeti_user_variable(yeti_shape_node: str, attr_name: str):
    if not attr_name.startswith("yetiVariableV_"):
        raise ValueError("Must start with yetiVariableV_")
    cmds.addAttr(yeti_shape_node,
                 longName=attr_name,
                 attributeType="double3",
                 cachedInternally=True,
                 keyable=True)
    for axis in "XYZ":
        cmds.addAttr(yeti_shape_node,
                     longName="{}{}".format(attr_name, axis),
                     attributeType="double",
                     parent=attr_name,
                     cachedInternally=True,
                     keyable=True)


def _create_float_yeti_user_variable(yeti_node: str, attr_name: str):
    if not attr_name.startswith("yetiVariableF_"):
        raise ValueError("Must start with yetiVariableF_")

    cmds.addAttr(yeti_node,
                 longName=attr_name,
                 attributeType="double",
                 cachedInternally=True,
                 softMinValue=0,
                 softMaxValue=100,
                 keyable=True)
