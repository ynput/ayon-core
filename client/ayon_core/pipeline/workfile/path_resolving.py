from __future__ import annotations
import os
import re
import copy
import platform
import warnings
import typing
from typing import Optional, Dict, Any
from dataclasses import dataclass

import ayon_api

from ayon_core.settings import get_project_settings
from ayon_core.lib import (
    filter_profiles,
    Logger,
    StringTemplate,
)
from ayon_core.pipeline import version_start, Anatomy
from ayon_core.pipeline.template_data import get_template_data

if typing.TYPE_CHECKING:
    from ayon_core.pipeline.anatomy import AnatomyTemplateResult


def get_workfile_template_key_from_context(
    project_name: str,
    folder_path: str,
    task_name: str,
    host_name: str,
    project_settings: Optional[Dict[str, Any]] = None,
) -> str:
    """Helper function to get template key for workfile template.

    Do the same as `get_workfile_template_key` but returns value for "session
    context".

    Args:
        project_name (str): Project name.
        folder_path (str): Folder path.
        task_name (str): Task name.
        host_name (str): Host name.
        project_settings (Dict[str, Any]): Project settings for passed
            'project_name'. Not required at all but makes function faster.

    Returns:
        str: Workfile template name.

    """
    folder_entity = ayon_api.get_folder_by_path(
        project_name,
        folder_path,
        fields={"id"},
    )
    task_entity = ayon_api.get_task_by_name(
        project_name,
        folder_entity["id"],
        task_name,
        fields={"taskType"},
    )
    task_type = task_entity.get("taskType")

    return get_workfile_template_key(
        project_name, task_type, host_name, project_settings
    )


def get_workfile_template_key(
    project_name, task_type, host_name, project_settings=None
):
    """Workfile template key which should be used to get workfile template.

    Function is using profiles from project settings to return right template
    for passed task type and host name.

    Args:
        project_name(str): Project name.
        task_type(str): Task type.
        host_name(str): Host name (e.g. "maya", "nuke", ...)
        project_settings(Dict[str, Any]): Prepared project settings for
            project name. Optional to make processing faster.
    """

    default = "work"
    if not task_type or not host_name:
        return default

    if not project_settings:
        project_settings = get_project_settings(project_name)

    try:
        profiles = (
            project_settings
            ["core"]
            ["tools"]
            ["Workfiles"]
            ["workfile_template_profiles"]
        )
    except Exception:
        profiles = []

    if not profiles:
        return default

    profile_filter = {
        "task_types": task_type,
        "hosts": host_name
    }
    profile = filter_profiles(profiles, profile_filter)
    if profile:
        return profile["workfile_template"] or default
    return default


def get_workdir_with_workdir_data(
    workdir_data,
    project_name,
    anatomy=None,
    template_key=None,
    project_settings=None
) -> "AnatomyTemplateResult":
    """Fill workdir path from entered data and project's anatomy.

    It is possible to pass only project's name instead of project's anatomy but
    one of them **must** be entered. It is preferred to enter anatomy if is
    available as initialization of a new Anatomy object may be time consuming.

    Args:
        workdir_data (Dict[str, Any]): Data to fill workdir template.
        project_name (str): Project's name.
        anatomy (Anatomy): Anatomy object for specific project. Faster
            processing if is passed.
        template_key (str): Key of work templates in anatomy templates. If not
            passed `get_workfile_template_key_from_context` is used to get it.
        project_settings(Dict[str, Any]): Prepared project settings for
            project name. Optional to make processing faster. Ans id used only
            if 'template_key' is not passed.

    Returns:
        AnatomyTemplateResult: Workdir path.

    """
    if not anatomy:
        anatomy = Anatomy(project_name)

    if not template_key:
        template_key = get_workfile_template_key(
            workdir_data["project"]["name"],
            workdir_data["task"]["type"],
            workdir_data["app"],
            project_settings
        )

    template_obj = anatomy.get_template_item(
        "work", template_key, "directory"
    )
    # Output is AnatomyTemplateResult object which contain useful data
    output = template_obj.format_strict(workdir_data)
    if output:
        return output.normalized()
    return output


