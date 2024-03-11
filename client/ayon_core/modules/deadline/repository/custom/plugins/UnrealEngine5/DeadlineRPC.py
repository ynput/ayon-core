#  Copyright Epic Games, Inc. All Rights Reserved

from ue_utils.rpc.server import RPCServerThread
from ue_utils.rpc.base_server import BaseRPCServerManager

from Deadline.Scripting import RepositoryUtils


class BaseDeadlineRPCJobManager:
    """
    This is a base class for exposing commonly used deadline function on RPC
    """

    def __init__(self):
        """
        Constructor
        """
        # get the instance of the deadline plugin from the python globals
        self._deadline_plugin = self.__get_instance_from_globals()

        # Get the current running job
        self._job = self._deadline_plugin.GetJob()
        self._is_connected = False

        # Track all completed tasks
        self._completed_tasks = set()

    def connect(self):
        """
        First mode of contact to the rpc server. It is very critical the
        client calls this function first as it will let the Deadline process
        know a client has connected and to wait on the task to complete.
        Else, Deadline will assume the connection was never made and requeue
        the job after a few minutes
        :return: bool representing the connection
        """
        self._is_connected = True
        print("Server connection established!")
        return self._is_connected

    def is_connected(self):
        """
        Returns the connection status to a client
        :return:
        """
        return self._is_connected

    def is_task_complete(self, task_id):
        """
        Checks and returns if a task has been marked as complete
        :param task_id: job task id
        :return: return True/False if the task id is present
        """
        return task_id in self._completed_tasks

    @staticmethod
    def __get_instance_from_globals():
        """
        Get the instance of the Deadline plugin from the python globals.
        Since this class is executed in a thread, this was the best method to
        get the plugin instance to the class without pass it though several
        layers of abstraction
        :return:
        """
        import __main__

        try:
            return __main__.__deadline_plugin_instance__
        except AttributeError as err:
            raise RuntimeError(
                f"Could not get deadline plugin instance from globals. "
                f"\n\tError: {err}"
            )

    def get_job_id(self):
        """
        Returns the current JobID
        :return: Job ID
        """
        return self._job.JobId

    def get_task_frames(self):
        """
        Returns the frames rendered by ths task
        :return:
        """
        return [
            self._deadline_plugin.GetStartFrame(),
            self._deadline_plugin.GetEndFrame()
        ]

    def get_job_extra_info_key_value(self, name):
        """
        Returns the value of a key in the job extra info property
        :param name: Extra Info Key
        :return: Returns Extra Info Value
        """
        # This function is probably the most important function in the class.
        # This allows you to store different types of data and retrieve the
        # data from the other side. This is what makes the Unreal plugin a bit
        # more feature/task agnostic
        return self._job.GetJobExtraInfoKeyValue(name)

    def fail_render(self, message):
        """
        Fail a render job with a message
        :param message: Failure message
        """
        self._deadline_plugin.FailRender(message.strip("\n"))
        return True

    def set_status_message(self, message):
        """
        Sets the message on the job status
        :param message: Status Message
        """
        self._deadline_plugin.SetStatusMessage(message)
        return True

    def set_progress(self, progress):
        """
        Sets the job progress
        :param progress: job progress
        """
        self._deadline_plugin.SetProgress(progress)
        return True

    def log_warning(self, message):
        """
        Logs a warning message
        :param message: Log message
        """
        self._deadline_plugin.LogWarning(message)
        return True

    def log_info(self, message):
        """
        Logs an informational message
        :param message: Log message
        """
        self._deadline_plugin.LogInfo(message)
        return True

    def get_task_id(self):
        """
        Returns the current Task ID
        :return:
        """
        return self._deadline_plugin.GetCurrentTaskId()

    def get_job_user(self):
        """
        Return the job user
        :return:
        """
        return self._job.JobUserName

    def complete_task(self, task_id):
        """
        Marks a task as complete. This function should be called when a task
        is complete. This will allow the Deadline render taskl process to end
        and get the next render task. If this is not called, deadline will
        render the task indefinitely
        :param task_id: Task ID to mark as complete
        :return:
        """
        self._completed_tasks.add(task_id)
        return True

    def update_job_output_filenames(self, filenames):
        """
        Updates the file names for the current job
        :param list filenames: list of filenames
        """
        if not isinstance(filenames, list):
            filenames = list(filenames)

        self._deadline_plugin.LogInfo(
            "Setting job filenames: {filename}".format(
                filename=", ".join(filenames)
            )
        )

        # Set the file names on the job
        RepositoryUtils.UpdateJobOutputFileNames(self._job, filenames)

        # Make sure to save the settings just in case
        RepositoryUtils.SaveJob(self._job)

    def update_job_output_directories(self, directories):
        """
        Updates the output directories on job
        :param list directories: List of directories
        """
        if not isinstance(directories, list):
            directories = list(directories)

        self._deadline_plugin.LogInfo(
            "Setting job directories: {directories}".format(
                directories=", ".join(directories)
            )
        )

        # Set the directory on the job
        RepositoryUtils.SetJobOutputDirectories(self._job, directories)

        # Make sure to save the settings just in case
        RepositoryUtils.SaveJob(self._job)

    def check_path_mappings(self, paths):
        """
        Resolves any path mappings set on input path
        :param [str] paths: Path string with tokens
        :return: Resolved path mappings
        """
        if not isinstance(paths, list):
            paths = list(paths)

        # Deadline returns a System.String[] object here. Convert to a proper
        # list
        path_mapped_strings = RepositoryUtils.CheckPathMappingForMultiplePaths(
            paths,
            forceSeparator="/",
            verbose=False
        )

        return [str(path) for path in path_mapped_strings]


