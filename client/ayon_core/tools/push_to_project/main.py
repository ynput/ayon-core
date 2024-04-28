import click

from ayon_core.tools.utils import get_ayon_qt_app
from ayon_core.tools.push_to_project.ui import PushToContextSelectWindow


def main_show(project_name, version_id, library_filter, context_only):
    window = PushToContextSelectWindow(
        library_filter=library_filter, context_only=context_only
    )
    window.show()
    window.set_source(project_name, version_id)

    if __name__ == "__main__":
        app = get_ayon_qt_app()
        app.exec_()
    else:
        window.exec_()

    return window.context


@click.command()
@click.option("--project", help="Source project name")
@click.option("--version", help="Source version id")
def main(project, version):
    """Run PushToProject tool to integrate version in different project.

    Args:
        project (str): Source project name.
        version (str): Version id.
    """

    main_show(project, version)


if __name__ == "__main__":
    main()