def get_workdir(
    project_entity: dict[str, Any],
    folder_entity: dict[str, Any],
    task_entity: dict[str, Any],
    host_name: str,
    anatomy=None,
    template_key=None,
    project_settings=None
) -> "AnatomyTemplateResult":
    """Fill workdir path from entered data and project's anatomy.

    Args:
        project_entity (Dict[str, Any]): Project entity.
        folder_entity (Dict[str, Any]): Folder entity.
        task_entity (dict[str, Any]): Task entity.
        host_name (str): Host which is used to workdir. This is required
            because workdir template may contain `{app}` key. In `Session`
            is stored under `AYON_HOST_NAME` key.
        anatomy (Anatomy): Optional argument. Anatomy object is created using
            project name from `project_entity`. It is preferred to pass this
            argument as initialization of a new Anatomy object may be
            time-consuming.
        template_key (str): Key of work templates in anatomy templates. Default
            value is defined in `get_workdir_with_workdir_data`.
        project_settings(Dict[str, Any]): Prepared project settings for
            project name. Optional to make processing faster. Ans id used only
            if 'template_key' is not passed.

    Returns:
        AnatomyTemplateResult: Workdir path.

    """
    if not anatomy:
        anatomy = Anatomy(
            project_entity["name"], project_entity=project_entity
        )

    workdir_data = get_template_data(
        project_entity,
        folder_entity,
        task_entity,
        host_name,
    )
    # Output is AnatomyTemplateResult object which contain useful data
    return get_workdir_with_workdir_data(
        workdir_data,
        anatomy.project_name,
        anatomy,
        template_key,
        project_settings
    )


@dataclass
class WorkfileParsedData:
    version: Optional[int] = None
    comment: Optional[str] = None
    ext: Optional[str] = None


class WorkfileDataParser:
    """Parse dynamic data from existing filenames based on template.

    Args:
        file_template (str): Workfile file template.
        data (dict[str, Any]): Data to fill the template with.

    """
    def __init__(
        self,
        file_template: str,
        data: dict[str, Any],
    ):
        data = copy.deepcopy(data)
        file_template = str(file_template)
        # Use placeholders that will never be in the filename
        ext_replacement = "CIextID"
        version_replacement = "CIversionID"
        comment_replacement = "CIcommentID"
        data["version"] = version_replacement
        data["comment"] = comment_replacement
        for pattern, replacement in (
            # Replace `.{ext}` with `{ext}` so we are sure dot is not at the end
            (r"\.?{ext}", ext_replacement),
        ):
            file_template = re.sub(pattern, replacement, file_template)

        file_template = StringTemplate(file_template)
        comment_template = re.escape(str(file_template.format_strict(data)))
        data.pop("comment")
        file_template = re.escape(str(file_template.format_strict(data)))
        for src, replacement in (
            (ext_replacement, r"(?P<ext>\..*)"),
            (version_replacement, r"(?P<version>[0-9]+)"),
            (comment_replacement, r"(?P<comment>.+?)"),
        ):
            comment_template = comment_template.replace(src, replacement)
            file_template = file_template.replace(src, replacement)

        kwargs = {}
        if platform.system().lower() == "windows":
            kwargs["flags"] = re.IGNORECASE

        # Match from beginning to end of string to be safe
        self._comment_template = re.compile(f"^{comment_template}$", **kwargs)
        self._file_template = re.compile(f"^{file_template}$", **kwargs)

    def parse_data(self, filename: str) -> WorkfileParsedData:
        """Parse the dynamic data from a filename."""
        match = self._comment_template.match(filename)
        if not match:
            match = self._file_template.match(filename)

        if not match:
            return WorkfileParsedData()

        kwargs = match.groupdict()
        version = kwargs.get("version")
        if version is not None:
            kwargs["version"] = int(version)
        return WorkfileParsedData(**kwargs)


def parse_dynamic_data_from_workfile(
    filename: str,
    file_template: str,
    template_data: dict[str, Any],
) -> WorkfileParsedData:
    """Parse dynamic data from a workfile filename.

    Dynamic data are 'version', 'comment' and 'ext'.

    Args:
        filename (str): Workfile filename.
        file_template (str): Workfile file template.
        template_data (dict[str, Any]): Data to fill the template with.

    Returns:
        WorkfileParsedData: Dynamic data parsed from the filename.

    """
    parser = WorkfileDataParser(file_template, template_data)
    return parser.parse_data(filename)


