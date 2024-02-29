"""Pre-launch to force zbrush startup script."""
import os
import subprocess
from ayon_core.hosts.zbrush import ZBRUSH_HOST_DIR
from ayon_core.lib import get_ayon_launcher_args
from ayon_core.lib.applications import PreLaunchHook, LaunchTypes



class CreateZMenuScript(PreLaunchHook):
    """Create AYON Menu Zscript to Zbrush.

    Note that this works in combination whit Zbrush startup script
    to successfully install zscripts.menu

    Hook `GlobalHostDataHook` must be executed before this hook.
    """
    app_groups = {"zbrush"}
    order = 12
    launch_types = {LaunchTypes.local}

    def execute(self):
        zscript_path = os.path.join(ZBRUSH_HOST_DIR, "api", "zscripts")
        os.makedirs(zscript_path, exist_ok=True)
        zscript_txt = os.path.join(zscript_path, "ayon_zbrush_menu.txt")
        with open(zscript_txt, "w") as zscript:
            zscript.write(self.ayon_menu())
            zscript.close()

    def ayon_menu(self):
        os.environ["AYON_ZBRUSH_CMD"] = subprocess.list2cmdline(
            get_ayon_launcher_args())
        zclient_path = os.path.join(ZBRUSH_HOST_DIR, "api", "widgets.py")
        zclient_path = zclient_path.replace("\\", "/")
        python_exe = os.environ["AYON_ZBRUSH_CMD"]
        ayon_script = ("""
[ISubPalette,"Zplugin:AYON"]
[IButton,"Zplugin:AYON:Load","Loader",
	[VarSet,sc, "{client_script}"]
	[VarSet, loader, "loader_tool"]
    [VarSet, q, [StrFromAsc, 34]]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{py}",#q, " ",#q, sc, #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #loader, #q]]
	[ShellExecute, cmd], 0, 120
]//end button
[IButton,"Zplugin:AYON:Publish","Publish Tab for Publisher",
	[VarSet, sc, "{client_script}"]
	[VarSet, publisher, "publish_tool"]
    [VarSet, q, [StrFromAsc, 34]]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{py}",#q, " ",#q, sc, #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #publisher, #q]]
	[ShellExecute, cmd], 0, 120
]//end button
[IButton,"Zplugin:AYON:Manage","Scene Inventory Manager",
	[VarSet, sc, "{client_script}"]
	[VarSet, sceneinventory, "scene_inventory_tool"]
    [VarSet, q, [StrFromAsc, 34]]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{py}",#q, " ",#q, sc, #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #sceneinventory, #q]]
	[ShellExecute, cmd], 0, 120
]//end button
[IButton,"Zplugin:AYON:Workfile","Workfile",
	[VarSet,sc, "{client_script}"]
	[VarSet, workfiles, "workfiles_tool"]
	[VarSet, q, [StrFromAsc, 34]]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{py}",#q, " ",#q, sc, #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #workfiles, #q]]
	[ShellExecute, cmd], 0, 120
]//end button""").format(client_script=zclient_path, py=python_exe)
        return ayon_script
