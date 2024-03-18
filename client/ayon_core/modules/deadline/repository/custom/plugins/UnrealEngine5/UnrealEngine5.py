#!/usr/bin/env python3
#  Copyright Epic Games, Inc. All Rights Reserved

import os
import time
import sys
from datetime import datetime
from pathlib import Path

from Deadline.Plugins import DeadlinePlugin, PluginType
from FranticX.Processes import ManagedProcess
from Deadline.Scripting import RepositoryUtils, FileUtils, StringUtils

from DeadlineRPC import (
    DeadlineRPCServerManager,
    DeadlineRPCServerThread,
    BaseDeadlineRPCJobManager
)


def GetDeadlinePlugin():
    """
    Deadline calls this function to get am instance of our class
    """
    return UnrealEnginePlugin()


def CleanupDeadlinePlugin(deadline_plugin):
    """
    Deadline call this function to run any cleanup code
    :param deadline_plugin: An instance of the deadline plugin
    """
    deadline_plugin.clean_up()


class UnrealEnginePlugin(DeadlinePlugin):
    """
    Deadline plugin to execute an Unreal Engine job.
    NB: This plugin makes no assumptions about what the render job is but has a
    few expectations. This plugin runs as a server in the deadline process
    and exposes a few Deadline functionalities over XML RPC. The managed process
    used by this plugin waits for a client to connect and continuously polls the
    RPC server till a task has been marked complete before exiting the
    process. This behavior however has a drawback. If for some reason your
    process does not mark a task complete after working on a command,
    the plugin will run the current task indefinitely until specified to
    end by the repository settings or manually.
    """

    def __init__(self):
        """
        Constructor
        """
        if sys.version_info.major == 3:
            super().__init__()
        self.InitializeProcessCallback += self._on_initialize_process
        self.StartJobCallback += self._on_start_job
        self.RenderTasksCallback += self._on_render_tasks
        self.EndJobCallback += self._on_end_job
        self.MonitoredManagedProcessExitCallback += self._on_process_exit

        # Set the name of the managed process to the current deadline process ID
        self._unreal_process_name = f"UnrealEngine_{os.getpid()}"
        self.unreal_managed_process = None

        # Keep track of the RPC manager
        self._deadline_rpc_manager = None

        # Keep track of when Job Ended has been called
        self._job_ended = False

        # set the plugin to commandline mode by default. This will launch the
        # editor and wait for the process to exit. There is no communication
        # with the deadline process.
        self._commandline_mode = True

    def clean_up(self):
        """
        Plugin cleanup
        """
        del self.InitializeProcessCallback
        del self.StartJobCallback
        del self.RenderTasksCallback
        del self.EndJobCallback

        if self.unreal_managed_process:
            self.unreal_managed_process.clean_up()
            del self.unreal_managed_process

        del self.MonitoredManagedProcessExitCallback

    def _on_initialize_process(self):
        """
        Initialize the plugin
        """
        self.LogInfo("Initializing job plugin")
        self.SingleFramesOnly = False
        self.StdoutHandling = True
        self.PluginType = PluginType.Advanced
        self._commandline_mode = StringUtils.ParseBoolean(
            self.GetPluginInfoEntryWithDefault("CommandLineMode", "true")
        )

        if self._commandline_mode:
            self.AddStdoutHandlerCallback(
                ".*Progress: (\d+)%.*"
            ).HandleCallback += self._handle_progress
            self.AddStdoutHandlerCallback(
                ".*"
            ).HandleCallback += self._handle_stdout

        self.LogInfo("Initialization complete!")

    def _on_start_job(self):
        """
        This is executed when the plugin picks up a job
        """

        # Skip if we are in commandline mode
        if self._commandline_mode:
            return

        self.LogInfo("Executing Start Job")

        # Get and set up the RPC manager for the plugin
        self._deadline_rpc_manager = self._setup_rpc_manager()

        # Get a managed process
        self.unreal_managed_process = UnrealEngineManagedProcess(
            self._unreal_process_name, self, self._deadline_rpc_manager
        )
        self.LogInfo("Done executing Start Job")

    def _setup_rpc_manager(self):
        """
        Get an RPC manager for the plugin.
        """
        self.LogInfo("Setting up RPC Manager")
        # Setting the port to `0` will get a random available port for the
        # processes to connect on. This will help avoid TIME_WAIT
        # issues with the client if the job has to be re-queued
        port = 0

        # Get an instance of the deadline rpc manager class. This class will
        # store an instance of this plugin in the python globals. This should
        # allow threads in the process to get an instance of the plugin without
        # passing the data down through the thread instance
        _deadline_rpc_manager = DeadlineRPCServerManager(self, port)

        # We would like to run the server in a thread to not block deadline's
        # process. Get the Deadline RPC thread class. Set the class that is
        # going to be registered on the server on the thread class
        DeadlineRPCServerThread.deadline_job_manager = BaseDeadlineRPCJobManager

        # Set the threading class on the deadline manager
        _deadline_rpc_manager.threaded_server_class = DeadlineRPCServerThread

        return _deadline_rpc_manager

    def _on_render_tasks(self):
        """
        Execute the render task
        """
        # This starts a self-managed process that terminates based on the exit
        # code of the process. 0 means success
        if self._commandline_mode:
            startup_dir = self._get_startup_directory()

            self.unreal_managed_process = UnrealEngineCmdManagedProcess(
                self, self._unreal_process_name, startup_dir=startup_dir
            )

            # Auto execute the managed process
            self.RunManagedProcess(self.unreal_managed_process)
            exit_code = self.unreal_managed_process.ExitCode  # type: ignore

            self.LogInfo(f"Process returned: {exit_code}")

            if exit_code != 0:
                self.FailRender(
                    f"Process returned non-zero exit code '{exit_code}'"
                )

        else:
            # Flush stdout. This is useful after executing the first task
            self.FlushMonitoredManagedProcessStdout(self._unreal_process_name)

            # Start next tasks
            self.LogWarning(f"Starting Task {self.GetCurrentTaskId()}")

            # Account for any re-queued jobs. Deadline will immediately execute
            # render tasks if a job has been re-queued on the same process. If
            # that happens get a new instance of the rpc manager
            if not self._deadline_rpc_manager or self._job_ended:
                self._deadline_rpc_manager = self._setup_rpc_manager()

            if not self._deadline_rpc_manager.is_started:

                # Start the manager
                self._deadline_rpc_manager.start(threaded=True)

                # Get the socket the server is using and expose it to the
                # process
                server = self._deadline_rpc_manager.get_server()

                _, server_port = server.socket.getsockname()

                self.LogWarning(
                    f"Starting Deadline RPC Manager on port `{server_port}`"
                )

                # Get the port the server socket is going to use and
                # allow other systems to get the port to the rpc server from the
                # process environment variables
                self.SetProcessEnvironmentVariable(
                    "DEADLINE_RPC_PORT", str(server_port)
                )

            # Fail if we don't have an instance to a managed process.
            # This should typically return true
            if not self.unreal_managed_process:
                self.FailRender("There is no unreal process Running")

            if not self.MonitoredManagedProcessIsRunning(self._unreal_process_name):
                # Start the monitored Process
                self.StartMonitoredManagedProcess(
                    self._unreal_process_name,
                    self.unreal_managed_process
                )

                self.VerifyMonitoredManagedProcess(self._unreal_process_name)

            # Execute the render task
            self.unreal_managed_process.render_task()

            self.LogWarning(f"Finished Task {self.GetCurrentTaskId()}")
            self.FlushMonitoredManagedProcessStdout(self._unreal_process_name)

    def _on_end_job(self):
        """
        Called when the job ends
        """
        if self._commandline_mode:
            return

        self.FlushMonitoredManagedProcessStdout(self._unreal_process_name)
        self.LogWarning("EndJob called")
        self.ShutdownMonitoredManagedProcess(self._unreal_process_name)

        # Gracefully shutdown the RPC manager. This will also shut down any
        # threads spun up by the manager
        if self._deadline_rpc_manager:
            self._deadline_rpc_manager.shutdown()

        # Mark the job as ended. This also helps us to know when a job has
        # been re-queued, so we can get a new instance of the RPC manager,
        # as Deadline calls End Job when an error occurs
        self._job_ended = True

    def _on_process_exit(self):
        # If the process ends unexpectedly, make sure we shut down the manager
        # gracefully
        if self._commandline_mode:
            return

        if self._deadline_rpc_manager:
            self._deadline_rpc_manager.shutdown()

    def _handle_stdout(self):
        """
        Handle stdout
        """
        self._deadline_plugin.LogInfo(self.GetRegexMatch(0))

    def _handle_progress(self):
        """
        Handles any progress reports
        :return:
        """
        progress = float(self.GetRegexMatch(1))
        self.SetProgress(progress)

    def _get_startup_directory(self):
        """
        Get startup directory
        """
        startup_dir = self.GetPluginInfoEntryWithDefault(
            "StartupDirectory", ""
        ).strip()
        # Get the project root path
        project_root = self.GetProcessEnvironmentVariable("ProjectRoot")

        if startup_dir:
            if project_root:
                startup_dir = startup_dir.format(ProjectRoot=project_root)

            self.LogInfo("Startup Directory: {dir}".format(dir=startup_dir))
            return startup_dir.replace("\\", "/")


