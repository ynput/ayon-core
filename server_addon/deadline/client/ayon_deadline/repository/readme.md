## OpenPype Deadline repository overlay

 This directory is an overlay for Deadline repository. 
 It means that you can copy the whole hierarchy to Deadline repository and it 
 should work.
 
 Logic:
 -----
 GlobalJobPreLoad
 ----- 
 
The `GlobalJobPreLoad` will retrieve the AYON executable path from the
`Ayon` Deadline Plug-in's settings. Then it will call the executable to 
retrieve the environment variables needed for the Deadline Job.
These environment variables are injected into rendering process.

Deadline triggers the `GlobalJobPreLoad.py` for each Worker as it starts the 
Job.  

*Note*: It also contains backward compatible logic to preserve functionality 
for old Pype2 and non-OpenPype triggered jobs.
 
 Plugin
 ------
 For each render and publishing job the `AYON` Deadline Plug-in is checked 
 for the configured location of the OpenPype executable (needs to be configured 
 in `Deadline's Configure Plugins > OpenPype`) through `GlobalJobPreLoad`.

Unreal5 Plugin
--------------
Whole Unreal5 plugin copied here as it is not possible to add to custom folder only `JobPreLoad.py` and `UnrealSyncUtil.py` which is handling Perforce. 
Might need to be revisited as this would create dependency on official Unreal5 plugin.

`JobPreLoad.py` and `UnrealSyncUtil.py` handles Perforce syncing, must be triggered before Unreal rendering job. 
It would better to have here only these two files here, but deployment wouldn't be straightforward copy as for other plugins.
 
 
