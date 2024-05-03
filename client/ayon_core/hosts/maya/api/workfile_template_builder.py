from maya import cmds

from ayon_core.pipeline import (
    registered_host,
    get_current_folder_path,
    AYON_INSTANCE_ID,
    AVALON_INSTANCE_ID,
)
from ayon_core.pipeline.workfile.workfile_template_builder import (
    TemplateAlreadyImported,
    AbstractTemplateBuilder
)
from ayon_core.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)

from .lib import get_main_window

PLACEHOLDER_SET = "PLACEHOLDERS_SET"


class MayaTemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for maya"""

    use_legacy_creators = True

    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """

        if cmds.objExists(PLACEHOLDER_SET):
            raise TemplateAlreadyImported((
                "Build template already loaded\n"
                "Clean scene if needed (File > New Scene)"
            ))

        cmds.sets(name=PLACEHOLDER_SET, empty=True)
        new_nodes = cmds.file(
            path,
            i=True,
            returnNewNodes=True,
            preserveReferences=True,
            loadReferenceDepth="all",
        )

        # make default cameras non-renderable
        default_cameras = [cam for cam in cmds.ls(cameras=True)
                           if cmds.camera(cam, query=True, startupCamera=True)]
        for cam in default_cameras:
            if not cmds.attributeQuery("renderable", node=cam, exists=True):
                self.log.debug(
                    "Camera {} has no attribute 'renderable'".format(cam)
                )
                continue
            cmds.setAttr("{}.renderable".format(cam), 0)

        cmds.setAttr(PLACEHOLDER_SET + ".hiddenInOutliner", True)

        imported_sets = cmds.ls(new_nodes, set=True)
        if not imported_sets:
            return True

        # update imported sets information
        folder_path = get_current_folder_path()
        for node in imported_sets:
            if not cmds.attributeQuery("id", node=node, exists=True):
                continue
            if cmds.getAttr("{}.id".format(node)) not in {
                AYON_INSTANCE_ID, AVALON_INSTANCE_ID
            }:
                continue
            if not cmds.attributeQuery("folderPath", node=node, exists=True):
                continue

            cmds.setAttr(
                "{}.folderPath".format(node), folder_path, type="string")

        return True


def build_workfile_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.build_template()


def update_workfile_template(*args):
    builder = MayaTemplateBuilder(registered_host())
    builder.rebuild_template()


def create_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=get_main_window())
    window.show()


def update_placeholder(*args):
    host = registered_host()
    builder = MayaTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node_name in cmds.ls(selection=True, long=True):
        if node_name in placeholder_items_by_id:
            placeholder_items.append(placeholder_items_by_id[node_name])

    # TODO show UI at least
    if len(placeholder_items) == 0:
        raise ValueError("No node selected")

    if len(placeholder_items) > 1:
        raise ValueError("Too many selected nodes")

    placeholder_item = placeholder_items[0]
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=get_main_window())
    window.set_update_mode(placeholder_item)
    window.exec_()
