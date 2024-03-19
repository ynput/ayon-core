# -*- coding: utf-8 -*-
"""Creator plugin for creating point cloud."""
from ayon_core.hosts.max.api import plugin


class CreatePointCloud(plugin.MaxCreator):
    """Creator plugin for Point Clouds."""
    identifier = "io.openpype.creators.max.pointcloud"
    label = "Point Cloud"
    product_type = "pointcloud"
    icon = "gear"