def parse_dynamic_data_from_workfiles(
    filenames: list[str],
    file_template: str,
    template_data: dict[str, Any],
) -> dict[str, WorkfileParsedData]:
    """Parse dynamic data from a workfiles filenames.

    Dynamic data are 'version', 'comment' and 'ext'.

    Args:
        filenames (list[str]): Workfiles filenames.
        file_template (str): Workfile file template.
        template_data (dict[str, Any]): Data to fill the template with.

    Returns:
        dict[str, WorkfileParsedData]: Dynamic data parsed from the filenames
            by filename.

    """
    parser = WorkfileDataParser(file_template, template_data)
    return {
        filename: parser.parse_data(filename)
        for filename in filenames
    }


def get_last_workfile_with_version_from_paths(
    filepaths: list[str],
    file_template: str,
    template_data: dict[str, Any],
    extensions: set[str],
) -> tuple[Optional[str], Optional[int]]:
    """Return last workfile version.

    Using the workfile template and its template data find most possible last
    version of workfile which was created for the context.

    Functionality is fully based on knowing which keys are optional or what
    values are expected as value.

    The last modified file is used if more files can be considered as
    last workfile.

    Args:
        filepaths (list[str]): Workfile paths.
        file_template (str): Template of file name.
        template_data (Dict[str, Any]): Data for filling template.
        extensions (set[str]): All allowed file extensions of workfile.

    Returns:
        tuple[Optional[str], Optional[int]]: Last workfile with version
            if there is any workfile otherwise None for both.

    """
    if not filepaths:
        return None, None

    dotted_extensions = set()
    for ext in extensions:
        if not ext.startswith("."):
            ext = f".{ext}"
        dotted_extensions.add(re.escape(ext))

    # Build template without optionals, version to digits only regex
    # and comment to any definable value.
    # Escape extensions dot for regex
    ext_expression = "(?:" + "|".join(dotted_extensions) + ")"

    for pattern, replacement in (
        # Replace `.{ext}` with `{ext}` so we are sure dot is not at the end
        (r"\.?{ext}", ext_expression),
        # Replace optional keys with optional content regex
        (r"<.*?>", r".*?"),
        # Replace `{version}` with group regex
        (r"{version.*?}", r"([0-9]+)"),
        (r"{comment.*?}", r".+?"),
    ):
        file_template = re.sub(pattern, replacement, file_template)

    file_template = StringTemplate.format_strict_template(
        file_template, template_data
    )

    # Match with ignore case on Windows due to the Windows
    # OS not being case-sensitive. This avoids later running
    # into the error that the file did exist if it existed
    # with a different upper/lower-case.
    kwargs = {}
    if platform.system().lower() == "windows":
        kwargs["flags"] = re.IGNORECASE

    # Get highest version among existing matching files
    version = None
    output_filepaths = []
    for filepath in sorted(filepaths):
        filename = os.path.basename(filepath)
        match = re.match(file_template, filename, **kwargs)
        if not match:
            continue

        if not match.groups():
            output_filepaths.append(filename)
            continue

        file_version = int(match.group(1))
        if version is None or file_version > version:
            output_filepaths.clear()
            version = file_version

        if file_version == version:
            output_filepaths.append(filepath)

    # Use file modification time to use most recent file if there are
    #   multiple workfiles with the same version
    output_filepath = None
    last_time = None
    for _output_filepath in output_filepaths:
        mod_time = None
        if os.path.exists(_output_filepath):
            mod_time = os.path.getmtime(_output_filepath)
        if (
            last_time is None
            or (mod_time is not None and last_time < mod_time)
        ):
            output_filepath = _output_filepath
            last_time = mod_time

    return output_filepath, version


