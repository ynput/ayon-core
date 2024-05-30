import collections
import nuke

from ayon_core.pipeline import registered_host
from ayon_core.pipeline.workfile.workfile_template_builder import (
    AbstractTemplateBuilder,
    PlaceholderPlugin,
)
from ayon_core.tools.workfile_template_build import (
    WorkfileBuildPlaceholderDialog,
)
from .lib import (
    imprint,
    reset_selection,
    get_main_window,
    WorkfileSettings,
)

PLACEHOLDER_SET = "PLACEHOLDERS_SET"


class NukeTemplateBuilder(AbstractTemplateBuilder):
    """Concrete implementation of AbstractTemplateBuilder for nuke"""

    def import_template(self, path):
        """Import template into current scene.
        Block if a template is already loaded.

        Args:
            path (str): A path to current template (usually given by
            get_template_preset implementation)

        Returns:
            bool: Whether the template was successfully imported or not
        """

        # TODO check if the template is already imported

        nuke.nodePaste(path)
        reset_selection()

        return True


class NukePlaceholderPlugin(PlaceholderPlugin):
    node_color = 4278190335

    def _collect_scene_placeholders(self):
        # Cache placeholder data to shared data
        placeholder_nodes = self.builder.get_shared_populate_data(
            "placeholder_nodes"
        )
        if placeholder_nodes is None:
            placeholder_nodes = {}
            all_groups = collections.deque()
            all_groups.append(nuke.thisGroup())
            while all_groups:
                group = all_groups.popleft()
                for node in group.nodes():
                    if isinstance(node, nuke.Group):
                        all_groups.append(node)

                    node_knobs = node.knobs()
                    if (
                        "is_placeholder" not in node_knobs
                        or not node.knob("is_placeholder").value()
                    ):
                        continue

                    if "empty" in node_knobs and node.knob("empty").value():
                        continue

                    placeholder_nodes[node.fullName()] = node

            self.builder.set_shared_populate_data(
                "placeholder_nodes", placeholder_nodes
            )
        return placeholder_nodes

    def create_placeholder(self, placeholder_data):
        placeholder_data["plugin_identifier"] = self.identifier

        placeholder = nuke.nodes.NoOp()
        placeholder.setName("PLACEHOLDER")
        placeholder.knob("tile_color").setValue(self.node_color)

        imprint(placeholder, placeholder_data)
        imprint(placeholder, {"is_placeholder": True})
        placeholder.knob("is_placeholder").setVisible(False)

    def update_placeholder(self, placeholder_item, placeholder_data):
        node = nuke.toNode(placeholder_item.scene_identifier)
        imprint(node, placeholder_data)

    def _parse_placeholder_node_data(self, node):
        placeholder_data = {}
        for key in self.get_placeholder_keys():
            knob = node.knob(key)
            value = None
            if knob is not None:
                value = knob.getValue()
            placeholder_data[key] = value
        return placeholder_data

    def delete_placeholder(self, placeholder):
        """Remove placeholder if building was successful"""
        placeholder_node = nuke.toNode(placeholder.scene_identifier)
        nuke.delete(placeholder_node)


def build_workfile_template(*args, **kwargs):
    builder = NukeTemplateBuilder(registered_host())
    builder.build_template(*args, **kwargs)

    # set all settings to shot context default
    WorkfileSettings().set_context_settings()


def update_workfile_template(*args):
    builder = NukeTemplateBuilder(registered_host())
    builder.rebuild_template()


def create_placeholder(*args):
    host = registered_host()
    builder = NukeTemplateBuilder(host)
    window = WorkfileBuildPlaceholderDialog(host, builder,
                                            parent=get_main_window())
    window.show()


def update_placeholder(*args):
    host = registered_host()
    builder = NukeTemplateBuilder(host)
    placeholder_items_by_id = {
        placeholder_item.scene_identifier: placeholder_item
        for placeholder_item in builder.get_placeholders()
    }
    placeholder_items = []
    for node in nuke.selectedNodes():
        node_name = node.fullName()
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
