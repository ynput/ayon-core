import subprocess
import re
import socket
import os
from xml.sax.handler import property_declaration_handler
import zipfile
import time
import stat
import threading
import platform

try:
    import queue
except ImportError:
    import Queue as queue

"""
Utility tools to sync and build projects in remote machines.
Currently it supports Perforce only, but user can implement other source control system (i.e. git)
"""


class UnrealToolError(Exception):
    pass


class PerforceError(UnrealToolError):
    def __init__(self, message):
        self.message = message

    def __str__(self):
        return repr(self.message)


class PerforceArgumentError(PerforceError):
    """An exception that is raised when a perforce command is executed but is missing required arguments.

    Attributes:
        message -- programmer defined message
    """

    pass


class PerforceMissingWorkspaceError(PerforceError):
    def __init__(self, hostName, streamName):
        self.message = 'Could not find a workspace for stream: "%s" on host: "%s"' % (
            streamName,
            hostName,
        )


class PerforceMultipleWorkspaceError(PerforceError):
    def __init__(self, hostName, streamName, count):
        self.message = (
            'Found multiple(%d) workspaces for stream: "%s" on host: "%s"'
            % (count, streamName, hostName)
        )


class PerforceResponseError(PerforceError):
    def __init__(self, message, command, response):
        self.message = '%s. Executed Command: "%s". Got Response: "%s"' % (
            message,
            " ".join(command),
            response,
        )


class PerforceMultipleProjectError(PerforceError):
    def __init__(self, path, count):
        self.message = 'Found multiple(%d) uproject files with this path: "%s"' % (
            count,
            path,
        )


class PerforceProjectNotFoundError(PerforceError):
    def __init__(self, path):
        self.message = 'Could not find a uproject file with this path: "%s"' % (path)


class StoppableThread(threading.Thread):
    def __init__(self, process, _queue, *args, **kwargs):
        super(StoppableThread, self).__init__(*args, **kwargs)
        self.stopEvent = threading.Event()
        self.process = process
        self.queue = _queue

    def stop(self):
        self.stopEvent.set()

    def run(self):
        while True:
            if self.stopEvent.isSet():
                return
            try:
                for line in iter(self.process.stdout.readline, b""):
                    self.queue.put(line)
                self.process.stdout.close()
            except ValueError:
                # File most likely closed so stop trying to queue output.
                return


