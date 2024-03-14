# Copyright Epic Games, Inc. All Rights Reserved

from Deadline.Scripting import *
import UnrealSyncUtil
import os
from Deadline.Scripting import FileUtils


# This is executed on the Slave prior to it attempting to execute a task.
# We use this to sync to the specified changelist and build the project
def __main__( deadlinePlugin ):
    #
    # Retrieve the settings from the job so we know which branch/stream/target this is.
    #
    stream      = deadlinePlugin.GetPluginInfoEntry("PerforceStream")
    if not stream:
        print("Perforce info not collected, skipping!")
    changelist  = int(deadlinePlugin.GetPluginInfoEntryWithDefault("PerforceChangelist", "0"))
    gamePath    = deadlinePlugin.GetPluginInfoEntry("PerforceGamePath")
    projectFile = deadlinePlugin.GetPluginInfoEntry("ProjectFile")
    editorName  = deadlinePlugin.GetPluginInfoEntry("EditorExecutableName")
    if not editorName:
        editorName = projectFile.replace('.uproject','Editor')

    bForceClean       = deadlinePlugin.GetPluginInfoEntryWithDefault("ForceClean",       "false").lower() == "true"
    bForceFullSync    = deadlinePlugin.GetPluginInfoEntryWithDefault("ForceFullSync",    "false").lower() == "true"
    bSyncProject      = deadlinePlugin.GetPluginInfoEntryWithDefault("SyncProject",      "true" ).lower() == "true"
    bSyncEntireStream = deadlinePlugin.GetPluginInfoEntryWithDefault("SyncEntireStream", "false").lower() == "true"
    bBuildProject     = True 

    print("bSyncProject::: "      + str(bSyncProject))
    print("bSyncEntireStream: " + str(bSyncEntireStream))


    #
    # Set up PerforceUtil 
    #

    try:
        env = os.environ.copy()
        env["P4PORT"] = deadlinePlugin.GetProcessEnvironmentVariable("P4PORT")
        env["P4USER"] = deadlinePlugin.GetProcessEnvironmentVariable("P4USER")
        env["P4PASSWD"] = deadlinePlugin.GetProcessEnvironmentVariable("P4PASSWD")
        print(f"env::{env}")
        perforceTools = UnrealSyncUtil.PerforceUtils(stream, gamePath, env)
    except UnrealSyncUtil.PerforceError as pe:
        # Catch environment configuration errors.
        deadlinePlugin.FailRender(pe.message)


    # Automatically determine a perforce workspace for this local machine
    try:
        deadlinePlugin.SetStatusMessage("Determining Workspace")
        deadlinePlugin.LogInfo("Determining client workspace for %s on %s" % (stream, perforceTools.localHost))
        deadlinePlugin.SetProgress(0)
        perforceTools.DetermineClientWorkspace()
    except UnrealSyncUtil.PerforceArgumentError as argError:
        deadlinePlugin.LogWarning(argError.message)
        deadlinePlugin.FailRender(argError.message)
    except UnrealSyncUtil.PerforceMissingWorkspaceError as argError:
        deadlinePlugin.LogWarning(argError.message)
        deadlinePlugin.FailRender(argError.message)
    except UnrealSyncUtil.PerforceMultipleWorkspaceError as argError:
        deadlinePlugin.LogWarning(argError.message)
        deadlinePlugin.FailRender(argError.message)    

    # Set project root
    # This resolves gamePath in case it contains "...""
    try:
        deadlinePlugin.SetStatusMessage("Determining project root")
        deadlinePlugin.LogInfo("Determining project root for %s" % (projectFile))
        deadlinePlugin.SetProgress(0)
        perforceTools.DetermineProjectRoot( projectFile )
    except UnrealSyncUtil.PerforceError as argError:
        deadlinePlugin.LogWarning(argError.message)
        deadlinePlugin.FailRender(argError.message)
    
    projectRoot = perforceTools.projectRoot.replace('\\','/')
    deadlinePlugin.LogInfo( "Storing UnrealProjectRoot (\"%s\") in environment variable..." % projectRoot )
    deadlinePlugin.SetProcessEnvironmentVariable( "UnrealProjectRoot", projectRoot )

    project_path = os.path.join(projectRoot, projectFile)
    deadlinePlugin.LogInfo( "Storing UnrealUProject (\"%s\") in environment variable..." % project_path )
    deadlinePlugin.SetProcessEnvironmentVariable( "UnrealUProject", project_path )


    # Set the option if it's syncing entire stream or just game path
    perforceTools.SetSyncEntireStream( bSyncEntireStream ) 

    #
    # Clean workspace
    #
    if bForceFullSync:
        deadlinePlugin.LogWarning("A full perforce sync is queued, this will take some time.")
    elif bForceClean:
        # We don't bother doing a clean if they're doing a force full sync.
        deadlinePlugin.LogInfo("Performing a perforce clean to bring local files in sync with depot.")
        perforceTools.CleanWorkspace()
        deadlinePlugin.LogInfo("Finished p4 clean.")
    
    deadlinePlugin.LogInfo("Perforce Command Prefix: " + " ".join(perforceTools.GetP4CommandPrefix()))
    
    # Determine the latest changelist to sync to if unspecified.
    try:
        if changelist == 0:
            deadlinePlugin.LogInfo("No changelist specified, determining latest...")
            perforceTools.DetermineLatestChangelist()
            deadlinePlugin.LogInfo("Determined %d as latest." % perforceTools.changelist)
        else:
            deadlinePlugin.LogInfo("Syncing to manually specified CL %d." % changelist)
            perforceTools.setChangelist(changelist)
    except UnrealSyncUtil.PerforceResponseError as argError:
        deadlinePlugin.LogWarning(str(argError))
        deadlinePlugin.LogWarning("Changelist will be latest in subsequent commands.")


    #
    # Sync project
    #       
    if bSyncProject:

        # Estimate how much work there is to do for a sync operation.
        try:
            deadlinePlugin.SetStatusMessage("Estimating work for Project sync (CL %d)" % perforceTools.changelist)
            deadlinePlugin.LogInfo("Estimating work for Project sync (CL %d)" % perforceTools.changelist)
            perforceTools.DetermineSyncWorkEstimate(bForceFullSync)
        except UnrealSyncUtil.PerforceResponseError as argError:
            deadlinePlugin.LogWarning(str(argError))
            deadlinePlugin.LogWarning("No sync estimates will be available.")
            
        # If there's no files to sync, let's skip running the sync. It takes a lot of time as it's a double-estimate.
        if perforceTools.syncEstimates[0] == 0 and perforceTools.syncEstimates[1] == 0 and perforceTools.syncEstimates[2] == 0:
            deadlinePlugin.LogInfo("Skipping sync command as estimated says there's no work to sync!")
        else:
            # Sync to the changelist already calculated.
            try:
                deadlinePlugin.SetStatusMessage("Syncing to CL %d" % perforceTools.changelist)
                deadlinePlugin.LogInfo("Syncing to CL %d" % perforceTools.changelist)
                deadlinePlugin.SetProgress(0)
                deadlinePlugin.LogInfo("Estimated Files %s (added/updated/deleted)" % ("/".join(map(str, perforceTools.syncEstimates))))
                
                logCallback = lambda tools: deadlinePlugin.SetProgress(perforceTools.GetSyncProgress() * 100)

                
                # Perform the sync. This could take a while.
                perforceTools.Sync(logCallback, bForceFullSync)
                    
                # The estimates are only estimates, so when the command is complete we'll ensure  it looks complete.
                deadlinePlugin.SetStatusMessage("Synced Workspace to CL " + str(perforceTools.changelist))
                deadlinePlugin.LogInfo("Synced Workspace to CL " + str(perforceTools.changelist))
                deadlinePlugin.SetProgress(100)
            except IOError as ioError:
                deadlinePlugin.LogWarning(str(ioError))
                deadlinePlugin.FailRender("Suspected Out of Disk Error while syncing: \"%s\"" % str(ioError))
    else:
        deadlinePlugin.LogInfo("Skipping Project Sync due to job settings.")
        


    #      
    # Build project
    #
    if bBuildProject:
        # BuildUtils requires engine root to determine a path to UnrealBuildTool
        # Using Deadline system to determine the path to the executable
        version = deadlinePlugin.GetPluginInfoEntry("EngineVersion")
        deadlinePlugin.LogInfo('Version defined: %s' % version )
        version_string = str(version).replace(".", "_")
        executable_key = f"UnrealEditorExecutable_{version_string}"
        unreal_exe_list = (deadlinePlugin.GetEnvironmentVariable(executable_key)
            or deadlinePlugin.GetEnvironmentVariable("UnrealExecutable"))
        unreal_exe_list = r"C:\Program Files\Epic Games\UE_5.3\Engine\Binaries\Win64\UnrealEditor-Cmd.exe"  # TODO TEMP!
        if not unreal_exe_list:
            deadlinePlugin.FailRender( "Unreal Engine " + str(version) + " entry not found in .param file" )
        unreal_executable = FileUtils.SearchFileList( unreal_exe_list )
        if unreal_executable == "":
            err_msg = 'Unreal Engine %s executable was not found in the semicolon separated list \"%s\".' % (str(version), str(unreal_exe_list))
            deadlinePlugin.FailRender( err_msg )

        unreal_executable = unreal_executable.replace('\\','/')
        engine_root = unreal_executable.split('/Engine/Binaries/')[0]

        uproject_path = perforceTools.uprojectPath
                
        buildtool = UnrealSyncUtil.BuildUtils( engine_root, uproject_path, editorName )

        if not buildtool.IsCppProject():
            deadlinePlugin.LogInfo("Skip building process -- no need to build for BP project")
        else:
            deadlinePlugin.LogInfo("Starting a local build")

            try:                
                deadlinePlugin.LogInfo("Generating project files...")
                deadlinePlugin.SetStatusMessage("Generating project files")
                buildtool.GenerateProjectFiles()
            except Exception as e:
                deadlinePlugin.LogWarning("Caught exception while generating project files. " + str(e))
                deadlinePlugin.FailRender(str(e))

            try:
                deadlinePlugin.LogInfo("Building Engine...")
                deadlinePlugin.SetStatusMessage("Building Engine")
                buildtool.BuildBuildTargets()
            except Exception as e:
                deadlinePlugin.LogWarning("Caught exception while building engine. " + str(e))
                deadlinePlugin.FailRender(str(e))


    deadlinePlugin.LogInfo("Content successfully synced and engine up to date!")
    deadlinePlugin.SetStatusMessage("Content Synced & Engine Up to Date")
    deadlinePlugin.SetProgress(100)

