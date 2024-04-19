from qtpy import QtWidgets, QtCore
from ayon_core.pipeline import (
    load,
    get_representation_path,
)
from ayon_core.pipeline.load import LoadError
from ayon_core.hosts.substancepainter.api.pipeline import (
    imprint_container,
    set_container_metadata,
    remove_container_metadata
)

import substance_painter.project


def _convert(substance_attr):
    """Return Substance Painter Python API Project attribute from string.
    
    This converts a string like "ProjectWorkflow.Default" to for example
    the Substance Painter Python API equivalent object, like:
        `substance_painter.project.ProjectWorkflow.Default`

    Args:
        substance_attr (str): The `substance_painter.project` attribute,
            for example "ProjectWorkflow.Default"

    Returns:
        Any: Substance Python API object of the project attribute.

    Raises:
        ValueError: If attribute does not exist on the
            `substance_painter.project` python api.
    """
    root = substance_painter.project
    for attr in substance_attr.split("."):
        root = getattr(root, attr, None)
        if root is None:
            raise ValueError(
                "Substance Painter project attribute"
                f" does not exist: {substance_attr}")

    return root


def get_template_by_name(name: str, templates: list[dict]) -> dict:
    return next(
        template for template in templates
        if template["name"] == name
    )


class SubstanceProjectConfigurationWindow(QtWidgets.QDialog):
    """The pop-up dialog allows users to choose material
    duplicate options for importing Max objects when updating
    or switching assets.
    """
    def __init__(self, project_templates):
        super(SubstanceProjectConfigurationWindow, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.import_cameras = False
        self.preserve_strokes = False
        self.template_name = None
        self.template_names = [template["name"] for template
                               in project_templates]
        self.project_templates = project_templates

        self.widgets = {
            "label": QtWidgets.QLabel(
                "Select your template for project configuration"),
            "template_options": QtWidgets.QComboBox(),
            "import_cameras": QtWidgets.QCheckBox("Import Cameras"),
            "preserve_strokes": QtWidgets.QCheckBox("Preserve Strokes"),
            "clickbox": QtWidgets.QWidget(),
            "combobox": QtWidgets.QWidget(),
            "buttons": QtWidgets.QDialogButtonBox(
                QtWidgets.QDialogButtonBox.Ok
                | QtWidgets.QDialogButtonBox.Cancel)
        }
        for template in self.template_names:
            self.widgets["template_options"].addItem(template)

        template_name = self.widgets["template_options"].currentText()
        self.get_boolean_setting(template_name)
        # Build clickboxes
        layout = QtWidgets.QHBoxLayout(self.widgets["clickbox"])
        layout.addWidget(self.widgets["import_cameras"])
        layout.addWidget(self.widgets["preserve_strokes"])
        # Build combobox
        layout = QtWidgets.QHBoxLayout(self.widgets["combobox"])
        layout.addWidget(self.widgets["template_options"])

        # Build buttons
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["label"])
        layout.addWidget(self.widgets["combobox"])
        layout.addWidget(self.widgets["clickbox"])
        layout.addWidget(self.widgets["buttons"])

        self.widgets["template_options"].currentTextChanged.connect(
            self.on_options_changed)
        self.widgets["buttons"].accepted.connect(self.on_ok_pressed)
        self.widgets["buttons"].rejected.connect(self.on_cancel_pressed)

    def on_options_changed(self, value):
        self.get_boolean_setting(value)

    def on_ok_pressed(self):
        if self.widgets["import_cameras"].isChecked():
            self.import_cameras = True
        if self.widgets["preserve_strokes"].isChecked():
            self.preserve_strokes = True
        self.template_name = (
            self.widgets["template_options"].currentText()
        )
        self.close()

    def on_cancel_pressed(self):
        self.template_name = None
        self.close()

    def get_boolean_setting(self, template_name):
        self.import_cameras = next(template["import_cameras"] for
                                   template in self.project_templates
                                   if template["name"] == template_name)
        self.preserve_strokes = next(template["preserve_strokes"] for
                                     template in self.project_templates
                                     if template["name"] == template_name)
        self.widgets["import_cameras"].setChecked(self.import_cameras)
        self.widgets["preserve_strokes"].setChecked(self.preserve_strokes)

    def get_result(self):
        import copy
        templates = self.project_templates
        name = self.template_name
        if not name:
            return None
        template = get_template_by_name(name, templates)
        template = copy.deepcopy(template) # do not edit the original
        template["import_cameras"] = self.widgets["import_cameras"].isChecked()
        template["preserve_strokes"] = self.widgets["preserve_strokes"].isChecked()
        return template

    @classmethod
    def prompt(cls, templates):
        dialog = cls(templates)
        dialog.exec_()

        return dialog


