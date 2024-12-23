import os
from ayon_core.lib import is_staging_enabled

RESOURCES_DIR = os.path.dirname(os.path.abspath(__file__))


def get_resource(*args):
    """ Serves to simple resources access

    :param *args: should contain *subfolder* names and *filename* of
                  resource from resources folder
    :type *args: list
    """
    return os.path.normpath(os.path.join(RESOURCES_DIR, *args))


def get_image_path(*args):
    """Helper function to get images.

    Args:
        *<str>: Filepath part items.
    """
    return get_resource("images", *args)


def get_liberation_font_path(bold=False, italic=False):
    font_name = "LiberationSans"
    suffix = ""
    if bold:
        suffix += "Bold"
    if italic:
        suffix += "Italic"

    if not suffix:
        suffix = "Regular"

    filename = "{}-{}.ttf".format(font_name, suffix)
    font_path = get_resource("fonts", font_name, filename)
    return font_path


def get_ayon_production_icon_filepath():
    return get_resource("icons", "AYON_icon.png")


def get_ayon_staging_icon_filepath():
    return get_resource("icons", "AYON_icon_staging.png")


def get_ayon_icon_filepath(staging=None):
    if os.getenv("AYON_USE_DEV") == "1":
        return get_resource("icons", "AYON_icon_dev.png")

    if staging is None:
        staging = is_staging_enabled()

    if staging:
        return get_ayon_staging_icon_filepath()
    return get_ayon_production_icon_filepath()


def get_ayon_splash_filepath(staging=None):
    if staging is None:
        staging = is_staging_enabled()

    if os.getenv("AYON_USE_DEV") == "1":
        splash_file_name = "AYON_splash_dev.png"
    elif staging:
        splash_file_name = "AYON_splash_staging.png"
    else:
        splash_file_name = "AYON_splash.png"
    return get_resource("icons", splash_file_name)
