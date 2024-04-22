import os
from qtpy import QtWidgets, QtCore
from ayon_core.lib.attribute_definitions import EnumDef
from ayon_core.hosts.max.api import lib
from ayon_core.hosts.max.api.lib import (
    unique_namespace,
    get_namespace,
    object_transform_set,
    is_headless
)
from ayon_core.hosts.max.api.pipeline import (
    containerise, get_previous_loaded_object,
    update_custom_attribute_data,
    remove_container_data
)
from ayon_core.pipeline import get_representation_path, load


class MaterialDupOptionsWindow(QtWidgets.QDialog):
    """The pop-up dialog allows users to choose material
    duplicate options for importing Max objects when updating
    or switching assets.
    """
    def __init__(self, material_options):
        super(MaterialDupOptionsWindow, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.material_option = None
        self.material_options = material_options

        self.widgets = {
            "label": QtWidgets.QLabel(
                "Select material duplicate options before loading the max scene."),
            "material_options_list": QtWidgets.QListWidget(),
            "warning": QtWidgets.QLabel("No material options selected!"),
            "buttons": QtWidgets.QWidget(),
            "okButton": QtWidgets.QPushButton("Ok"),
            "cancelButton": QtWidgets.QPushButton("Cancel")
        }
        for key, value in material_options.items():
            item = QtWidgets.QListWidgetItem(value)
            self.widgets["material_options_list"].addItem(item)
            item.setData(QtCore.Qt.UserRole, key)
        # Build buttons.
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        layout.addWidget(self.widgets["okButton"])
        layout.addWidget(self.widgets["cancelButton"])
        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["label"])
        layout.addWidget(self.widgets["material_options_list"])
        layout.addWidget(self.widgets["buttons"])

        self.widgets["okButton"].pressed.connect(self.on_ok_pressed)
        self.widgets["cancelButton"].pressed.connect(self.on_cancel_pressed)
        self.widgets["material_options_list"].itemPressed.connect(
            self.on_material_options_pressed)

    def on_material_options_pressed(self, item):
        self.material_option = item.data(QtCore.Qt.UserRole)

    def on_ok_pressed(self):
        if self.material_option is None:
            self.widgets["warning"].setVisible(True)
            return
        self.close()

    def on_cancel_pressed(self):
        self.material_option = "promptMtlDups"
        self.close()

class MaxSceneLoader(load.LoaderPlugin):
    """Max Scene Loader."""

    product_types = {
        "camera",
        "maxScene",
        "model",
    }

    representations = {"max"}
    order = -8
    icon = "code-fork"
    color = "green"
    mtl_dup_default = "promptMtlDups"
    mtl_dup_enum_dict = {
        "promptMtlDups": "Prompt on Duplicate Materials",
        "useMergedMtlDups": "Use Incoming Material",
        "useSceneMtlDups": "Use Scene Material",
        "renameMtlDups": "Merge and Rename Incoming Material"
        }
    @classmethod
    def get_options(cls, contexts):
        return [
            EnumDef("mtldup",
                    items=cls.mtl_dup_enum_dict,
                    default=cls.mtl_dup_default,
                    label="Material Duplicate Options")
        ]

    def load(self, context, name=None, namespace=None, options=None):
        from pymxs import runtime as rt
        mat_dup_options = options.get("mtldup", self.mtl_dup_default)
        path = self.filepath_from_context(context)
        path = os.path.normpath(path)
        # import the max scene by using "merge file"
        path = path.replace('\\', '/')
        rt.MergeMaxFile(path, rt.Name(mat_dup_options),
                        quiet=True, includeFullGroup=True)
        max_objects = rt.getLastMergedNodes()
        max_object_names = [obj.name for obj in max_objects]
        # implement the OP/AYON custom attributes before load
        max_container = []
        namespace = unique_namespace(
            name + "_",
            suffix="_",
        )
        for max_obj, obj_name in zip(max_objects, max_object_names):
            max_obj.name = f"{namespace}:{obj_name}"
            max_container.append(rt.getNodeByName(max_obj.name))
        return containerise(
            name, max_container, context,
            namespace, loader=self.__class__.__name__)

    def update(self, container, context):
        from pymxs import runtime as rt

        repre_entity = context["representation"]
        path = get_representation_path(repre_entity)
        node_name = container["instance_node"]
        node = rt.getNodeByName(node_name)
        namespace, _ = get_namespace(node_name)
        # delete the old container with attribute
        # delete old duplicate
        # use the modifier OP data to delete the data
        node_list = get_previous_loaded_object(node)
        rt.select(node_list)
        prev_max_objects = rt.GetCurrentSelection()
        transform_data = object_transform_set(prev_max_objects)

        for prev_max_obj in prev_max_objects:
            if rt.isValidNode(prev_max_obj):  # noqa
                rt.Delete(prev_max_obj)
        material_option = self.mtl_dup_default
        if not is_headless():
            window = MaterialDupOptionsWindow(self.mtl_dup_enum_dict)
            window.exec_()
            material_option = window.material_option
        rt.MergeMaxFile(path, rt.Name(material_option), quiet=True)

        current_max_objects = rt.getLastMergedNodes()

        current_max_object_names = [obj.name for obj
                                    in current_max_objects]

        max_objects = []
        for max_obj, obj_name in zip(current_max_objects,
                                     current_max_object_names):
            max_obj.name = f"{namespace}:{obj_name}"
            max_objects.append(max_obj)
            max_transform = f"{max_obj.name}.transform"
            if max_transform in transform_data.keys():
                max_obj.pos = transform_data[max_transform] or 0
                max_obj.scale = transform_data[
                    f"{max_obj.name}.scale"] or 0

        update_custom_attribute_data(node, max_objects)
        lib.imprint(container["instance_node"], {
            "representation": repre_entity["id"]
        })

    def switch(self, container, context):
        self.update(container, context)

    def remove(self, container):
        from pymxs import runtime as rt
        node = rt.GetNodeByName(container["instance_node"])
        remove_container_data(node)