class SubstanceLoadProjectMesh(load.LoaderPlugin):
    """Load mesh for project"""

    product_types = {"*"}
    representations = {"abc", "fbx", "obj", "gltf", "usd", "usda", "usdc"}

    label = "Load mesh"
    order = -10
    icon = "code-fork"
    color = "orange"
    project_templates = []

    def load(self, context, name, namespace, options=None):

        # Get user inputs
        result = SubstanceProjectConfigurationWindow.prompt(
            self.project_templates).get_result()
        if result is None:
            return
        import_cameras = result["import_cameras"]
        sp_settings = substance_painter.project.Settings(
            normal_map_format=_convert(result["normal_map_format"]),
            import_cameras=result["import_cameras"],
            project_workflow=_convert(result["project_workflow"]),
            tangent_space_mode=_convert(result["tangent_space_mode"]),
            default_texture_resolution=result["default_texture_resolution"]
        )
        if not substance_painter.project.is_open():
            # Allow to 'initialize' a new project
            path = self.filepath_from_context(context)

            settings = substance_painter.project.create(
                mesh_file_path=path, settings=sp_settings
            )
        else:
            # Reload the mesh
            preserve_strokes = result["preserve_cameras"]
            settings = substance_painter.project.MeshReloadingSettings(
                import_cameras=import_cameras,
                preserve_strokes=preserve_strokes)

            def on_mesh_reload(status: substance_painter.project.ReloadMeshStatus):  # noqa
                if status == substance_painter.project.ReloadMeshStatus.SUCCESS:  # noqa
                    self.log.info("Reload succeeded")
                else:
                    raise LoadError("Reload of mesh failed")

            path = self.filepath_from_context(context)
            substance_painter.project.reload_mesh(path,
                                                  settings,
                                                  on_mesh_reload)

        # Store container
        container = {}
        project_mesh_object_name = "_ProjectMesh_"
        imprint_container(container,
                          name=project_mesh_object_name,
                          namespace=project_mesh_object_name,
                          context=context,
                          loader=self)

        # We want store some options for updating to keep consistent behavior
        # from the user's original choice. We don't store 'preserve_strokes'
        # as we always preserve strokes on updates.
        # TODO: update the code
        container["options"] = {
            "import_cameras": import_cameras,
        }

        set_container_metadata(project_mesh_object_name, container)

    def switch(self, container, context):
        self.update(container, context)

    def update(self, container, context):
        repre_entity = context["representation"]

        path = get_representation_path(repre_entity)

        # Reload the mesh
        container_options = container.get("options", {})
        settings = substance_painter.project.MeshReloadingSettings(
            import_cameras=container_options.get("import_cameras", True),
            preserve_strokes=True
        )

        def on_mesh_reload(status: substance_painter.project.ReloadMeshStatus):
            if status == substance_painter.project.ReloadMeshStatus.SUCCESS:
                self.log.info("Reload succeeded")
            else:
                raise LoadError("Reload of mesh failed")

        substance_painter.project.reload_mesh(path, settings, on_mesh_reload)

        # Update container representation
        object_name = container["objectName"]
        update_data = {"representation": repre_entity["id"]}
        set_container_metadata(object_name, update_data, update=True)

    def remove(self, container):

        # Remove OpenPype related settings about what model was loaded
        # or close the project?
        # TODO: This is likely best 'hidden' away to the user because
        #       this will leave the project's mesh unmanaged.
        remove_container_metadata(container["objectName"])
