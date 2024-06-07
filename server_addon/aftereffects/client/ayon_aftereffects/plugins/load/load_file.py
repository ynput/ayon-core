import re
import os
from ayon_core.pipeline import get_representation_path
from ayon_aftereffects import api
from ayon_aftereffects.api.lib import get_unique_layer_name


class FileLoader(api.AfterEffectsLoader):
    """Load images

    Stores the imported asset in a container named after the asset.
    """
    label = "Load file"

    product_types = {
        "image",
        "plate",
        "render",
        "prerender",
        "review",
        "audio",
    }
    representations = {"*"}

    def load(self, context, name=None, namespace=None, data=None):
        stub = self.get_stub()
        selected_folders = stub.get_selected_items(
            comps=False, folders=True, footages=False)
        if selected_folders:
            stub.select_items([folder.id for folder in selected_folders])
        layers = stub.get_items(comps=True, folders=True, footages=True)
        existing_layers = [layer.name for layer in layers]
        comp_name = get_unique_layer_name(
            existing_layers, "{}_{}".format(
                context["folder"]["name"], name
            )
        )

        import_options = {}

        path = self.filepath_from_context(context)

        if len(context["representation"]["files"]) > 1:
            import_options['sequence'] = True

        if not path:
            repr_id = context["representation"]["id"]
            self.log.warning(
                "Representation id `{}` is failing to load".format(repr_id))
            return

        path = path.replace("\\", "/")
        if '.psd' in path:
            import_options['ImportAsType'] = 'ImportAsType.COMP'

        comp = stub.import_file(path, stub.LOADED_ICON + comp_name,
                                import_options)
        if not comp:
            self.log.warning(
                "Representation `{}` is failing to load".format(path))
            self.log.warning("Check host app for alert error.")
            return

        self[:] = [comp]
        namespace = namespace or comp_name
        return api.containerise(
            name,
            namespace,
            comp,
            context,
            self.__class__.__name__
        )

    def update(self, container, context):
        """ Switch asset or change version """
        stub = self.get_stub()
        layer = container.pop("layer")

        folder_name = context["folder"]["name"]
        product_name = context["product"]["name"]
        repre_entity = context["representation"]

        namespace_from_container = re.sub(r'_\d{3}$', '',
                                          container["namespace"])
        layer_name = "{}_{}".format(folder_name, product_name)
        # switching assets
        if namespace_from_container != layer_name:
            layers = stub.get_items(comps=True)
            existing_layers = [layer.name for layer in layers]
            layer_name = get_unique_layer_name(
                existing_layers,
                "{}_{}".format(folder_name, product_name))
        else:  # switching version - keep same name
            layer_name = container["namespace"]
        path = get_representation_path(repre_entity)

        if len(repre_entity["files"]) > 1:
           path = os.path.dirname(path)
        # with aftereffects.maintained_selection():  # TODO
        stub.replace_item(layer.id, path, stub.LOADED_ICON + layer_name)
        stub.imprint(
            layer.id, {"representation": repre_entity["id"],
                       "name": product_name,
                       "namespace": layer_name}
        )

    def remove(self, container):
        """
            Removes element from scene: deletes layer + removes from Headline
        Args:
            container (dict): container to be removed - used to get layer_id
        """
        stub = self.get_stub()
        layer = container.pop("layer")
        stub.imprint(layer.id, {})
        stub.delete_item(layer.id)

    def switch(self, container, context):
        self.update(container, context)
