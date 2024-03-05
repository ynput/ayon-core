"""Pre-launch to force zbrush startup script."""
import os
from ayon_core.hosts.zbrush import ZBRUSH_HOST_DIR
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
        python_exe = os.environ["AYON_EXECUTABLE"]
        ayon_script = ("""
// Set a variable to " so we can quote the command line arguments for ShellExecute
[VarSet, q, [StrFromAsc, 34]]
[VarSet, addon, "addon"]
[VarSet, zbrush, "zbrush"]
[VarSet, zscript, "run-with-zscript"]
[VarSet, arg, "--launcher"]
[IPalette, "AYON", 1]

[ISubPalette, "AYON:Tools", 2]

// Load
[IButton, "AYON:Tools:Load...", "Open AYON Loader",
	[VarSet, loader, "loader_tool"]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{launch}", #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #addon, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zbrush, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zscript, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #arg, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #loader, #q]]
	[ShellExecute, cmd], 0, 120
]

// Publish
[IButton, "AYON:Tools:Publish...", "Open AYON Publisher",
	[VarSet, publisher, "publish_tool"]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{launch}", #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #addon, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zbrush, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zscript, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #arg, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #publisher, #q]]
	[ShellExecute, cmd], 0, 120
]

// Manage
[IButton, "AYON:Tools:Manage...", "Open AYON Scene Inventory UI",
	[VarSet, scene_inventory, "scene_inventory_tool"]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{launch}", #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #addon, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zbrush, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zscript, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #arg, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #scene_inventory, #q]]
	[ShellExecute, cmd], 0, 120
]

[ISubPalette, "AYON:Project", 2]
// Workfile
[IButton, "AYON:Project:Work Files...", "Open AYON Work Files UI",
	[VarSet, workfiles, "workfiles_tool"]
	[VarSet, cmd, [StrMerge, start, " ",#q, #q, "  ",#q, "{launch}", #q]]
	[VarSet, cmd, [StrMerge, cmd, " ", #addon, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zbrush, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #zscript, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #arg, #q]]
	[VarSet, cmd, [StrMerge, cmd, #q,  " ", #workfiles, #q]]
	[ShellExecute, cmd], 0, 120
]""").format(launch=python_exe)
        return ayon_script
