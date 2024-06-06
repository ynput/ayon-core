# -*- coding: utf-8 -*-
from ayon_unreal.api.plugin import (
    UnrealActorCreator,
)


class CreateLayout(UnrealActorCreator):
    """Layout output for character rigs."""

    identifier = "io.ayon.creators.unreal.layout"
    label = "Layout"
    product_type = "layout"
    icon = "cubes"
