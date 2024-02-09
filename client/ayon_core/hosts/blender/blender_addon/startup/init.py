from ayon_core.pipeline import install_host
from ayon_core.hosts.blender.api import BlenderHost


def register():
    install_host(BlenderHost())


def unregister():
    pass