class PerforceUtils(object):
    def __init__(self, stream, gamePath, env):
        # The hostname of the perforce server. Defaults to the "P4PORT" Environment Var.
        self._serverName = self._FindServerHostName()
        if not self._serverName:
            raise PerforceError('"P4PORT" has not been set in the Slave environment!')

        # The hostname of the local computer. Defaults to the local hostname.
        self._localHost = socket.gethostname()

        # Which stream should the perforce commands be executed for.
        # Assumes a workspace exists on this machine for that stream.
        # (Removing '/' in the end)
        self._stream = re.sub("/$", "", stream)  # str

        # Store game name so that we can sync project only (not entire stream)
        self._gamePath = gamePath

        # The change list that the sync operations should sync to.
        self._changelist = 0  # int

        # The workspace the perforce commands should be executed for.
        # Can be automatically determined with DetermineClientWorkspace()
        self._clientWorkspace = None  # str

        # The root on the local machine that the workspace is based out of.
        # Can be automatically determined with DetermineClientWorkspace()
        self._workspaceRoot = None  # str

        # Sync Estimates calculated by DetermineSyncWorkEstimate
        self._syncEstimates = [0, 0, 0]  # [int,int,int]
        self._syncResults = [0, 0, 0]  # [int,int, int]

        # Sync entire stream or just game path
        self._bSyncAll = False

        # Name of the uproject file
        self._uprojectFile = None

        self._env = env

    @property
    def workspaceRoot(self):
        return self._workspaceRoot

    @property
    def changelist(self):
        return self._changelist

    @property
    def syncEstimates(self):
        return tuple(self._syncEstimates)

    @property
    def localHost(self):
        self._localHost

    @property
    def serverName(self):
        self._serverName

    @property
    def projectRoot(self):
        return "%s/%s" % (self._workspaceRoot, self._gamePath)

    @property
    def uprojectPath(self):
        return "%s/%s" % (self.projectRoot, self._uprojectFile)

    def setChangelist(self, value):
        self._changelist = value

    def _FindServerHostName(self):
        # The hostname of the perforce server. Defaults to the "P4PORT" Environment Var.
        # If it's not set, try to find it from 'p4 set' command
        name = os.getenv("P4PORT")
        if name:
            return name
        output = subprocess.check_output(["p4", "set"])
        for line in output.splitlines():
            m = re.search("(?<=P4PORT=)(.*:\d+)", line)
            if m:
                return m.group()

    def SetSyncEntireStream(self, bSyncAll):
        self._bSyncAll = bSyncAll

    #
    # Automatically determine the client workspace by iterating through
    # available workspaces for the local host machine
    #
    # Raises PerforceMultipleWrokspaceError when multiple workspaces are found for this host/stream.
    # (i.e. a render host is also artist workstation where one workspace for artist and another for render job)
    # This code should be modified to handle the case (i.e. determine by workspace name)
    #
    def DetermineClientWorkspace(self):
        if not self._stream:
            raise PerforceArgumentError("stream must be set to retrieve workspaces")
        if not self._localHost:
            raise PerforceArgumentError(
                "localHostName must be set to retrieve workspaces"
            )

        cmd = [
            "p4",
            "-ztag",
            "-F",
            '"%client%,%Root%,%Host%"',
            "workspaces",
            "-S",
            self._stream,
        ]

        result = subprocess.check_output(cmd, env=self._env)
        print(">>>>result {}".format(result))
        result = result.splitlines()
        local_workspaces = []

        for line in result:
            line = str(line).strip()
            match = re.search('"(.*),(.*),(.*)"', line)
            if match:
                workspace, root, host = match.groups()
                if host.lower() == self._localHost.lower():
                    local_workspaces.append((workspace, root))

        if not local_workspaces:
            raise PerforceMissingWorkspaceError(self._localHost, self._stream)
        elif len(local_workspaces) > 1:
            raise PerforceMultipleWorkspaceError(
                self._localHost, self._stream, len(local_workspaces)
            )

        workspace, root = local_workspaces[0]
        print(
            "Successfully found perforce workspace: %s on this host: %s"
            % (workspace, self._localHost)
        )
        self._clientWorkspace = workspace
        self._workspaceRoot = root

    def DetermineProjectRoot(self, uprojectFile):
        # Find project file from workspaceRoot. If gamePath contains '...', it should try to search the path recursively
        # 2023-04-06 18:31:56:  0: PYTHON: {'self': <UnrealSyncUtil.PerforceUtils object at 0x00000291C0830A90>, 'uprojectFile': u'DLFarmTests.uproject', 'cmd': ['p4', '-p', '10.10.10.162:1666', '-c', 'DLFarmTests_bepic-devtop01', 'files', u'//dl-farm-test/mainline///DLFarmTests.uproject'], 'result': [], 'search_path': u'//dl-farm-test/mainline///DLFarmTests.uproject'}

        if not self._gamePath:
            search_path = self._stream + "/" + uprojectFile
        else:
            search_path = self._stream + "/" + self._gamePath + "/" + uprojectFile
        cmd = self.GetP4CommandPrefix() + ["files", search_path]
        result = subprocess.check_output(cmd, env=self._env)
        result = result.splitlines()

        if len(result) == 0:
            raise PerforceProjectNotFoundError(search_path)
        elif len(result) > 1:
            raise PerforceMultipleProjectError(search_path, len(result))
        result = result[0]
        # m = re.search("%s/(.*)/%s" % (self._stream, uprojectFile), str(result))
        m = re.search("%s/.*/?%s#.*" % (self._stream, uprojectFile), str(result))
        if not m:
            raise PerforceError("Unable to parse project path: %s" % str(result))

        # self._gamePath = m.group(1)
        self._uprojectFile = uprojectFile
        print("ProjectRoot: %s" % self.projectRoot)

    def DetermineLatestChangelist(self):

        sync_path = self._stream
        if not self._bSyncAll:
            sync_path = self._stream

        # Default to no cl so that if one of the below checks fails it still gets latest.
        self._changelist = 0
        latest_cl_command = self.GetP4CommandPrefix() + [
            "changes",
            "-m1",
            sync_path + "/...",
        ]
        print("Determining latest CL using: " + " ".join(latest_cl_command))

        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW

        # proc = subprocess.Popen(latest_cl_command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, startupinfo=info)
        # result = proc.stdout.readline().strip()

        result = subprocess.check_output(latest_cl_command, startupinfo=info,
                                         env=self._env)

        print("Result: {}".format(result))
        if not result.startswith("Change "):
            raise PerforceResponseError(
                "Failed to get latest changelist for stream", latest_cl_command, result
            )

        clTest = re.search("(?<=Change )(\S*)(?= )", result)
        if clTest is None:
            raise PerforceResponseError(
                "Failed to parse response for latest changelist",
                latest_cl_command,
                result,
            )

        self._changelist = int(clTest.group())
        print("Changelist set: %d" % self._changelist)

    def DetermineSyncWorkEstimate(self, bForceSync=False):
        # Get an estimate on how much syncing there is to do.
        sync_estimate_command = self._BuildSyncCommand(
            bForceSync=bForceSync, bDryRun=True
        )
        info = subprocess.STARTUPINFO()
        info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        result = subprocess.check_output(sync_estimate_command, 
                                         startupinfo=info,
                                         env=self._env)

        print(f"Sync Estimate Result: {result}")

        estimate_success = False
        lines = result.splitlines()
        for line in lines:
            # Should return in the form "Server network estimates: files added/updated/deleted=x/y/z, bytes..."
            estimateResult = re.search("(?<=deleted=)(\S*)(?=,)", str(line))
            if estimateResult:
                estimate_success = True
                estimates = list(map(int, estimateResult.group().split("/")))
                self._syncEstimates[0] += estimates[0]  # added
                self._syncEstimates[1] += estimates[1]  # updated
                self._syncEstimates[2] += estimates[2]  # deleted

        if not estimate_success:
            self._syncEstimates = [
                -1,
                -1,
                -1,
            ]  # Progress will be wrong but no need to crash over it. Don't use 0 here because 0 is a valid estimate (already sync'd)
            raise PerforceResponseError(
                "Failed to get estimated work for sync operation.",
                sync_estimate_command,
                result,
            )

    def CleanWorkspace(self):
        sync_path = self._stream
        if not self._bSyncAll:
            sync_path = self._stream + "/" + self._gamePath

        clean_command = self.GetP4CommandPrefix() + [
            "clean",
            "-e",
            "-a",
            "-d",
            "-m",
            sync_path + "/...",
        ]  # "]#, "-m"]
        print("Cleaning using: " + " ".join(clean_command))

        result = ""
        try:
            result = subprocess.check_output(clean_command,
                                             env=self._env)
        except subprocess.CalledProcessError as e:
            print("Clean: %s" % str(e))

        print("Clean Result: " + result)

    # Build a perforce sync command based on the options
    def _BuildSyncCommand(self, bForceSync=False, bDryRun=False):

        sync_files = []
        if self._bSyncAll:
            sync_files.append("")
        else:
            sync_files.append("%s/..." % (self._stream))

        if self._changelist > 0:
            for i in range(len(sync_files)):
                sync_files[i] += "@%d" % self._changelist

        sync_command = self.GetP4CommandPrefix() + ["sync"]
        if bDryRun:
            sync_command.append("-N")
        else:
            sync_command.append("--parallel=threads=8")

        if bForceSync:
            sync_command.append("-f")

        sync_command.extend(sync_files)

        return sync_command

    def Sync(self, progressCallback=None, bForceSync=False):
        syncCommand = self._BuildSyncCommand(bForceSync=bForceSync, bDryRun=False)

        print("Sync Command: " + " ".join(syncCommand))

        self._syncResults = [0, 0, 0]

        process = subprocess.Popen(
            syncCommand, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            env=self._env
        )

        stdoutQueue = queue.Queue()
        # stdoutThread = threading.Thread(target=queueStdout, args=(process, stdoutQueue))
        stdoutThread = StoppableThread(process, stdoutQueue)
        stdoutThread.daemon = True
        stdoutThread.start()

        while process.poll() is None:
            while not stdoutQueue.empty():
                stdOutLine = stdoutQueue.get_nowait()
                print(stdOutLine)
                stdOutLine = str(stdOutLine)

                if (
                    "The system cannot find the file specified." in stdOutLine
                    or "There is not enough space on the disk." in stdOutLine
                ):
                    raise IOError(
                        'Suspected Out of Disk Error while syncing: "%s"' % stdOutLine
                    )

                # Look for either "deleted", "updated", or "added" and add to our results array.
                if "added" in stdOutLine:
                    self._syncResults[0] += 1
                if "updated" in stdOutLine:
                    self._syncResults[1] += 1
                if "refreshing" in stdOutLine:
                    self._syncResults[
                        1
                    ] += (
                        1  # This is a guess that refreshing in a full sync is the same.
                    )
                if "deleted" in stdOutLine:
                    self._syncResults[2] += 1

                if progressCallback is not None:
                    progressCallback(self)

        print("process.poll returned a code, sync finished. Calling Stop")
        stdoutThread.stop()
        print("called stop. calling join.")
        stdoutThread.join()
        print("called join.")

        # One more progress callback to ensure we're at 1.0
        if progressCallback is not None:
            progressCallback(1)

    # Generate the prefix for perforce commands that need user/workspace for scope.
    def GetP4CommandPrefix(self):  # -> str[]
        return ["p4", "-p", self._serverName, "-c", self._clientWorkspace]

    # Get the sync progress for the current or last sync (Range: 0-1)
    def GetSyncProgress(self):  # -> float
        # Totals
        total_operations_est = float(
            self._syncEstimates[0] + self._syncEstimates[1] + self._syncEstimates[2]
        )
        total_operations = float(
            self._syncResults[0] + self._syncResults[1] + self._syncResults[2]
        )

        if total_operations > 0:
            return total_operations / total_operations_est

        return 0