def get_last_workfile_from_paths(
    filepaths: list[str],
    file_template: str,
    template_data: dict[str, Any],
    extensions: set[str],
) -> Optional[str]:
    """Return the last workfile filename.

    Returns the file with version 1 if there is not workfile yet.

    Args:
        filepaths (list[str]): Paths to workfiles.
        file_template (str): Template of file name.
        template_data (dict[str, Any]): Data for filling template.
        extensions (set[str]): All allowed file extensions of workfile.

    Returns:
        Optional[str]: Last workfile path.

    """
    filepath, _version = get_last_workfile_with_version_from_paths(
        filepaths, file_template, template_data, extensions
    )
    return filepath


def _filter_dir_files_by_ext(
    dirpath: str,
    extensions: set[str],
) -> tuple[list[str], set[str]]:
    """Filter files by extensions.

    Args:
        dirpath (str): List of file paths.
        extensions (set[str]): Set of file extensions.

    Returns:
        tuple[list[str], set[str]]: Filtered list of file paths.

    """
    dotted_extensions = set()
    for ext in extensions:
        if not ext.startswith("."):
            ext = f".{ext}"
        dotted_extensions.add(ext)

    if not os.path.exists(dirpath):
        return [], dotted_extensions

    filtered_paths = [
        os.path.join(dirpath, filename)
        for filename in os.listdir(dirpath)
        if os.path.splitext(filename)[-1] in dotted_extensions
    ]
    return filtered_paths, dotted_extensions


def get_last_workfile_with_version(
    workdir: str,
    file_template: str,
    template_data: dict[str, Any],
    extensions: set[str],
) -> tuple[Optional[str], Optional[int]]:
    """Return last workfile version.

    Using the workfile template and its filling data to find the most possible
    last version of workfile which was created for the context.

    Functionality is fully based on knowing which keys are optional or what
    values are expected as value.

    The last modified file is used if more files can be considered as
    last workfile.

    Args:
        workdir (str): Path to dir where workfiles are stored.
        file_template (str): Template of file name.
        template_data (dict[str, Any]): Data for filling template.
        extensions (set[str]): All allowed file extensions of workfile.

    Returns:
        tuple[Optional[str], Optional[int]]: Last workfile with version
            if there is any workfile otherwise None for both.

    """
    if not os.path.exists(workdir):
        return None, None

    filepaths, dotted_extensions = _filter_dir_files_by_ext(
        workdir, extensions
    )

    return get_last_workfile_with_version_from_paths(
        filepaths,
        file_template,
        template_data,
        dotted_extensions,
    )


def get_last_workfile(
    workdir: str,
    file_template: str,
    template_data: dict[str, Any],
    extensions: set[str],
    full_path: bool = False,
) -> str:
    """Return last the workfile filename.

    Returns first file name/path if there are not workfiles yet.

    Args:
        workdir (str): Path to dir where workfiles are stored.
        file_template (str): Template of file name.
        template_data (Dict[str, Any]): Data for filling template.
        extensions (Iterable[str]): All allowed file extensions of workfile.
        full_path (bool): Return full path to the file or only filename.

    Returns:
        str: Last or first workfile file name or path based on
            'full_path' value.

    """
    # TODO (iLLiCiTiT): Remove the argument 'full_path' and return only full
    #   path. As far as I can tell it is always called with 'full_path' set
    #   to 'True'.
    # - it has to be 2 step operation, first warn about having it 'False', and
    #   then warn about having it filled.
    if full_path is False:
        warnings.warn(
            "Argument 'full_path' will be removed and will return"
            " only full path in future.",
            DeprecationWarning,
        )

    filepaths, dotted_extensions = _filter_dir_files_by_ext(
        workdir, extensions
    )
    filepath = get_last_workfile_from_paths(
        filepaths,
        file_template,
        template_data,
        dotted_extensions
    )
    if filepath is None:
        data = copy.deepcopy(template_data)
        data["version"] = version_start.get_versioning_start(
            data["project"]["name"],
            data["app"],
            task_name=data["task"]["name"],
            task_type=data["task"]["type"],
            product_type="workfile"
        )
        data.pop("comment", None)
        if data.get("ext") is None:
            data["ext"] = next(iter(extensions), "")
        data["ext"] = data["ext"].lstrip(".")
        filename = StringTemplate.format_strict_template(file_template, data)
        filepath = os.path.join(workdir, filename)

    if full_path:
        return os.path.normpath(filepath)
    return os.path.basename(filepath)


