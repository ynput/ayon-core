import click

from ayon_core.tools.utils import get_ayon_qt_app
from ayon_core.tools.push_to_project.ui import PushToContextSelectWindow


def main_show(project_name, version_ids):
    app = get_ayon_qt_app()

    window = PushToContextSelectWindow()
    window.show()
    window.set_source(project_name, version_ids)

    app.exec_()


@click.command()
@click.option("--project", help="Source project name")
@click.option("--versions", help="Source version ids")
def main(project, versions):
    """Run PushToProject tool to integrate version in different project.

    Args:
        project (str): Source project name.
        versions (str): comma separated versions for same context
    """

    main_show(project, versions)


if __name__ == "__main__":
    main()
