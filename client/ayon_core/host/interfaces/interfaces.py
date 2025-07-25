from abc import abstractmethod

from .exceptions import MissingMethodsError


class ILoadHost:
    """Implementation requirements to be able use reference of representations.

    The load plugins can do referencing even without implementation of methods
    here, but switch and removement of containers would not be possible.

    Questions:
        - Is list container dependency of host or load plugins?
        - Should this be directly in HostBase?
            - how to find out if referencing is available?
            - do we need to know that?
    """

    @staticmethod
    def get_missing_load_methods(host):
        """Look for missing methods on "old type" host implementation.

        Method is used for validation of implemented functions related to
        loading. Checks only existence of methods.

        Args:
            Union[ModuleType, HostBase]: Object of host where to look for
                required methods.

        Returns:
            list[str]: Missing method implementations for loading workflow.
        """

        if isinstance(host, ILoadHost):
            return []

        required = ["ls"]
        missing = []
        for name in required:
            if not hasattr(host, name):
                missing.append(name)
        return missing

    @staticmethod
    def validate_load_methods(host):
        """Validate implemented methods of "old type" host for load workflow.

        Args:
            Union[ModuleType, HostBase]: Object of host to validate.

        Raises:
            MissingMethodsError: If there are missing methods on host
                implementation.
        """
        missing = ILoadHost.get_missing_load_methods(host)
        if missing:
            raise MissingMethodsError(host, missing)

    @abstractmethod
    def get_containers(self):
        """Retrieve referenced containers from scene.

        This can be implemented in hosts where referencing can be used.

        Todo:
            Rename function to something more self explanatory.
                Suggestion: 'get_containers'

        Returns:
            list[dict]: Information about loaded containers.
        """

        pass

    # --- Deprecated method names ---
    def ls(self):
        """Deprecated variant of 'get_containers'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.get_containers()


class IPublishHost:
    """Functions related to new creation system in new publisher.

    New publisher is not storing information only about each created instance
    but also some global data. At this moment are data related only to context
    publish plugins but that can extend in future.
    """

    @staticmethod
    def get_missing_publish_methods(host):
        """Look for missing methods on "old type" host implementation.

        Method is used for validation of implemented functions related to
        new publish creation. Checks only existence of methods.

        Args:
            Union[ModuleType, HostBase]: Host module where to look for
                required methods.

        Returns:
            list[str]: Missing method implementations for new publisher
                workflow.
        """

        if isinstance(host, IPublishHost):
            return []

        required = [
            "get_context_data",
            "update_context_data",
            "get_context_title",
            "get_current_context",
        ]
        missing = []
        for name in required:
            if not hasattr(host, name):
                missing.append(name)
        return missing

    @staticmethod
    def validate_publish_methods(host):
        """Validate implemented methods of "old type" host.

        Args:
            Union[ModuleType, HostBase]: Host module to validate.

        Raises:
            MissingMethodsError: If there are missing methods on host
                implementation.
        """
        missing = IPublishHost.get_missing_publish_methods(host)
        if missing:
            raise MissingMethodsError(host, missing)

    @abstractmethod
    def get_context_data(self):
        """Get global data related to creation-publishing from workfile.

        These data are not related to any created instance but to whole
        publishing context. Not saving/returning them will cause that each
        reset of publishing resets all values to default ones.

        Context data can contain information about enabled/disabled publish
        plugins or other values that can be filled by artist.

        Returns:
            dict: Context data stored using 'update_context_data'.
        """

        pass

    @abstractmethod
    def update_context_data(self, data, changes):
        """Store global context data to workfile.

        Called when some values in context data has changed.

        Without storing the values in a way that 'get_context_data' would
        return them will each reset of publishing cause loose of filled values
        by artist. Best practice is to store values into workfile, if possible.

        Args:
            data (dict): New data as are.
            changes (dict): Only data that has been changed. Each value has
                tuple with '(<old>, <new>)' value.
        """

        pass


class INewPublisher(IPublishHost):
    """Legacy interface replaced by 'IPublishHost'.

    Deprecated:
        'INewPublisher' is replaced by 'IPublishHost' please change your
        imports.
        There is no "reasonable" way hot mark these classes as deprecated
        to show warning of wrong import. Deprecated since 3.14.* will be
        removed in 3.15.*
    """

    pass
