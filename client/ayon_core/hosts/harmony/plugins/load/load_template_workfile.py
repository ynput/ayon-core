import tempfile
import zipfile
import os
import shutil

from ayon_core.pipeline import (
    load,
    get_representation_path,
)
import ayon_core.hosts.harmony.api as harmony


class ImportTemplateLoader(load.LoaderPlugin):
    """Import templates."""

    product_types = {"harmony.template", "workfile"}
    representations = {"*"}
    label = "Import Template"

    def load(self, context, name=None, namespace=None, data=None):
        # Import template.
        temp_dir = tempfile.mkdtemp()
        zip_file = get_representation_path(context["representation"])
        template_path = os.path.join(temp_dir, "temp.tpl")
        with zipfile.ZipFile(zip_file, "r") as zip_ref:
            zip_ref.extractall(template_path)

        sig = harmony.signature("paste")
        func = """function %s(args)
        {
            var template_path = args[0];
            var drag_object = copyPaste.pasteTemplateIntoGroup(
                template_path, "Top", 1
            );
        }
        %s
        """ % (sig, sig)

        harmony.send({"function": func, "args": [template_path]})

        shutil.rmtree(temp_dir)

        product_name = context["product"]["name"]

        return harmony.containerise(
            product_name,
            namespace,
            product_name,
            context,
            self.__class__.__name__
        )

    def update(self, container, context):
        pass

    def remove(self, container):
        pass


class ImportWorkfileLoader(ImportTemplateLoader):
    """Import workfiles."""

    product_types = {"workfile"}
    representations = {"zip"}
    label = "Import Workfile"