def get_custom_workfile_template(
    project_entity,
    folder_entity,
    task_entity,
    host_name,
    anatomy=None,
    project_settings=None
):
    """Filter and fill workfile template profiles by passed context.

    Custom workfile template can be used as first version of workfiles.
    Template is a file on a disk which is set in settings. Expected settings
    structure to have this feature enabled is:
    project settings
    |- <host name>
      |- workfile_builder
        |- create_first_version   - a bool which must be set to 'True'
        |- custom_templates       - profiles based on task name/type which
                                    points to a file which is copied as
                                    first workfile

    It is expected that passed argument are already queried entities of
    project and folder as parents of processing task name.

    Args:
        project_entity (Dict[str, Any]): Project entity.
        folder_entity (Dict[str, Any]): Folder entity.
        task_entity (Dict[str, Any]): Task entity.
        host_name (str): Name of host.
        anatomy (Anatomy): Optionally passed anatomy object for passed project
            name.
        project_settings(Dict[str, Any]): Preloaded project settings.

    Returns:
        Optional[str]: Path to template or None if none of profiles match
            current context. Existence of formatted path is not validated.

    """
    log = Logger.get_logger("CustomWorkfileResolve")

    project_name = project_entity["name"]
    if project_settings is None:
        project_settings = get_project_settings(project_name)

    host_settings = project_settings.get(host_name)
    if not host_settings:
        log.info("Host \"{}\" doesn't have settings".format(host_name))
        return None

    workfile_builder_settings = host_settings.get("workfile_builder")
    if not workfile_builder_settings:
        log.info((
            "Seems like old version of settings is used."
            " Can't access custom templates in host \"{}\"."
        ).format(host_name))
        return

    if not workfile_builder_settings["create_first_version"]:
        log.info((
            "Project \"{}\" has turned off to create first workfile for"
            " host \"{}\""
        ).format(project_name, host_name))
        return

    # Backwards compatibility
    template_profiles = workfile_builder_settings.get("custom_templates")
    if not template_profiles:
        log.info(
            "Custom templates are not filled. Skipping template copy."
        )
        return

    if anatomy is None:
        anatomy = Anatomy(project_name)

    # get project, folder, task anatomy context data
    anatomy_context_data = get_template_data(
        project_entity, folder_entity, task_entity, host_name
    )
    # add root dict
    anatomy_context_data["root"] = anatomy.roots

    # get task type for the task in context
    current_task_type = anatomy_context_data["task"]["type"]

    # get path from matching profile
    matching_item = filter_profiles(
        template_profiles,
        {"task_types": current_task_type}
    )
    # when path is available try to format it in case
    # there are some anatomy template strings
    if matching_item:
        # extend anatomy context with os.environ to
        # also allow formatting against env
        full_context_data = os.environ.copy()
        full_context_data.update(anatomy_context_data)

        template = matching_item["path"][platform.system().lower()]
        return StringTemplate.format_strict_template(
            template, full_context_data
        ).normalized()

    return None


def get_custom_workfile_template_by_string_context(
    project_name,
    folder_path,
    task_name,
    host_name,
    anatomy=None,
    project_settings=None
):
    """Filter and fill workfile template profiles by passed context.

    Passed context are string representations of project, folder and task.
    Function will query documents of project and folder to be able to use
    `get_custom_workfile_template` for rest of logic.

    Args:
        project_name (str): Project name.
        folder_path (str): Folder path.
        task_name (str): Task name.
        host_name (str): Name of host.
        anatomy (Anatomy): Optionally prepared anatomy object for passed
            project.
        project_settings (Dict[str, Any]): Preloaded project settings.

    Returns:
        Union[str, None]: Path to template or None if none of profiles match
            current context. (Existence of formatted path is not validated.)

    """

    project_entity = ayon_api.get_project(project_name)
    folder_entity = ayon_api.get_folder_by_path(project_name, folder_path)
    task_entity = ayon_api.get_task_by_name(
        project_name, folder_entity["id"], task_name
    )

    return get_custom_workfile_template(
        project_entity,
        folder_entity,
        task_entity,
        host_name,
        anatomy,
        project_settings
    )


