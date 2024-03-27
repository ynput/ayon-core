import os
import re

import click
import speedcopy
import ayon_api

from ayon_core.lib import Terminal
from ayon_core.pipeline import Anatomy
from ayon_core.pipeline.template_data import get_template_data


t = Terminal()

texture_extensions = ['.tif', '.tiff', '.jpg', '.jpeg', '.tx', '.png', '.tga',
                      '.psd', '.dpx', '.hdr', '.hdri', '.exr', '.sxr', '.psb']


class TextureCopy:
    def _get_textures(self, path):
        textures = []
        for dir, subdir, files in os.walk(path):
            textures.extend(
                os.path.join(dir, x) for x in files
                if os.path.splitext(x)[1].lower() in texture_extensions)
        return textures

    def _get_destination_path(self, folder_entity, project_entity):
        project_name = project_entity["name"]

        product_name = "Main"
        product_type = "texture"
        template_data = get_template_data(project_entity, folder_entity)
        template_data.update({
            "family": product_type,
            "subset": product_name,
            "product": {
                "name": product_name,
                "type": product_type,
            },
        })
        anatomy = Anatomy(project_name, project_entity=project_entity)
        template_obj = anatomy.get_template_item(
            "publish", "texture", "path"
        )
        return template_obj.format_strict(template_data)

    def _get_version(self, path):
        versions = [0]
        dirs = [f.path for f in os.scandir(path) if f.is_dir()]
        for d in dirs:
            ver = re.search(r'^v(\d+)$',
                            os.path.basename(d),
                            flags=re.IGNORECASE)
            if ver is not None:
                versions.append(int(ver.group(1)))

        return max(versions) + 1

    def _copy_textures(self, textures, destination):
        for tex in textures:
            dst = os.path.join(destination,
                               os.path.basename(tex))
            t.echo("  - Copy {} -> {}".format(tex, dst))
            try:
                speedcopy.copyfile(tex, dst)
            except Exception as e:
                t.echo("!!! Copying failed")
                t.echo("!!! {}".format(e))
                exit(1)

    def process(self, project_name, folder_path, path):
        """
        Process all textures found in path and copy them to folder under
        project.
        """

        t.echo(">>> Looking for textures ...")
        textures = self._get_textures(path)
        if len(textures) < 1:
            t.echo("!!! no textures found.")
            exit(1)
        else:
            t.echo(">>> Found {} textures ...".format(len(textures)))

        project_entity = ayon_api.get_project(project_name)
        if not project_entity:
            t.echo("!!! Project name [ {} ] not found.".format(project_name))
            exit(1)

        folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
        if not folder_entity:
            t.echo(
                "!!! Folder [ {} ] not found in project".format(folder_path)
            )
            exit(1)
        t.echo(
            (
                ">>> Project [ {} ] and folder [ {} ] seems to be OK ..."
            ).format(project_entity['name'], folder_entity['path'])
        )

        dst_path = self._get_destination_path(folder_entity, project_entity)
        t.echo("--- Using [ {} ] as destination path".format(dst_path))
        if not os.path.exists(dst_path):
            try:
                os.makedirs(dst_path)
            except IOError as e:
                t.echo("!!! Unable to create destination directory")
                t.echo("!!! {}".format(e))
                exit(1)
        version = '%02d' % self._get_version(dst_path)
        t.echo("--- Using version [ {} ]".format(version))
        dst_path = os.path.join(dst_path, "v{}".format(version))
        t.echo("--- Final destination path [ {} ]".format(dst_path))
        try:
            os.makedirs(dst_path)
        except FileExistsError:
            t.echo("!!! Somethings wrong, version directory already exists")
            exit(1)
        except IOError as e:
            t.echo("!!! Cannot create version directory")
            t.echo("!!! {}".format(e))
            exit(1)

        t.echo(">>> copying textures  ...")
        self._copy_textures(textures, dst_path)
        t.echo(">>> done.")
        t.echo("<<< terminating ...")


@click.command()
@click.option('--project', required=True)
@click.option('--folder', required=True)
@click.option('--path', required=True)
def texture_copy(project, folder, path):
    t.echo("*** Running Texture tool ***")
    t.echo(">>> Initializing avalon session ...")
    os.environ["AYON_PROJECT_NAME"] = project
    os.environ["AYON_FOLDER_PATH"] = folder
    TextureCopy().process(project, folder, path)


if __name__ == '__main__':
    texture_copy()
