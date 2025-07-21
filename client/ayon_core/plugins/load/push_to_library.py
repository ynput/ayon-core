import os

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import get_ayon_launcher_args, run_detached_process
from ayon_core.pipeline import load
from ayon_core.pipeline.load import LoadError


class PushToLibraryProject(load.ProductLoaderPlugin):
    """Export selected versions to folder structure from Template"""

    is_multiple_contexts_compatible = True

    representations = {"*"}
    product_types = {"*"}

    label = "Push to Library project"
    order = 35
    icon = "send"
    color = "#d8d8d8"

    def load(self, contexts, name=None, namespace=None, options=None):
        filtered_contexts = [
            context
            for context in contexts
            if context.get("project") and context.get("version")
        ]
        if not filtered_contexts:
            raise LoadError("Nothing to push for your selection")

        if len(filtered_contexts) > 1:
            raise LoadError("Please select only one item")

        context = tuple(filtered_contexts)[0]

        push_tool_script_path = os.path.join(
            AYON_CORE_ROOT,
            "tools",
            "push_to_project",
            "main.py"
        )

        project_name = context["project"]["name"]
        version_id = context["version"]["id"]

        args = get_ayon_launcher_args(
            "run",
            push_tool_script_path,
            "--project", project_name,
            "--version", version_id
        )
        run_detached_process(args)