class DeadlineRPCServerThread(RPCServerThread):
    """
    Deadline server thread
    """

    deadline_job_manager = None

    def __init__(self, name, port):
        super(DeadlineRPCServerThread, self).__init__(name, port)
        if self.deadline_job_manager:
            self.deadline_job_manager = self.deadline_job_manager()
        else:
            self.deadline_job_manager = BaseDeadlineRPCJobManager()

        # Register our instance on the server
        self.server.register_instance(
            self.deadline_job_manager,
            allow_dotted_names=True
        )


class DeadlineRPCServerManager(BaseRPCServerManager):
    """
    RPC server manager class. This class is responsible for registering a
    server thread class and starting the thread. This can be a blocking or
    non-blocking thread
    """

    def __init__(self, deadline_plugin, port):
        super(DeadlineRPCServerManager, self).__init__()
        self.name = "DeadlineRPCServer"
        self.port = port
        self.is_started = False
        self.__make_plugin_instance_global(deadline_plugin)

    @staticmethod
    def __make_plugin_instance_global(deadline_plugin_instance):
        """
        Puts an instance of the deadline plugin in the python globals. This
        allows the server thread to get the plugin instance without having
        the instance passthrough abstraction layers
        :param deadline_plugin_instance: Deadline plugin instance
        :return:
        """
        import __main__

        if not hasattr(__main__, "__deadline_plugin_instance__"):
            __main__.__deadline_plugin_instance__ = None

        __main__.__deadline_plugin_instance__ = deadline_plugin_instance

    def start(self, threaded=True):
        """
        Starts the server thread
        :param threaded: Run as threaded or blocking
        :return:
        """
        super(DeadlineRPCServerManager, self).start(threaded=threaded)
        self.is_started = True

    def client_connected(self):
        """
        Check if there is a client connected
        :return:
        """
        if self.server_thread:
            return self.server_thread.deadline_job_manager.is_connected()
        return False

    def get_temporary_client_proxy(self):
        """
        This returns client proxy and is not necessarily expected to be used
        for server communication but for mostly queries.
        NOTE: This behavior is implied
        :return: RPC client proxy
        """
        from ue_utils.rpc.client import RPCClient

        # Get the port the server is using
        server = self.get_server()
        _, server_port = server.socket.getsockname()
        return RPCClient(port=int(server_port)).proxy

    def shutdown(self):
        """
        Stops the server and shuts down the thread
        :return:
        """
        super(DeadlineRPCServerManager, self).shutdown()
        self.is_started = False
