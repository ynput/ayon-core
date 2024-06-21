from ayon_houdini.api import plugin
from ayon_houdini.api.lib import (
    lsattr, read
)
from ayon_core.pipeline.create import (
    CreatedInstance,
    get_product_name
)
from ayon_api import get_folder_by_path, get_task_by_name
from ayon_core.lib import (
    AbstractAttrDef,
    BoolDef,
    NumberDef,
    EnumDef,
    TextDef,
    UISeparatorDef,
    UILabelDef,
    FileDef
)

import hou
import json


def attribute_def_to_parm_template(attribute_def, key=None):
    """AYON Attribute Definition to Houdini Parm Template.

    Arguments:
        attribute_def (AbstractAttrDef): Attribute Definition.

    Returns:
        hou.ParmTemplate: Parm Template matching the Attribute Definition.
    """

    if key is None:
        key = attribute_def.key

    if isinstance(attribute_def, BoolDef):
        return hou.ToggleParmTemplate(name=key,
                                      label=attribute_def.label,
                                      default_value=attribute_def.default,
                                      help=attribute_def.tooltip)
    elif isinstance(attribute_def, NumberDef):
        if attribute_def.decimals == 0:
            return hou.IntParmTemplate(
                name=key,
                label=attribute_def.label,
                default_value=(attribute_def.default,),
                help=attribute_def.tooltip,
                min=attribute_def.minimum,
                max=attribute_def.maximum,
                num_components=1
            )
        else:
            return hou.FloatParmTemplate(
                name=key,
                label=attribute_def.label,
                default_value=(attribute_def.default,),
                help=attribute_def.tooltip,
                min=attribute_def.minimum,
                max=attribute_def.maximum,
                num_components=1
            )
    elif isinstance(attribute_def, EnumDef):
        # TODO: Support multiselection EnumDef
        # We only support enums that do not allow multiselection
        # as a dedicated houdini parm.
        if not attribute_def.multiselection:
            labels = [item["label"] for item in attribute_def.items]
            values = [item["value"] for item in attribute_def.items]

            print(attribute_def.default)

            return hou.StringParmTemplate(
                name=key,
                label=attribute_def.label,
                default_value=(attribute_def.default,),
                help=attribute_def.tooltip,
                num_components=1,
                menu_labels=labels,
                menu_items=values,
                menu_type=hou.menuType.Normal
            )
    elif isinstance(attribute_def, TextDef):
        return hou.StringParmTemplate(
            name=key,
            label=attribute_def.label,
            default_value=(attribute_def.default,),
            help=attribute_def.tooltip,
            num_components=1
        )
    elif isinstance(attribute_def, UISeparatorDef):
        return hou.SeparatorParmTemplate(
            name=key,
            label=attribute_def.label,
        )
    elif isinstance(attribute_def, UILabelDef):
        return hou.LabelParmTemplate(
            name=key,
            label=attribute_def.label,
        )
    elif isinstance(attribute_def, FileDef):
        # TODO: Support FileDef
        pass

    # Unsupported attribute definition. We'll store value as JSON so just
    # turn it into a string `JSON::` value
    json_value = json.dumps(getattr(attribute_def, "default", None),
                            default=str)
    return hou.StringParmTemplate(
        name=key,
        label=attribute_def.label,
        default_value=f"JSON::{json_value}",
        help=getattr(attribute_def, "tooltip", None),
        num_components=1
    )


def set_values(node: "hou.OpNode", values: dict):
    """Set parm values only if both the raw value (e.g. expression) or the
    evaluated value differ. This way we preserve expressions if they happen
    to evaluate to a matching value.

    Parms must exist on the node already.

    """
    for key, value in values.items():

        parm = node.parm(key)

        try:
            unexpanded_value = parm.unexpandedString()
            if unexpanded_value == value:
                # Allow matching expressions
                continue
        except hou.OperationFailed:
            pass

        if parm.rawValue() == value:
            continue

        if parm.eval() == value:
            # Needs no change
            continue

        # TODO: Set complex data types as `JSON:`
        parm.set(value)