class UnrealEngineManagedProcess(ManagedProcess):
    """
    Process for executing and managing an unreal jobs.

    .. note::

        Although this process can auto start a batch process by
        executing a script on startup, it is VERY important the command
        that is executed on startup makes a connection to the Deadline RPC
        server.
        This will allow Deadline to know a task is running and will wait
        until the task is complete before rendering the next one. If this
        is not done, Deadline will assume something went wrong with the
        process and fail the job after a few minutes. It is also VERY
        critical the Deadline process is told when a task is complete, so
        it can move on to the next one. See the Deadline RPC manager on how
        this communication system works.
        The reason for this complexity is, sometimes an unreal project can
        take several minutes to load, and we only want to bare the cost of
        that load time once between tasks.

    """

    def __init__(self, process_name, deadline_plugin, deadline_rpc_manager):
        """
        Constructor
        :param process_name: The name of this process
        :param deadline_plugin: An instance of the plugin
        :param deadline_rpc_manager: An instance of the rpc manager
        """
        if sys.version_info.major == 3:
            super().__init__()
        self.InitializeProcessCallback += self._initialize_process
        self.RenderExecutableCallback += self._render_executable
        self.RenderArgumentCallback += self._render_argument
        self._deadline_plugin = deadline_plugin
        self._deadline_rpc_manager = deadline_rpc_manager
        self._temp_rpc_client = None
        self._name = process_name
        self._executable_path = None

        # Elapsed time to check for connection
        self._process_wait_time = int(self._deadline_plugin.GetConfigEntryWithDefault("RPCWaitTime", "300"))

    def clean_up(self):
        """
        Called when the plugin cleanup is called
        """
        self._deadline_plugin.LogInfo("Executing managed process cleanup.")
        # Clean up stdout handler callbacks.
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback
        self._deadline_plugin.LogInfo("Managed Process Cleanup Finished.")

    def _initialize_process(self):
        """
        Called by Deadline to initialize the process.
        """
        self._deadline_plugin.LogInfo(
            "Executing managed process Initialize Process."
        )

        # Set the ManagedProcess specific settings.
        self.PopupHandling = False
        self.StdoutHandling = True

        # Set the stdout handlers.

        self.AddStdoutHandlerCallback(
            "LogPython: Error:.*"
        ).HandleCallback += self._handle_stdout_error
        self.AddStdoutHandlerCallback(
            "Warning:.*"
        ).HandleCallback += self._handle_stdout_warning

        logs_dir = self._deadline_plugin.GetPluginInfoEntryWithDefault(
            "LoggingDirectory", ""
        )

        if logs_dir:

            job = self._deadline_plugin.GetJob()

            log_file_dir = os.path.join(
                job.JobName,
                f"{job.JobSubmitDateTime.ToUniversalTime()}".replace(" ", "-"),
            )

            if not os.path.exists(log_file_dir):
                os.makedirs(log_file_dir)

            # If a log directory is specified, this may redirect stdout to the
            # log file instead. This is a builtin Deadline behavior
            self.RedirectStdoutToFile(
                os.path.join(
                    log_file_dir,
                    f"{self._deadline_plugin.GetSlaveName()}_{datetime.now()}.log".replace(" ", "-")
                )
            )

    def _handle_std_out(self):
        self._deadline_plugin.LogInfo(self.GetRegexMatch(0))

    # Callback for when a line of stdout contains a WARNING message.
    def _handle_stdout_warning(self):
        self._deadline_plugin.LogWarning(self.GetRegexMatch(0))

    # Callback for when a line of stdout contains an ERROR message.
    def _handle_stdout_error(self):
        self._deadline_plugin.FailRender(self.GetRegexMatch(0))

    def render_task(self):
        """
        Render a task
        """

        # Fail the render is we do not have a manager running
        if not self._deadline_rpc_manager:
            self._deadline_plugin.FailRender("No rpc manager was running!")

        # Start a timer to monitor the process time
        start_time = time.time()

        # Get temp client connection
        if not self._temp_rpc_client:
            self._temp_rpc_client = self._deadline_rpc_manager.get_temporary_client_proxy()


        print("Is server and client connected?", self._temp_rpc_client.is_connected())

        # Make sure we have a manager running, and we can establish a connection
        if not self._temp_rpc_client.is_connected():
            # Wait for a connection. This polls the server thread till an
            # unreal process client has connected. It is very important that
            # a connection is established by the client to allow this process
            # to execute.
            while round(time.time() - start_time) <= self._process_wait_time:
                try:
                    # keep checking to see if a client has connected
                    if self._temp_rpc_client.is_connected():
                        self._deadline_plugin.LogInfo(
                            "Client connection established!!"
                        )
                        break
                except Exception:
                    pass

                self._deadline_plugin.LogInfo("Waiting on client connection..")
                self._deadline_plugin.FlushMonitoredManagedProcessStdout(
                    self._name
                )
                time.sleep(2)
            else:

                # Fail the render after waiting too long
                self._deadline_plugin.FailRender(
                    "A connection was not established with an unreal process"
                )

        # if we are connected, wait till the process task is marked as
        # complete.
        while not self._temp_rpc_client.is_task_complete(
            self._deadline_plugin.GetCurrentTaskId()
        ):
            # Keep flushing stdout
            self._deadline_plugin.FlushMonitoredManagedProcessStdout(self._name)

        # Flush one last time
        self._deadline_plugin.FlushMonitoredManagedProcessStdout(self._name)

    def _render_executable(self):
        """
        Get the render executable
        """
        self._deadline_plugin.LogInfo("Setting up Render Executable")

        executable = self._deadline_plugin.GetEnvironmentVariable("UnrealExecutable")

        if not executable:
            executable = self._deadline_plugin.GetPluginInfoEntry("Executable")

        # Resolve any path mappings required
        executable = RepositoryUtils.CheckPathMapping(executable)

        project_root = self._deadline_plugin.GetEnvironmentVariable("ProjectRoot")

        # If a project root is specified in the environment, it is assumed a
        # previous process resolves the root location of the executable and
        # presents it in the environment.
        if project_root:
            # Resolve any `{ProjectRoot}` tokens present in the executable path
            executable = executable.format(ProjectRoot=project_root)

        # Make sure the executable exists
        if not FileUtils.FileExists(executable):
            self._deadline_plugin.FailRender(f"Could not find `{executable}`")

        self._executable_path = executable.replace("\\", "/")

        self._deadline_plugin.LogInfo(f"Found executable `{executable}`")

        return self._executable_path

    def _render_argument(self):
        """
        Get the arguments to startup unreal
        """
        self._deadline_plugin.LogInfo("Settifdfdsfsdfsfsfasng UP Render Arguments")

        # Look for any unreal uproject paths in the process environment. This
        # assumes a previous process resolves a uproject path and makes it
        # available.
        uproject = self._deadline_plugin.GetEnvironmentVariable("UnrealUProject")

        if not uproject:
            uproject = self._deadline_plugin.GetPluginInfoEntry("ProjectFile")
        self._deadline_plugin.LogInfo(f"hhhh")
        # Get any path mappings required. Expects this to be a full path
        uproject = RepositoryUtils.CheckPathMapping(uproject)

        # Get the project root path
        project_root = self._deadline_plugin.GetEnvironmentVariable("ProjectRoot")

        # Resolve any `{ProjectRoot}` tokens in the environment
        if project_root:
            uproject = uproject.format(ProjectRoot=project_root)

        uproject = Path(uproject.replace("\\", "/"))
        self._deadline_plugin.LogInfo(f"Suproject:: `{uproject}`")
        # Check to see if the Uproject is a relative path
        if str(uproject).replace("\\", "/").startswith("../"):

            if not self._executable_path:
                self._deadline_plugin.FailRender("Could not find executable path to resolve relative path.")

            # Find executable root
            import re
            engine_dir = re.findall("([\s\S]*.Engine)", self._executable_path)
            if not engine_dir:
                self._deadline_plugin.FailRender("Could not find executable Engine directory.")

            executable_root = Path(engine_dir[0]).parent

            # Resolve editor relative paths
            found_paths = sorted(executable_root.rglob(str(uproject).replace("\\", "/").strip("../")))

            if not found_paths or len(found_paths) > 1:
                self._deadline_plugin.FailRender(
                    f"Found multiple uprojects relative to the root directory. There should only be one when a relative path is defined."
                )

            uproject = found_paths[0]

        # make sure the project exists
        if not FileUtils.FileExists(uproject.as_posix()):
            self._deadline_plugin.FailRender(f"Could not find `{uproject.as_posix()}`")
        self._deadline_plugin.GetPluginInfoEntryWithDefault("CommandLineArguments", "")
        # Set up the arguments to startup unreal.
        job_command_args = [
            '"{u_project}"'.format(u_project=uproject.as_posix()),
            cmd_args,
            # Force "-log" otherwise there is no output from the executable
            "-log",
            "-unattended",
            "-stdout",
            "-allowstdoutlogverbosity",
        ]

        arguments = " ".join(job_command_args)
        self._deadline_plugin.LogInfo(f"Startup Arguments: `{arguments}`")

        return arguments


