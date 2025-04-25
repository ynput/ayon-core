from abc import abstractmethod



class IWorkfileHost:
    """Implementation requirements to be able use workfile utils and tool."""


    @abstractmethod
    def get_workfile_extensions(self):
        """Extensions that can be used as save.

        Questions:
            This could potentially use 'HostDefinition'.
        """

        return []

    @abstractmethod
    def save_workfile(self, dst_path=None):
        """Save currently opened scene.

        Args:
            dst_path (str): Where the current scene should be saved. Or use
                current path if 'None' is passed.
        """

        pass

    @abstractmethod
    def open_workfile(self, filepath):
        """Open passed filepath in the host.

        Args:
            filepath (str): Path to workfile.
        """

        pass

    @abstractmethod
    def get_current_workfile(self):
        """Retrieve path to current opened file.

        Returns:
            str: Path to file which is currently opened.
            None: If nothing is opened.
        """

        return None

    def workfile_has_unsaved_changes(self):
        """Currently opened scene is saved.

        Not all hosts can know if current scene is saved because the API of
        DCC does not support it.

        Returns:
            bool: True if scene is saved and False if has unsaved
                modifications.
            None: Can't tell if workfiles has modifications.
        """

        return None

    def work_root(self, session):
        """Modify workdir per host.

        Default implementation keeps workdir untouched.

        Warnings:
            We must handle this modification with more sophisticated way
            because this can't be called out of DCC so opening of last workfile
            (calculated before DCC is launched) is complicated. Also breaking
            defined work template is not a good idea.
            Only place where it's really used and can make sense is Maya. There
            workspace.mel can modify subfolders where to look for maya files.

        Args:
            session (dict): Session context data.

        Returns:
            str: Path to new workdir.
        """

        return session["AYON_WORKDIR"]

    # --- Deprecated method names ---
    def file_extensions(self):
        """Deprecated variant of 'get_workfile_extensions'.

        Todo:
            Remove when all usages are replaced.
        """
        return self.get_workfile_extensions()

    def save_file(self, dst_path=None):
        """Deprecated variant of 'save_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        self.save_workfile(dst_path)

    def open_file(self, filepath):
        """Deprecated variant of 'open_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.open_workfile(filepath)

    def current_file(self):
        """Deprecated variant of 'get_current_workfile'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.get_current_workfile()

    def has_unsaved_changes(self):
        """Deprecated variant of 'workfile_has_unsaved_changes'.

        Todo:
            Remove when all usages are replaced.
        """

        return self.workfile_has_unsaved_changes()