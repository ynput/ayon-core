name = "core"
title = "Core"
version = "1.3.2+dev"

client_dir = "ayon_core"

plugin_for = ["ayon_server"]

project_can_override_addon_version = True

ayon_server_version = ">=1.8.4,<2.0.0"
ayon_launcher_version = ">=1.0.2"
ayon_required_addons = {}
ayon_compatible_addons = {
    "ayon_ocio": ">=1.2.1",
    "applications": ">=1.1.2",
    "harmony": ">0.4.0",
    "fusion": ">=0.3.3",
    "openrv": ">=1.0.2",
}
