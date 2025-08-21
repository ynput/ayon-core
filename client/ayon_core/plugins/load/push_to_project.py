import os

from ayon_core import AYON_CORE_ROOT
from ayon_core.lib import get_ayon_launcher_args, run_detached_process
from ayon_core.pipeline import load
from ayon_core.pipeline.load import LoadError


class PushToProject(load.ProductLoaderPlugin):
    """Export selected versions to different project"""

    is_multiple_contexts_compatible = True

    representations = {"*"}
    product_types = {"*"}

    label = "Push to project"
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

        push_tool_script_path = os.path.join(
            AYON_CORE_ROOT,
            "tools",
            "push_to_project",
            "main.py"
        )
        project_name = filtered_contexts[0]["project"]["name"]

        version_ids = {
            context["version"]["id"]
            for context in filtered_contexts
        }

        args = get_ayon_launcher_args(
            push_tool_script_path,
            "--project", project_name,
            "--versions", ",".join(version_ids)
        )
        run_detached_process(args)
