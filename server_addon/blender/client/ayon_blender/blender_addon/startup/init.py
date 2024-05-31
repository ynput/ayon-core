from ayon_core.pipeline import install_host
from ayon_blender.api import BlenderHost


def register():
    install_host(BlenderHost())


def unregister():
    pass