class CreateHoudiniGeneric(plugin.HoudiniCreator):
    """Generic creator to ingest arbitrary products"""

    host_name = "houdini"

    identifier = "io.ayon.creators.houdini.publish"
    label = "Generic"
    product_type = "generic"
    icon = "male"
    description = "Make any ROP node publishable."

    # TODO: Override "create" to create the AYON publish attributes on the
    #  selected node so it becomes a publishable instance.
    render_target = "local_no_render"
    default_variant = "$OS"

    def get_detail_description(self):
        return "Publish any ROP node."

    def create(self, product_name, instance_data, pre_create_data):

        product_type = pre_create_data.get("productType", "pointcache")
        instance_data["productType"] = product_type

        # Unfortunately the Create Context will provide the product name
        # even before the `create` call without listening to pre create data
        # or the instance data - so instead we ignore the product name here
        # and redefine it ourselves based on the `variant` in instance data
        project_name = self.create_context.project_name
        folder_entity = get_folder_by_path(project_name,
                                           instance_data["folderPath"])
        task_entity = get_task_by_name(project_name,
                                       folder_id=folder_entity["id"],
                                       task_name=instance_data["task"])
        product_name = self._get_product_name_dynamic(
            self.create_context.project_name,
            folder_entity=folder_entity,
            task_entity=task_entity,
            variant=instance_data["variant"],
            product_type=product_type
        )

        for node in hou.selectedNodes():
            if node.parm("AYON_creator_identifier"):
                # Continue if already existing attributes
                continue

            # Enforce new style instance id otherwise first save may adjust
            # this to the `AVALON_INSTANCE_ID` instead
            instance_data["id"] = plugin.AYON_INSTANCE_ID

            instance_data["instance_node"] = node.path()
            instance_data["instance_id"] = node.path()
            created_instance = CreatedInstance(
                product_type, product_name, instance_data.copy(), self
            )

            # Add instance
            self._add_instance_to_context(created_instance)

            # Imprint on the selected node
            # NOTE: We imprint after `_add_instance_to_context` to ensure
            #  the imprinted data directly contains also the instance
            #  attributes for the product type. Otherwise, they will appear
            #  after first save.
            self.imprint(created_instance,
                         values=created_instance.data_to_store(),
                         update=False)

    def collect_instances(self):
        for node in lsattr("AYON_id", plugin.AYON_INSTANCE_ID):

            creator_identifier_parm = node.parm("AYON_creator_identifier")
            if not creator_identifier_parm:
                continue

            # creator instance
            creator_id = creator_identifier_parm.eval()
            if creator_id != self.identifier:
                continue

            # Read all attributes starting with `ayon_`
            node_data = {
                key.removeprefix("AYON_"): value
                for key, value in read(node).items()
                if key.startswith("AYON_")
            }

            # Node paths are always the full node path since that is unique
            # Because it's the node's path it's not written into attributes
            # but explicitly collected
            node_path = node.path()
            node_data["instance_id"] = node_path
            node_data["instance_node"] = node_path
            node_data["families"] = self.get_publish_families()

            # Read creator and publish attributes
            publish_attributes = {}
            creator_attributes = {}
            for key, value in dict(node_data).items():
                if key.startswith("publish_attributes_"):
                    if value == 0 or value == 1:
                        value = bool(value)
                    plugin_name, plugin_key = key[len("publish_attributes_"):].split("_", 1)
                    publish_attributes.setdefault(plugin_name, {})[plugin_key] = value
                    del node_data[key]  # remove from original
                elif key.startswith("creator_attributes_"):
                    creator_key = key[len("creator_attributes_"):]
                    creator_attributes[creator_key] = value
                    del node_data[key]  # remove from original

            node_data["creator_attributes"] = creator_attributes
            node_data["publish_attributes"] = publish_attributes

            created_instance = CreatedInstance.from_existing(
                node_data, self
            )
            self._add_instance_to_context(created_instance)

    def update_instances(self, update_list):
        # Overridden to pass `created_instance` to `self.imprint`
        for created_inst, changes in update_list:
            new_values = {
                key: changes[key].new_value
                for key in changes.changed_keys
            }
            # Update parm templates and values
            self.imprint(
                created_inst,
                new_values,
                update=True
            )

    def get_product_name(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        host_name=None,
        instance=None
    ):
        if instance is not None:
            self.product_type = instance.data["productType"]
            product_name = super(CreateHoudiniGeneric, self).get_product_name(
                project_name,
                folder_entity,
                task_entity,
                variant,
                host_name,
                instance)
            self.product_type = "generic"
            return product_name

        else:
            return "<-- defined on create -->"

    def create_attribute_def_parms(self,
                                   node: "hou.OpNode",
                                   created_instance: CreatedInstance):
        # We imprint all the attributes into an AYON tab on the node in which
        # we have a list folder called `attributes` in which we have
        # - Instance Attributes
        # - Creator Attributes
        # - Publish Attributes
        # With also a separate `advanced` section for specific attributes
        parm_group = node.parmTemplateGroup()

        # Create default folder parm structure
        ayon_folder = parm_group.findFolder("AYON")
        if not ayon_folder:
            ayon_folder = hou.FolderParmTemplate("folder", "AYON")
            parm_group.addParmTemplate(ayon_folder)

        attributes_folder = parm_group.find("AYON_attributes")
        if not attributes_folder:
            attributes_folder = hou.FolderParmTemplate(
                "AYON_attributes",
                "Attributes",
                folder_type=hou.folderType.Collapsible
            )
            ayon_folder.addParmTemplate(attributes_folder)

        # Create Instance, Creator and Publish attributes folders
        instance_attributes_folder = parm_group.find("AYON_instance_attributes")
        if not instance_attributes_folder:
            instance_attributes_folder = hou.FolderParmTemplate(
                "AYON_instance_attributes",
                "Instance Attributes",
                folder_type=hou.folderType.Simple
            )
            attributes_folder.addParmTemplate(instance_attributes_folder)

        creator_attributes_folder = parm_group.find("AYON_creator_attributes")
        if not creator_attributes_folder:
            creator_attributes_folder = hou.FolderParmTemplate(
                "AYON_creator_attributes",
                "Creator Attributes",
                folder_type=hou.folderType.Simple
            )
            attributes_folder.addParmTemplate(creator_attributes_folder)

        publish_attributes_folder = parm_group.find("AYON_publish_attributes")
        if not publish_attributes_folder:
            publish_attributes_folder = hou.FolderParmTemplate(
                "AYON_publish_attributes",
                "Publish Attributes",
                folder_type=hou.folderType.Simple
            )
            attributes_folder.addParmTemplate(publish_attributes_folder)

        # Create Advanced Folder
        advanced_folder = parm_group.find("AYON_advanced")
        if not advanced_folder:
            advanced_folder = hou.FolderParmTemplate(
                "AYON_advanced",
                "Advanced",
                folder_type=hou.folderType.Collapsible
            )
            ayon_folder.addParmTemplate(advanced_folder)

        # Get the creator and publish attribute definitions so that we can
        # generate matching Houdini parm types, including label, tooltips, etc.
        creator_attribute_defs = created_instance.creator_attributes.attr_defs
        for attr_def in creator_attribute_defs:
            parm_template = attribute_def_to_parm_template(
                attr_def,
                key=f"AYON_creator_attributes_{attr_def.key}")

            name = parm_template.name()
            existing = parm_group.find(name)
            if existing:
                # Remove from Parm Group - and also from the folder itself
                # because that reference is not live anymore to the parm
                # group itself so will still have the parm template
                parm_group.remove(name)
                creator_attributes_folder.setParmTemplates([
                    t for t in creator_attributes_folder.parmTemplates()
                    if t.name() != name
                ])
            creator_attributes_folder.addParmTemplate(parm_template)

        for plugin_name, plugin_attr_values in created_instance.publish_attributes.items():
            prefix = f"AYON_publish_attributes_{plugin_name}_"
            for attr_def in plugin_attr_values.attr_defs:
                parm_template = attribute_def_to_parm_template(
                    attr_def,
                    key=f"{prefix}{attr_def.key}"
                )

                name = parm_template.name()
                existing = parm_group.find(name)
                if existing:
                    # Remove from Parm Group - and also from the folder itself
                    # because that reference is not live anymore to the parm
                    # group itself so will still have the parm template
                    parm_group.remove(name)
                    publish_attributes_folder.setParmTemplates([
                        t for t in publish_attributes_folder.parmTemplates()
                        if t.name() != name
                    ])
                publish_attributes_folder.addParmTemplate(parm_template)

        # TODO
        # Add the Folder Path, Task Name, Product Type, Variant, Product Name
        # and Active state in Instance attributes
        for attribute in [
            hou.StringParmTemplate(
                "AYON_folderPath", "Folder Path",
                num_components=1,
                default_value=("$AYON_FOLDER_PATH",)
            ),
            hou.StringParmTemplate(
                "AYON_task", "Task Name",
                num_components=1,
                default_value=("$AYON_TASK_NAME",)
            ),
            hou.StringParmTemplate(
                "AYON_productType", "Product Type",
                num_components=1,
                default_value=("pointcache",)
            ),
            hou.StringParmTemplate(
                "AYON_variant", "Variant",
                num_components=1,
                default_value=(self.default_variant,)
            ),
            hou.StringParmTemplate(
                "AYON_productName", "Product Name",
                num_components=1,
                default_value=('`chs("AYON_productType")``chs("AYON_variant")`',)
            ),
            hou.ToggleParmTemplate(
                "AYON_active", "Active",
                default_value=True
            )
        ]:
            if not parm_group.find(attribute.name()):
                instance_attributes_folder.addParmTemplate(attribute)

        # Add the Creator Identifier and ID in advanced
        for attribute in [
            hou.StringParmTemplate(
                "AYON_id", "ID",
                num_components=1,
                default_value=(plugin.AYON_INSTANCE_ID,)
            ),
            hou.StringParmTemplate(
                "AYON_creator_identifier", "Creator Identifier",
                num_components=1,
                default_value=(self.identifier,)
            ),
        ]:
            if not parm_group.find(attribute.name()):
                advanced_folder.addParmTemplate(attribute)

        # Ensure all folders are up-to-date if they had previously existed
        # already
        for folder in [ayon_folder,
                       attributes_folder,
                       instance_attributes_folder,
                       publish_attributes_folder,
                       creator_attributes_folder,
                       advanced_folder]:
            if parm_group.find(folder.name()):
                parm_group.replace(folder.name(), folder)  # replace
        node.setParmTemplateGroup(parm_group)

    def imprint(self,
                created_instance: CreatedInstance,
                values: dict,
                update=False):

        # Do not ever write these into the node.
        values.pop("instance_node", None)
        values.pop("instance_id", None)
        values.pop("families", None)
        if not values:
            return

        instance_node = hou.node(created_instance.get("instance_node"))

        # Update attribute definition parms
        self.create_attribute_def_parms(instance_node, created_instance)

        # Creator attributes to parms
        creator_attributes = values.pop("creator_attributes", {})
        parm_values = {}
        for attr, value in creator_attributes.items():
            key = f"AYON_creator_attributes_{attr}"
            parm_values[key] = value

        # Publish attributes to parms
        publish_attributes = values.pop("publish_attributes", {})
        for plugin_name, plugin_attr_values in publish_attributes.items():
            for attr, value in plugin_attr_values.items():
                key = f"AYON_publish_attributes_{plugin_name}_{attr}"
                parm_values[key] = value

        # The remainder attributes are stored without any prefixes
        # Prefix all values with `AYON_`
        parm_values.update(
            {f"AYON_{key}": value for key, value in values.items()}
        )

        set_values(instance_node, parm_values)

        # TODO: Update defaults for Variant, Product Type, Product Name
        #   on the node so Houdini doesn't show them bold after save

    def get_publish_families(self):
        return [self.product_type]

    def get_instance_attr_defs(self):
        """get instance attribute definitions.

        Attributes defined in this method are exposed in
            publish tab in the publisher UI.
        """

        render_target_items = {
            "local": "Local machine rendering",
            "local_no_render": "Use existing frames (local)",
            "farm": "Farm Rendering",
        }

        return [
            # TODO: This review toggle may be odd - because a regular
            #  pointcache creator does not have the review toggle but with
            #  this it does. Is that confusing? Can we make it so that `review`
            #  only shows when relevant?
            BoolDef("review",
                    label="Review",
                    tooltip="Mark as reviewable",
                    default=True),
            EnumDef("render_target",
                    items=render_target_items,
                    label="Render target",
                    default=self.render_target)
        ]

    def get_pre_create_attr_defs(self):
        return [
            TextDef("productType",
                    label="Product Type",
                    tooltip="Publish product type",
                    default="pointcache")
        ]

    def _get_product_name_dynamic(
        self,
        project_name,
        folder_entity,
        task_entity,
        variant,
        product_type,
        host_name=None,
        instance=None
    ):
        if host_name is None:
            host_name = self.create_context.host_name

        task_name = task_type = None
        if task_entity:
            task_name = task_entity["name"]
            task_type = task_entity["taskType"]

        dynamic_data = self.get_dynamic_data(
            project_name,
            folder_entity,
            task_entity,
            variant,
            host_name,
            instance
        )

        return get_product_name(
            project_name,
            task_name,
            task_type,
            host_name,
            product_type,
            variant,
            dynamic_data=dynamic_data,
            project_settings=self.project_settings
        )

    def get_network_categories(self):
        # Do not show anywhere in TAB menus since it applies to existing nodes
        return []