class BuildUtils(object):
    def __init__(self, engineRoot, uprojectPath, editorName):

        self.engineRoot = engineRoot.replace("\\", "/")
        self.uprojectPath = uprojectPath.replace("\\", "/")
        self.editorName = editorName
        print("engine_root: %s" % self.engineRoot)
        print("uproject_path: %s" % self.uprojectPath)
        print("editor_name: %s" % self.editorName)

    def IsSourceBuildEngine(self):
        items = os.listdir(self.engineRoot)
        items = [
            item for item in items if re.search("GenerateProjectFiles", item, re.I)
        ]
        return len(items) > 0

    def IsCppProject(self):
        project_root = os.path.dirname(self.uprojectPath)
        items = os.listdir(project_root)
        items = [item for item in items if re.search("Source", item, re.I)]
        return len(items) > 0

    def GetGenerateProjectFileProgram(self):
        system = platform.system()

        if system == "Windows":
            paths = [
                os.path.join(self.engineRoot, "GenerateProjectFiles.bat"),
                os.path.join(
                    self.engineRoot,
                    "Engine",
                    "Build",
                    "BatchFiles",
                    "GenerateProjectFiles.bat",
                ),
                os.path.join(
                    self.engineRoot,
                    "Engine",
                    "Binaries",
                    "DotNET",
                    "UnrealBuildTool.exe",
                ),
                os.path.join(
                    self.engineRoot,
                    "Engine",
                    "Binaries",
                    "DotNET",
                    "UnrealBuildTool",
                    "UnrealBuildTool.exe",
                ),
            ]

        elif system == "Linux":
            paths = [
                os.path.join(self.engineRoot, "GenerateProjectFiles.sh"),
                os.path.join(
                    self.engineRoot,
                    "Engine",
                    "Build",
                    "BatchFiles",
                    "Linux",
                    "GenerateProjectFiles.sh",
                ),
            ]

        elif system == "Darwin":
            paths = [
                os.path.join(self.engineRoot, "GenerateProjectFiles.sh"),
                os.path.join(
                    self.engineRoot,
                    "Engine",
                    "Build",
                    "BatchFiles",
                    "Mac",
                    "GenerateProjectFiles.sh",
                ),
            ]
        else:
            raise RuntimeError("Platform not supported: %s" % system)

        for path in paths:
            if os.path.exists(path):
                return path
        raise RuntimeError("Failed to find program to generate project files")

    def GetBuildProgram(self):
        system = platform.system()
        if system == "Windows":
            return os.path.join(
                self.engineRoot, "Engine", "Build", "BatchFiles", "Build.bat"
            )
        elif system == "Linux":
            return os.path.join(
                self.engineRoot, "Engine", "Build", "BatchFiles", "Linux", "Build.sh"
            )
        elif system == "Darwin":
            return os.path.join(
                self.engineRoot, "Engine", "Build", "BatchFiles", "Mac", "Build.sh"
            )
        else:
            raise RuntimeError("Platform not supported: %s" % system)

    def GetBuildArgs(self):
        system = platform.system()
        if system == "Windows":
            system = "Win64"
        elif system == "Darwin":
            system = "Mac"

        args = [system, "Development", "-NoHotReloadFromIDE", "-progress"]
        return args

    def GetEditorBuildArgs(self):
        system = platform.system()
        if system == "Windows":
            system = "Win64"
        elif system == "Darwin":
            system = "Mac"

        args = [
            system,
            "Development",
            self.uprojectPath.encode("utf-8"),
            "-NoHotReloadFromIDE",
            "-progress",
        ]
        return args

    def GenerateProjectFiles(self):
        program = self.GetGenerateProjectFileProgram().replace("\\", "/")
        args = [program]
        if re.search("UnrealBuildTool", program.split("/")[-1]):
            args.append("-ProjectFiles")

        args.append(self.uprojectPath)
        args.append("-progress")

        print("Generating Project Files with:  %s" % " ".join(args))
        try:
            process = subprocess.check_output(args, env=self._env)
        except subprocess.CalledProcessError as e:
            print(
                "Exception while generating project files: %s (%s)" % (str(e), e.output)
            )
            raise
        print("Generated Project Files.")

    def BuildBuildTargets(self):
        print("Starting to build targets...")

        build_targets = []
        if self.IsSourceBuildEngine():
            build_targets.append(("UnrealHeaderTool", self.GetBuildArgs()))
            build_targets.append(("ShaderCompileWorker", self.GetBuildArgs()))
            build_targets.append(("CrashReportClient", self.GetBuildArgs()))
            build_targets.append(("UnrealLightmass", self.GetBuildArgs()))

        build_targets.append(
            (self.editorName.encode("utf-8"), self.GetEditorBuildArgs())
        )
        program = self.GetBuildProgram().replace("\\", "/")
        for target, buildArgs in build_targets:
            args = [program, target] + buildArgs
            print("Compiling {}...".format(target))
            print("Command Line: %s" % str(args))
            try:
                process = subprocess.check_output(args, env=self._env)
            except subprocess.CalledProcessError as e:
                print("Exception while building target: %s (%s)" % (str(e), e.output))
                raise

        print("Finished building targets.")
