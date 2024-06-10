#  Copyright Epic Games, Inc. All Rights Reserved

import os
from abc import abstractmethod
import traceback

from deadline_rpc.client import RPCClient

import unreal
import __main__


class _RPCContextManager:
    """
    Context manager used for automatically marking a task as complete after
    the statement is done executing
    """

    def __init__(self, proxy, task_id):
        """
        Constructor
        """
        # RPC Client proxy
        self._proxy = proxy

        # Current task id
        self._current_task_id = task_id

    def __enter__(self):
        return self._proxy

    def __exit__(self, exc_type, exc_val, exc_tb):
        """
        Called when the context manager exits
        """
        # Tell the server the task is complete
        self._proxy.complete_task(self._current_task_id)


class BaseRPC:
    """
    Base class for communicating with a Deadline RPC server. It is
    recommended this class is subclassed for any script that need to
    communicate with deadline. The class automatically handles connecting and
    marking tasks as complete when some abstract methods are implemented
    """

    def __init__(self, port=None, ignore_rpc=False, verbose=False):
        """
        This allows you to get an instance of the class without expecting
        an automatic connection to a rpc server. This will allow you to have
        a class that can both be executed in a deadline commandline interface or
        as a class instance.
        :param port: Optional port to connect to
        :param ignore_rpc: Flag to short circuit connecting to a rpc server
        """
        self._ignore_rpc = ignore_rpc
        self._proxy = None
        if not self._ignore_rpc:
            if not port:
                try:
                    port = os.environ["DEADLINE_RPC_PORT"]
                except KeyError:
                    raise RuntimeError(
                        "There was no port specified for the rpc server"
                    )

            self._port = int(port)

            # Make a connection to the RPC server
            self._proxy = self.__establish_connection()

        self.current_task_id = -1  # Setting this to -1 allows us to
        # render the first task. i.e task 0
        self._get_next_task = True
        self._tick_handle = None

        self._verbose_logging = verbose

        # Set up a property to notify the class when a task is complete
        self.__create_on_task_complete_global()
        self.task_complete = False
        self._sent_task_status = False

        # Start getting tasks to process
        self._execute()

    @staticmethod
    def __create_on_task_complete_global():
        """
        Creates a property in the globals that allows fire and forget tasks
        to notify the class when a task is complete and allowing it to get
        the next task
        :return:
        """
        if not hasattr(__main__, "__notify_task_complete__"):
            __main__.__notify_task_complete__ = False

        return __main__.__notify_task_complete__

    def __establish_connection(self):
        """
        Makes a connection to the Deadline RPC server
        """
        print(f"Connecting to rpc server on port `{self._port}`")
        try:
            _client = RPCClient(port=int(self._port))
            proxy = _client.proxy
            proxy.connect()
        except Exception:
            raise
        else:
            if not proxy.is_connected():
                raise RuntimeError(
                    "A connection could not be made with the server"
                )
            print(f"Connection to server established!")
            return proxy

    def _wait_for_next_task(self, delta_seconds):
        """
        Checks to see if there are any new tasks and executes when there is
        :param delta_seconds:
        :return:
        """

        # skip if our task is the same as previous
        if self.proxy.get_task_id() == self.current_task_id:
            if self._verbose_logging:
                print("Waiting on next task..")
            return

        print("New task received!")

        # Make sure we are explicitly told the task is complete by clearing
        # the globals when we get a new task
        __main__.__notify_task_complete__ = False
        self.task_complete = False

        # Unregister the tick handle and execute the task
        unreal.unregister_slate_post_tick_callback(self._tick_handle)
        self._tick_handle = None

        # Set the current task and execute
        self.current_task_id = self.proxy.get_task_id()
        self._get_next_task = False

        print(f"Executing task `{self.current_task_id}`")
        self.proxy.set_status_message("Executing task command")

        # Execute the next task
        # Make sure we fail the job if we encounter any exceptions and
        # provide the traceback to the proxy server
        try:
            self.execute()
        except Exception:
            trace = traceback.format_exc()
            print(trace)
            self.proxy.fail_render(trace)
            raise

        # Start a non-blocking loop that waits till its notified a task is
        # complete
        self._tick_handle = unreal.register_slate_post_tick_callback(
            self._wait_on_task_complete
        )

    def _wait_on_task_complete(self, delta_seconds):
        """
        Waits till a task is mark as completed
        :param delta_seconds:
        :return:
        """
        if self._verbose_logging:
            print("Waiting on task to complete..")
        if not self._sent_task_status:
            self.proxy.set_status_message("Waiting on task completion..")
            self._sent_task_status = True
        if __main__.__notify_task_complete__ or self.task_complete:

            # Exiting the waiting loop
            unreal.unregister_slate_post_tick_callback(self._tick_handle)
            self._tick_handle = None

            print("Task marked complete. Getting next Task")
            self.proxy.set_status_message("Task complete!")

            # Reset the task status notification
            self._sent_task_status = False

            # Automatically marks a task complete when the execute function
            # exits
            with _RPCContextManager(self.proxy, self.current_task_id):

                self._get_next_task = True

            # This will allow us to keep getting tasks till the process is
            # closed
            self._execute()

    def _execute(self):
        """
        Start the execution process
        """

        if self._get_next_task and not self._ignore_rpc:

            # register a callback with the editor that will check and execute
            # the task on editor tick
            self._tick_handle = unreal.register_slate_post_tick_callback(
                self._wait_for_next_task
            )

    @property
    def proxy(self):
        """
        Returns an instance of the Client proxy
        :return:
        """
        if not self._proxy:
            raise RuntimeError("There is no connected proxy!")

        return self._proxy

    @property
    def is_connected(self):
        """
        Property that returns if a connection was made with the server
        :return:
        """
        return self.proxy.is_connected()

    @abstractmethod
    def execute(self):
        """
        Abstract methods that is executed to perform a task job/command.
        This method must be implemented when communicating with a Deadline
        RPC server
        :return:
        """
        pass
