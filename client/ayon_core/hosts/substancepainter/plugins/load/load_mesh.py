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


def _convert(subst_attr):
    """Function to convert substance C++ objects to python instance.
    It is made to avoid any possible ValueError when C++ objects casting
    as python instance.

    Args:
        subst_attr (str): Substance attributes

    Raises:
        ValueError: Raise Error when unsupported Substance
            Project was detected

    Returns:
        python instance: converted python instance of the C++ objects.
    """
    if subst_attr in {"Default", "UVTile", "TextureSetPerUVTile"}:
        return getattr(substance_painter.project.ProjectWorkflow, subst_attr)
    elif subst_attr in {"PerFragment", "PerVertex"}:
        return getattr(substance_painter.project.TangentSpace, subst_attr)
    elif subst_attr in {"DirectX", "OpenGL"}:
        return getattr(substance_painter.project.NormalMapFormat, subst_attr)
    else:
        raise ValueError(
            f"Unsupported Substance Objects: {subst_attr}")


def parse_substance_attributes_setting(template_name, project_templates):
    """Function to parse the dictionary from the AYON setting to be used
    as the attributes for Substance Project Creation

    Args:
        template_name (str): name of the template from the setting
        project_templates (dict): project template data from the setting

    Returns:
        dict: data to be used as attributes for Substance Project Creation
    """
    attributes_data = {}
    for template in project_templates:
        if template["name"] == template_name:
            attributes_data.update(template)
    attributes_data["normal_map_format"] = _convert(
        attributes_data["normal_map_format"])
    attributes_data["project_workflow"] = _convert(
        attributes_data["project_workflow"])
    attributes_data["tangent_space_mode"] = _convert(
        attributes_data["tangent_space_mode"])
    attributes_data.pop("name")
    attributes_data.pop("preserve_strokes")
    return attributes_data


def parse_subst_attrs_reloading_mesh(template_name, project_templates):
    """Function to parse the substances attributes ('import_cameras'
        and 'preserve_strokes') for reloading mesh
        with the existing projects.

    Args:
        template_name (str): name of the template from the setting
        project_templates (dict): project template data from the setting

    Returns:
        dict: data to be used as attributes for reloading mesh with the
            existing project
    """
    attributes_data = {}
    for template in project_templates:
        if template["name"] == template_name:
            for key, value in template.items():
                if isinstance(value, bool):
                    attributes_data.update({key: value})
    return attributes_data


class SubstanceProjectConfigurationWindow(QtWidgets.QDialog):
    """The pop-up dialog allows users to choose material
    duplicate options for importing Max objects when updating
    or switching assets.
    """
    def __init__(self, project_templates):
        super(SubstanceProjectConfigurationWindow, self).__init__()
        self.setWindowFlags(self.windowFlags() | QtCore.Qt.FramelessWindowHint)

        self.template_name = None
        self.project_templates = project_templates

        self.widgets = {
            "label": QtWidgets.QLabel("Project Configuration"),
            "template_options": QtWidgets.QComboBox(),
            "buttons": QtWidgets.QWidget(),
            "okButton": QtWidgets.QPushButton("Ok"),
        }
        for template in project_templates:
            self.widgets["template_options"].addItem(template)
        # Build buttons.
        layout = QtWidgets.QHBoxLayout(self.widgets["buttons"])
        layout.addWidget(self.widgets["template_options"])
        layout.addWidget(self.widgets["okButton"])
        # Build layout.
        layout = QtWidgets.QVBoxLayout(self)
        layout.addWidget(self.widgets["label"])
        layout.addWidget(self.widgets["buttons"])

        self.widgets["okButton"].pressed.connect(self.on_ok_pressed)

    def on_ok_pressed(self):
        self.template_name = (
            self.widgets["template_options"].currentText()
        )
        self.close()


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
        template_enum = [template["name"] for template in self.project_templates]
        window = SubstanceProjectConfigurationWindow(template_enum)
        window.exec_()
        template_name = window.template_name

        template_settings = parse_substance_attributes_setting(
            template_name, self.project_templates)
        sp_settings = substance_painter.project.Settings(**template_settings)
        if not substance_painter.project.is_open():
            # Allow to 'initialize' a new project
            path = self.filepath_from_context(context)

            settings = substance_painter.project.create(
                mesh_file_path=path, settings=sp_settings
            )
        else:
            # Reload the mesh
            mesh_settings = parse_subst_attrs_reloading_mesh(
                template_name, self.project_templates)
            # TODO: fix the hardcoded when the preset setting in SP addon.
            settings = substance_painter.project.MeshReloadingSettings(**mesh_settings)

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
            "import_cameras": template_settings["import_cameras"],
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
