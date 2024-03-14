from ayon_core.lib.path_templates import TemplateUnsolved


class ProjectNotSet(Exception):
    """Exception raised when is created Anatomy without project name."""


class RootCombinationError(Exception):
    """This exception is raised when templates has combined root types."""

    def __init__(self, roots):
        joined_roots = ", ".join(
            ["\"{}\"".format(_root) for _root in roots]
        )
        # TODO better error message
        msg = (
            "Combination of root with and"
            " without root name in AnatomyTemplates. {}"
        ).format(joined_roots)

        super(RootCombinationError, self).__init__(msg)


class TemplateMissingKey(Exception):
    """Exception for cases when key does not exist in template."""

    msg = "Template key '{}' was not found."

    def __init__(self, parents):
        parent_join = "".join(["[\"{0}\"]".format(key) for key in parents])
        super(TemplateMissingKey, self).__init__(
            self.msg.format(parent_join)
        )


class AnatomyTemplateUnsolved(TemplateUnsolved):
    """Exception for unsolved template when strict is set to True."""

    msg = "Anatomy template \"{0}\" is unsolved.{1}{2}"