class UnrealEngineCmdManagedProcess(ManagedProcess):
    """
    Process for executing unreal over commandline
    """

    def __init__(self, deadline_plugin, process_name, startup_dir=""):
        """
        Constructor
        :param process_name: The name of this process
        """
        if sys.version_info.major == 3:
            super().__init__()
        self._deadline_plugin = deadline_plugin
        self._name = process_name
        self.ExitCode = -1
        self._startup_dir = startup_dir
        self._executable_path = None

        self.InitializeProcessCallback += self._initialize_process
        self.RenderExecutableCallback += self._render_executable
        self.RenderArgumentCallback += self._render_argument
        self.CheckExitCodeCallback += self._check_exit_code
        self.StartupDirectoryCallback += self._startup_directory

    def clean_up(self):
        """
        Called when the plugin cleanup is called
        """
        self._deadline_plugin.LogInfo("Executing managed process cleanup.")
        # Clean up stdout handler callbacks.
        for stdoutHandler in self.StdoutHandlers:
            del stdoutHandler.HandleCallback

        del self.InitializeProcessCallback
        del self.RenderExecutableCallback
        del self.RenderArgumentCallback
        del self.CheckExitCodeCallback
        del self.StartupDirectoryCallback
        self._deadline_plugin.LogInfo("Managed Process Cleanup Finished.")

    def _initialize_process(self):
        """
        Called by Deadline to initialize the process.
        """
        self._deadline_plugin.LogInfo(
            "Executing managed process Initialize Process."
        )

        # Set the ManagedProcess specific settings.
        self.PopupHandling = True
        self.StdoutHandling = True
        self.HideDosWindow = True

        # Ensure child processes are killed and the parent process is
        # terminated on exit
        self.UseProcessTree = True
        self.TerminateOnExit = True

        shell = self._deadline_plugin.GetPluginInfoEntryWithDefault("Shell", "")

        if shell:
            self._shell = shell

        self.AddStdoutHandlerCallback(
            ".*Progress: (\d+)%.*"
        ).HandleCallback += self._handle_progress

        # self.AddStdoutHandlerCallback("LogPython: Error:.*").HandleCallback += self._handle_stdout_error

        # Get the current frames for the task
        current_task_frames = self._deadline_plugin.GetCurrentTask().TaskFrameString

        # Set the frames sting as an environment variable
        self.SetEnvironmentVariable("CURRENT_RENDER_FRAMES", current_task_frames)

    def _handle_stdout_error(self):
        """
        Callback for when a line of stdout contains an ERROR message.
        """
        self._deadline_plugin.FailRender(self.GetRegexMatch(0))

    def _check_exit_code(self, exit_code):
        """
        Returns the process exit code
        :param exit_code:
        :return:
        """
        self.ExitCode = exit_code

    def _startup_directory(self):
        """
        Startup directory
        """
        return self._startup_dir

    def _handle_progress(self):
        """
        Handles progress reports
        """
        progress = float(self.GetRegexMatch(1))
        self._deadline_plugin.SetProgress(progress)

    def _render_executable(self):
        """
        Get the render executable
        """

        self._deadline_plugin.LogInfo("Setting up Render Executable")

        executable = self._deadline_plugin.GetEnvironmentVariable("UnrealExecutable")

        if not executable:
            executable = self._deadline_plugin.GetPluginInfoEntry("Executable")

        # Get the executable from the plugin
        executable = RepositoryUtils.CheckPathMapping(executable)
        # Get the project root path
        project_root = self._deadline_plugin.GetProcessEnvironmentVariable(
            "ProjectRoot"
        )

        # Resolve any `{ProjectRoot}` tokens in the environment
        if project_root:
            executable = executable.format(ProjectRoot=project_root)

        if not FileUtils.FileExists(executable):
            self._deadline_plugin.FailRender(
                "{executable} could not be found".format(executable=executable)
            )

        # TODO: Setup getting executable from the config as well

        self._deadline_plugin.LogInfo(
            "Render Executable: {exe}".format(exe=executable)
        )
        self._executable_path = executable.replace("\\", "/")

        return self._executable_path

    def _render_argument(self):
        """
        Get the arguments to startup unreal
        :return:
        """
        self._deadline_plugin.LogInfo("Setting up Render Arguments")

        # Look for any unreal uproject paths in the process environment. This
        # assumes a previous process resolves a uproject path and makes it
        # available.
        project_file = self._deadline_plugin.GetEnvironmentVariable("UnrealUProject")

        if not project_file:
            project_file = self._deadline_plugin.GetPluginInfoEntry("ProjectFile")

        # Get any path mappings required. Expects this to be a full path
        project_file = RepositoryUtils.CheckPathMapping(project_file)

        # Get the project root path
        project_root = self._deadline_plugin.GetProcessEnvironmentVariable(
            "ProjectRoot"
        )

        # Resolve any `{ProjectRoot}` tokens in the environment
        if project_root:
            project_file = project_file.format(ProjectRoot=project_root)

        if not project_file:
            self._deadline_plugin.FailRender(
                f"Expected project file but found `{project_file}`"
            )

        project_file = Path(project_file.replace("\u201c", '"').replace(
            "\u201d", '"'
        ).replace("\\", "/"))

        # Check to see if the Uproject is a relative path
        if str(project_file).replace("\\", "/").startswith("../"):

            if not self._executable_path:
                self._deadline_plugin.FailRender("Could not find executable path to resolve relative path.")

            # Find executable root
            import re
            engine_dir = re.findall("([\s\S]*.Engine)", self._executable_path)
            if not engine_dir:
                self._deadline_plugin.FailRender("Could not find executable Engine directory.")

            executable_root = Path(engine_dir[0]).parent

            # Resolve editor relative paths
            found_paths = sorted(executable_root.rglob(str(project_file).replace("\\", "/").strip("../")))

            if not found_paths or len(found_paths) > 1:
                self._deadline_plugin.FailRender(
                    f"Found multiple uprojects relative to the root directory. There should only be one when a relative path is defined."
                )

            project_file = found_paths[0]
        self._deadline_plugin.LogInfo(f"project_file:: `{project_file}`")
        # make sure the project exists
        if not FileUtils.FileExists(project_file.as_posix()):
            self._deadline_plugin.FailRender(f"Could not find `{project_file.as_posix()}`")

        # Get the render arguments
        args = RepositoryUtils.CheckPathMapping(
            self._deadline_plugin.GetPluginInfoEntry(
                "CommandLineArguments"
            ).strip()
        )

        args = args.replace("\u201c", '"').replace("\u201d", '"')

        startup_args = " ".join(
            [
                '"{u_project}"'.format(u_project=project_file.as_posix()),
                args,
                "-log",
                "-unattended",
                "-stdout",
                "-allowstdoutlogverbosity",
            ]
        )

        self._deadline_plugin.LogInfo(
            "Render Arguments: {args}".format(args=startup_args)
        )

        return startup_args