def create_workdir_extra_folders(
    workdir,
    host_name,
    task_type,
    task_name,
    project_name,
    project_settings=None
):
    """Create extra folders in work directory based on context.

    Args:
        workdir (str): Path to workdir where workfiles is stored.
        host_name (str): Name of host implementation.
        task_type (str): Type of task for which extra folders should be
            created.
        task_name (str): Name of task for which extra folders should be
            created.
        project_name (str): Name of project on which task is.
        project_settings (dict): Prepared project settings. Are loaded if not
            passed.
    """

    # Load project settings if not set
    if not project_settings:
        project_settings = get_project_settings(project_name)

    # Load extra folders profiles
    extra_folders_profiles = (
        project_settings["core"]["tools"]["Workfiles"]["extra_folders"]
    )
    # Skip if are empty
    if not extra_folders_profiles:
        return

    # Prepare profiles filters
    filter_data = {
        "task_types": task_type,
        "task_names": task_name,
        "hosts": host_name
    }
    profile = filter_profiles(extra_folders_profiles, filter_data)
    if profile is None:
        return

    for subfolder in profile["folders"]:
        # Make sure backslashes are converted to forwards slashes
        #   and does not start with slash
        subfolder = subfolder.replace("\\", "/").lstrip("/")
        # Skip empty strings
        if not subfolder:
            continue

        fullpath = os.path.join(workdir, subfolder)
        if not os.path.exists(fullpath):
            os.makedirs(fullpath)


class CommentMatcher:
    """Use anatomy and work file data to parse comments from filenames.

    Args:
        extensions (set[str]): Set of extensions.
        file_template (StringTemplate): Workfile file template.
        data (dict[str, Any]): Data to fill the template with.

    """
    def __init__(
        self,
        extensions: set[str],
        file_template: StringTemplate,
        data: dict[str, Any]
    ):
        self._fname_regex = None

        if "{comment}" not in file_template:
            # Don't look for comment if template doesn't allow it
            return

        # Create a regex group for extensions
        any_extension = "(?:{})".format(
            "|".join(re.escape(ext.lstrip(".")) for ext in extensions)
        )

        # Use placeholders that will never be in the filename
        temp_data = copy.deepcopy(data)
        temp_data["comment"] = "<<comment>>"
        temp_data["version"] = "<<version>>"
        temp_data["ext"] = "<<ext>>"

        fname_pattern = re.escape(
            file_template.format_strict(temp_data)
        )

        # Replace comment and version with something we can match with regex
        replacements = (
            ("<<comment>>", r"(?P<comment>.+)"),
            ("<<version>>", r"[0-9]+"),
            ("<<ext>>", any_extension),
        )
        for src, dest in replacements:
            fname_pattern = fname_pattern.replace(re.escape(src), dest)

        # Match from beginning to end of string to be safe
        self._fname_regex = re.compile(f"^{fname_pattern}$")

    def parse_comment(self, filename: str) -> Optional[str]:
        """Parse the {comment} part from a filename."""
        if self._fname_regex:
            match = self._fname_regex.match(filename)
            if match:
                return match.group("comment")
        return None


def get_comments_from_workfile_paths(
    filepaths: list[str],
    extensions: set[str],
    file_template: StringTemplate,
    template_data: dict[str, Any],
    current_filename: Optional[str] = None,
) -> tuple[list[str], str]:
    """Collect comments from workfile filenames.

    Based on 'current_filename' is also returned "current comment".

    Args:
        filepaths (list[str]): List of filepaths to parse.
        extensions (set[str]): Set of file extensions.
        file_template (StringTemplate): Workfile file template.
        template_data (dict[str, Any]): Data to fill the template with.
        current_filename (str): Filename to check for the current comment.

    Returns:
        tuple[list[str], str]: List of comments and the current comment.

    """
    current_comment = ""
    if not filepaths:
        return [], current_comment

    matcher = CommentMatcher(extensions, file_template, template_data)

    comment_hints = set()
    for filepath in filepaths:
        filename = os.path.basename(filepath)
        comment = matcher.parse_comment(filename)
        if comment:
            comment_hints.add(comment)
            if filename == current_filename:
                current_comment = comment

    return list(comment_hints), current_comment
