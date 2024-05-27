from nukescripts import autoBackdrop

from ayon_nuke.api import (
    NukeCreator,
    maintained_selection,
    select_nodes
)


class CreateBackdrop(NukeCreator):
    """Add Publishable Backdrop"""

    settings_category = "nuke"

    identifier = "create_backdrop"
    label = "Nukenodes (backdrop)"
    product_type = "nukenodes"
    icon = "file-archive-o"
    maintain_selection = True

    # plugin attributes
    node_color = "0xdfea5dff"

    def create_instance_node(
        self,
        node_name,
        knobs=None,
        parent=None,
        node_type=None
    ):
        with maintained_selection():
            if len(self.selected_nodes) >= 1:
                select_nodes(self.selected_nodes)

            created_node = autoBackdrop()
            created_node["name"].setValue(node_name)
            created_node["tile_color"].setValue(int(self.node_color, 16))
            created_node["note_font_size"].setValue(24)
            created_node["label"].setValue("[{}]".format(node_name))

            return created_node

    def create(self, product_name, instance_data, pre_create_data):
        # make sure product name is unique
        self.check_existing_product(product_name)

        instance = super(CreateBackdrop, self).create(
            product_name,
            instance_data,
            pre_create_data
        )

        return instance
