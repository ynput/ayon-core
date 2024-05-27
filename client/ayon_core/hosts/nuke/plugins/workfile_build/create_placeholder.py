import nuke

from ayon_core.pipeline.workfile.workfile_template_builder import (
    CreatePlaceholderItem,
    PlaceholderCreateMixin,
)
from ayon_core.hosts.nuke.api.lib import (
    find_free_space_to_paste_nodes,
    get_extreme_positions,
    get_group_io_nodes,
    imprint,
    refresh_node,
    refresh_nodes,
    reset_selection,
    get_names_from_nodes,
    get_nodes_by_names,
    select_nodes,
    duplicate_node,
    node_tempfile,
)
from ayon_core.hosts.nuke.api.workfile_template_builder import (
    NukePlaceholderPlugin
)


class NukePlaceholderCreatePlugin(
    NukePlaceholderPlugin, PlaceholderCreateMixin
):
    identifier = "nuke.create"
    label = "Nuke create"

    def _parse_placeholder_node_data(self, node):
        placeholder_data = super(
            NukePlaceholderCreatePlugin, self
        )._parse_placeholder_node_data(node)

        node_knobs = node.knobs()
        nb_children = 0
        if "nb_children" in node_knobs:
            nb_children = int(node_knobs["nb_children"].getValue())
        placeholder_data["nb_children"] = nb_children

        siblings = []
        if "siblings" in node_knobs:
            siblings = node_knobs["siblings"].values()
        placeholder_data["siblings"] = siblings

        node_full_name = node.fullName()
        placeholder_data["group_name"] = node_full_name.rpartition(".")[0]
        placeholder_data["last_loaded"] = []
        placeholder_data["delete"] = False
        return placeholder_data

    def _before_instance_create(self, placeholder):
        placeholder.data["nodes_init"] = nuke.allNodes()

    def collect_placeholders(self):
        output = []
        scene_placeholders = self._collect_scene_placeholders()
        for node_name, node in scene_placeholders.items():
            plugin_identifier_knob = node.knob("plugin_identifier")
            if (
                plugin_identifier_knob is None
                or plugin_identifier_knob.getValue() != self.identifier
            ):
                continue

            placeholder_data = self._parse_placeholder_node_data(node)

            output.append(
                CreatePlaceholderItem(node_name, placeholder_data, self)
            )

        return output

    def populate_placeholder(self, placeholder):
        self.populate_create_placeholder(placeholder)

    def repopulate_placeholder(self, placeholder):
        self.populate_create_placeholder(placeholder)

    def get_placeholder_options(self, options=None):
        return self.get_create_plugin_options(options)

    def post_placeholder_process(self, placeholder, failed):
        """Cleanup placeholder after load of its corresponding representations.

        Args:
            placeholder (PlaceholderItem): Item which was just used to load
                representation.
            failed (bool): Loading of representation failed.
        """
        # deselect all selected nodes
        placeholder_node = nuke.toNode(placeholder.scene_identifier)

        # getting the latest nodes added
        nodes_init = placeholder.data["nodes_init"]
        nodes_created = list(set(nuke.allNodes()) - set(nodes_init))
        self.log.debug("Created nodes: {}".format(nodes_created))
        if not nodes_created:
            return

        placeholder.data["delete"] = True

        nodes_created = self._move_to_placeholder_group(
            placeholder, nodes_created
        )
        placeholder.data["last_created"] = nodes_created
        refresh_nodes(nodes_created)

        # positioning of the created nodes
        min_x, min_y, _, _ = get_extreme_positions(nodes_created)
        for node in nodes_created:
            xpos = (node.xpos() - min_x) + placeholder_node.xpos()
            ypos = (node.ypos() - min_y) + placeholder_node.ypos()
            node.setXYpos(xpos, ypos)
        refresh_nodes(nodes_created)

        # fix the problem of z_order for backdrops
        self._fix_z_order(placeholder)

        if placeholder.data.get("keep_placeholder"):
            self._imprint_siblings(placeholder)

        if placeholder.data["nb_children"] == 0:
            # save initial nodes positions and dimensions, update them
            # and set inputs and outputs of created nodes

            if placeholder.data.get("keep_placeholder"):
                self._imprint_inits()
                self._update_nodes(placeholder, nuke.allNodes(), nodes_created)

            self._set_created_connections(placeholder)

        elif placeholder.data["siblings"]:
            # create copies of placeholder siblings for the new created nodes,
            # set their inputs and outputs and update all nodes positions and
            # dimensions and siblings names

            siblings = get_nodes_by_names(placeholder.data["siblings"])
            refresh_nodes(siblings)
            copies = self._create_sib_copies(placeholder)
            new_nodes = list(copies.values())  # copies nodes
            self._update_nodes(new_nodes, nodes_created)
            placeholder_node.removeKnob(placeholder_node.knob("siblings"))
            new_nodes_name = get_names_from_nodes(new_nodes)
            imprint(placeholder_node, {"siblings": new_nodes_name})
            self._set_copies_connections(placeholder, copies)

            self._update_nodes(
                nuke.allNodes(),
                new_nodes + nodes_created,
                20
            )

            new_siblings = get_names_from_nodes(new_nodes)
            placeholder.data["siblings"] = new_siblings

        else:
            # if the placeholder doesn't have siblings, the created
            # nodes will be placed in a free space

            xpointer, ypointer = find_free_space_to_paste_nodes(
                nodes_created, direction="bottom", offset=200
            )
            node = nuke.createNode("NoOp")
            reset_selection()
            nuke.delete(node)
            for node in nodes_created:
                xpos = (node.xpos() - min_x) + xpointer
                ypos = (node.ypos() - min_y) + ypointer
                node.setXYpos(xpos, ypos)

        placeholder.data["nb_children"] += 1
        reset_selection()

        # go back to root group
        nuke.root().begin()

    def _move_to_placeholder_group(self, placeholder, nodes_created):
        """
        opening the placeholder's group and copying created nodes in it.

        Returns :
            nodes_created (list): the new list of pasted nodes
        """
        groups_name = placeholder.data["group_name"]
        reset_selection()
        select_nodes(nodes_created)
        if groups_name:
            with node_tempfile() as filepath:
                nuke.nodeCopy(filepath)
                for node in nuke.selectedNodes():
                    nuke.delete(node)
                group = nuke.toNode(groups_name)
                group.begin()
                nuke.nodePaste(filepath)
                nodes_created = nuke.selectedNodes()
        return nodes_created

    def _fix_z_order(self, placeholder):
        """Fix the problem of z_order when a backdrop is create."""

        nodes_created = placeholder.data["last_created"]
        created_backdrops = []
        bd_orders = set()
        for node in nodes_created:
            if isinstance(node, nuke.BackdropNode):
                created_backdrops.append(node)
                bd_orders.add(node.knob("z_order").getValue())

        if not bd_orders:
            return

        sib_orders = set()
        for node_name in placeholder.data["siblings"]:
            node = nuke.toNode(node_name)
            if isinstance(node, nuke.BackdropNode):
                sib_orders.add(node.knob("z_order").getValue())

        if not sib_orders:
            return

        min_order = min(bd_orders)
        max_order = max(sib_orders)
        for backdrop_node in created_backdrops:
            z_order = backdrop_node.knob("z_order").getValue()
            backdrop_node.knob("z_order").setValue(
                z_order + max_order - min_order + 1)

    def _imprint_siblings(self, placeholder):
        """
        - add siblings names to placeholder attributes (nodes created with it)
        - add Id to the attributes of all the other nodes
        """

        created_nodes = placeholder.data["last_created"]
        created_nodes_set = set(created_nodes)

        for node in created_nodes:
            node_knobs = node.knobs()

            if (
                "is_placeholder" not in node_knobs
                or (
                    "is_placeholder" in node_knobs
                    and node.knob("is_placeholder").value()
                )
            ):
                siblings = list(created_nodes_set - {node})
                siblings_name = get_names_from_nodes(siblings)
                siblings = {"siblings": siblings_name}
                imprint(node, siblings)

    def _imprint_inits(self):
        """Add initial positions and dimensions to the attributes"""

        for node in nuke.allNodes():
            refresh_node(node)
            imprint(node, {"x_init": node.xpos(), "y_init": node.ypos()})
            node.knob("x_init").setVisible(False)
            node.knob("y_init").setVisible(False)
            width = node.screenWidth()
            height = node.screenHeight()
            if "bdwidth" in node.knobs():
                imprint(node, {"w_init": width, "h_init": height})
                node.knob("w_init").setVisible(False)
                node.knob("h_init").setVisible(False)
            refresh_node(node)

    def _update_nodes(
        self, placeholder, nodes, considered_nodes, offset_y=None
    ):
        """Adjust backdrop nodes dimensions and positions.

        Considering some nodes sizes.

        Args:
            nodes (list): list of nodes to update
            considered_nodes (list): list of nodes to consider while updating
                positions and dimensions
            offset (int): distance between copies
        """

        placeholder_node = nuke.toNode(placeholder.scene_identifier)

        min_x, min_y, max_x, max_y = get_extreme_positions(considered_nodes)

        diff_x = diff_y = 0
        contained_nodes = []  # for backdrops

        if offset_y is None:
            width_ph = placeholder_node.screenWidth()
            height_ph = placeholder_node.screenHeight()
            diff_y = max_y - min_y - height_ph
            diff_x = max_x - min_x - width_ph
            contained_nodes = [placeholder_node]
            min_x = placeholder_node.xpos()
            min_y = placeholder_node.ypos()
        else:
            siblings = get_nodes_by_names(placeholder.data["siblings"])
            minX, _, maxX, _ = get_extreme_positions(siblings)
            diff_y = max_y - min_y + 20
            diff_x = abs(max_x - min_x - maxX + minX)
            contained_nodes = considered_nodes

        if diff_y <= 0 and diff_x <= 0:
            return

        for node in nodes:
            refresh_node(node)

            if (
                node == placeholder_node
                or node in considered_nodes
            ):
                continue

            if (
                not isinstance(node, nuke.BackdropNode)
                or (
                    isinstance(node, nuke.BackdropNode)
                    and not set(contained_nodes) <= set(node.getNodes())
                )
            ):
                if offset_y is None and node.xpos() >= min_x:
                    node.setXpos(node.xpos() + diff_x)

                if node.ypos() >= min_y:
                    node.setYpos(node.ypos() + diff_y)

            else:
                width = node.screenWidth()
                height = node.screenHeight()
                node.knob("bdwidth").setValue(width + diff_x)
                node.knob("bdheight").setValue(height + diff_y)

            refresh_node(node)

    def _set_created_connections(self, placeholder):
        """
        set inputs and outputs of created nodes"""

        placeholder_node = nuke.toNode(placeholder.scene_identifier)
        input_node, output_node = get_group_io_nodes(
            placeholder.data["last_created"]
        )
        for node in placeholder_node.dependent():
            for idx in range(node.inputs()):
                if node.input(idx) == placeholder_node and output_node:
                    node.setInput(idx, output_node)

        for node in placeholder_node.dependencies():
            for idx in range(placeholder_node.inputs()):
                if placeholder_node.input(idx) == node and input_node:
                    input_node.setInput(0, node)

    def _create_sib_copies(self, placeholder):
        """ creating copies of the palce_holder siblings (the ones who were
        created with it) for the new nodes added

        Returns :
            copies (dict) : with copied nodes names and their copies
        """

        copies = {}
        siblings = get_nodes_by_names(placeholder.data["siblings"])
        for node in siblings:
            new_node = duplicate_node(node)

            x_init = int(new_node.knob("x_init").getValue())
            y_init = int(new_node.knob("y_init").getValue())
            new_node.setXYpos(x_init, y_init)
            if isinstance(new_node, nuke.BackdropNode):
                w_init = new_node.knob("w_init").getValue()
                h_init = new_node.knob("h_init").getValue()
                new_node.knob("bdwidth").setValue(w_init)
                new_node.knob("bdheight").setValue(h_init)
                refresh_node(node)

            if "repre_id" in node.knobs().keys():
                node.removeKnob(node.knob("repre_id"))
            copies[node.name()] = new_node
        return copies

    def _set_copies_connections(self, placeholder, copies):
        """Set inputs and outputs of the copies.

        Args:
            copies (dict): Copied nodes by their names.
        """

        last_input, last_output = get_group_io_nodes(
            placeholder.data["last_created"]
        )
        siblings = get_nodes_by_names(placeholder.data["siblings"])
        siblings_input, siblings_output = get_group_io_nodes(siblings)
        copy_input = copies[siblings_input.name()]
        copy_output = copies[siblings_output.name()]

        for node_init in siblings:
            if node_init == siblings_output:
                continue

            node_copy = copies[node_init.name()]
            for node in node_init.dependent():
                for idx in range(node.inputs()):
                    if node.input(idx) != node_init:
                        continue

                    if node in siblings:
                        copies[node.name()].setInput(idx, node_copy)
                    else:
                        last_input.setInput(0, node_copy)

            for node in node_init.dependencies():
                for idx in range(node_init.inputs()):
                    if node_init.input(idx) != node:
                        continue

                    if node_init == siblings_input:
                        copy_input.setInput(idx, node)
                    elif node in siblings:
                        node_copy.setInput(idx, copies[node.name()])
                    else:
                        node_copy.setInput(idx, last_output)

        siblings_input.setInput(0, copy_output)
