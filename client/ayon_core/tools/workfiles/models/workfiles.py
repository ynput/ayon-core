import os
import re
import copy
import uuid

import arrow
import ayon_api
from ayon_api.operations import OperationsSession

from ayon_core.lib import get_ayon_username
from ayon_core.pipeline.template_data import (
    get_template_data,
    get_task_template_data,
    get_folder_template_data,
)
from ayon_core.pipeline.workfile import (
    get_workdir_with_workdir_data,
    get_workfile_template_key,
    get_last_workfile_with_version,
)
from ayon_core.pipeline.version_start import get_versioning_start
from ayon_core.tools.workfiles.abstract import (
    WorkareaFilepathResult,
    FileItem,
    WorkfileInfo,
)

_NOT_SET = object()


class CommentMatcher(object):
    """Use anatomy and work file data to parse comments from filenames.

    Args:
        extensions (set[str]): Set of extensions.
        file_template (AnatomyStringTemplate): File template.
        data (dict[str, Any]): Data to fill the template with.

    """
    def __init__(self, extensions, file_template, data):
        self.fname_regex = None

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

        fname_pattern = file_template.format_strict(temp_data)
        fname_pattern = re.escape(fname_pattern)

        # Replace comment and version with something we can match with regex
        replacements = {
            "<<comment>>": "(.+)",
            "<<version>>": "[0-9]+",
            "<<ext>>": any_extension,
        }
        for src, dest in replacements.items():
            fname_pattern = fname_pattern.replace(re.escape(src), dest)

        # Match from beginning to end of string to be safe
        fname_pattern = "^{}$".format(fname_pattern)

        self.fname_regex = re.compile(fname_pattern)

    def parse_comment(self, filepath):
        """Parse the {comment} part from a filename"""
        if not self.fname_regex:
            return

        fname = os.path.basename(filepath)
        match = self.fname_regex.match(fname)
        if match:
            return match.group(1)


class WorkareaModel:
    """Workfiles model looking for workfiles in workare folder.

    Workarea folder is usually task and host specific, defined by
    anatomy templates. Is looking for files with extensions defined
    by host integration.
    """

    def __init__(self, controller):
        self._controller = controller
        extensions = None
        if controller.is_host_valid():
            extensions = controller.get_workfile_extensions()
        self._extensions = extensions
        self._base_data = None
        self._fill_data_by_folder_id = {}
        self._task_data_by_folder_id = {}
        self._workdir_by_context = {}

    @property
    def project_name(self):
        return self._controller.get_current_project_name()

    def reset(self):
        self._base_data = None
        self._fill_data_by_folder_id = {}
        self._task_data_by_folder_id = {}

    def _get_base_data(self):
        if self._base_data is None:
            base_data = get_template_data(
                ayon_api.get_project(self.project_name)
            )
            base_data["app"] = self._controller.get_host_name()
            self._base_data = base_data
        return copy.deepcopy(self._base_data)

    def _get_folder_data(self, folder_id):
        fill_data = self._fill_data_by_folder_id.get(folder_id)
        if fill_data is None:
            folder = self._controller.get_folder_entity(
                self.project_name, folder_id
            )
            fill_data = get_folder_template_data(folder, self.project_name)
            self._fill_data_by_folder_id[folder_id] = fill_data
        return copy.deepcopy(fill_data)

    def _get_task_data(self, project_entity, folder_id, task_id):
        task_data = self._task_data_by_folder_id.setdefault(folder_id, {})
        if task_id not in task_data:
            task = self._controller.get_task_entity(
                self.project_name, task_id
            )
            if task:
                task_data[task_id] = get_task_template_data(
                    project_entity, task)
        return copy.deepcopy(task_data[task_id])

    def _prepare_fill_data(self, folder_id, task_id):
        if not folder_id or not task_id:
            return {}

        base_data = self._get_base_data()
        project_name = base_data["project"]["name"]
        folder_data = self._get_folder_data(folder_id)
        project_entity = self._controller.get_project_entity(project_name)
        task_data = self._get_task_data(project_entity, folder_id, task_id)

        base_data.update(folder_data)
        base_data.update(task_data)

        return base_data

    def get_workarea_dir_by_context(self, folder_id, task_id):
        if not folder_id or not task_id:
            return None
        folder_mapping = self._workdir_by_context.setdefault(folder_id, {})
        workdir = folder_mapping.get(task_id)
        if workdir is not None:
            return workdir

        workdir_data = self._prepare_fill_data(folder_id, task_id)

        workdir = get_workdir_with_workdir_data(
            workdir_data,
            self.project_name,
            anatomy=self._controller.project_anatomy,
        )
        folder_mapping[task_id] = workdir
        return workdir

    def get_file_items(self, folder_id, task_id, task_name):
        items = []
        if not folder_id or not task_id:
            return items

        workdir = self.get_workarea_dir_by_context(folder_id, task_id)
        if not os.path.exists(workdir):
            return items

        for filename in os.listdir(workdir):
            # We want to support both files and folders. e.g. Silhoutte uses
            # folders as its project files. So we do not check whether it is
            # a file or not.
            filepath = os.path.join(workdir, filename)

            ext = os.path.splitext(filename)[1].lower()
            if ext not in self._extensions:
                continue

            workfile_info = self._controller.get_workfile_info(
                folder_id, task_name, filepath
            )
            modified = os.path.getmtime(filepath)
            items.append(FileItem(
                workdir,
                filename,
                modified,
                workfile_info.created_by,
                workfile_info.updated_by,
            ))
        return items

    def _get_template_key(self, fill_data):
        task_type = fill_data.get("task", {}).get("type")
        # TODO cache
        return get_workfile_template_key(
            self.project_name,
            task_type,
            self._controller.get_host_name(),
        )

    def _get_last_workfile_version(
        self, workdir, file_template, fill_data, extensions
    ):
        """

        Todos:
            Validate if logic of this function is correct. It does return
                last version + 1 which might be wrong.

        Args:
            workdir (str): Workdir path.
            file_template (str): File template.
            fill_data (dict[str, Any]): Fill data.
            extensions (set[str]): Extensions.

        Returns:
            int: Next workfile version.

        """
        version = get_last_workfile_with_version(
            workdir, file_template, fill_data, extensions
        )[1]

        if version is None:
            task_info = fill_data.get("task", {})
            version = get_versioning_start(
                self.project_name,
                self._controller.get_host_name(),
                task_name=task_info.get("name"),
                task_type=task_info.get("type"),
                product_type="workfile",
                project_settings=self._controller.project_settings,
            )
        else:
            version += 1
        return version

    def _get_comments_from_root(
        self,
        file_template,
        extensions,
        fill_data,
        root,
        current_filename,
    ):
        """Get comments from root directory.

        Args:
            file_template (AnatomyStringTemplate): File template.
            extensions (set[str]): Extensions.
            fill_data (dict[str, Any]): Fill data.
            root (str): Root directory.
            current_filename (str): Current filename.

        Returns:
            Tuple[list[str], Union[str, None]]: Comment hints and current
                comment.

        """
        current_comment = None
        filenames = []
        if root and os.path.exists(root):
            for filename in os.listdir(root):
                path = os.path.join(root, filename)
                if not os.path.isfile(path):
                    continue

                ext = os.path.splitext(filename)[-1].lower()
                if ext in extensions:
                    filenames.append(filename)

        if not filenames:
            return [], current_comment

        matcher = CommentMatcher(extensions, file_template, fill_data)

        comment_hints = set()
        for filename in filenames:
            comment = matcher.parse_comment(filename)
            if comment:
                comment_hints.add(comment)
                if filename == current_filename:
                    current_comment = comment

        return list(comment_hints), current_comment

    def _get_workdir(self, anatomy, template_key, fill_data):
        directory_template = anatomy.get_template_item(
            "work", template_key, "directory"
        )
        return directory_template.format_strict(fill_data).normalized()

    def get_workarea_save_as_data(self, folder_id, task_id):
        folder_entity = None
        task_entity = None
        if folder_id:
            folder_entity = self._controller.get_folder_entity(
                self.project_name, folder_id
            )
            if folder_entity and task_id:
                task_entity = self._controller.get_task_entity(
                    self.project_name, task_id
                )

        if not folder_entity or not task_entity:
            return {
                "template_key": None,
                "template_has_version": None,
                "template_has_comment": None,
                "ext": None,
                "workdir": None,
                "comment": None,
                "comment_hints": None,
                "last_version": None,
                "extensions": None,
            }

        anatomy = self._controller.project_anatomy
        fill_data = self._prepare_fill_data(folder_id, task_id)
        template_key = self._get_template_key(fill_data)

        current_workfile = self._controller.get_current_workfile()
        current_filename = None
        current_ext = None
        if current_workfile:
            current_filename = os.path.basename(current_workfile)
            current_ext = os.path.splitext(current_filename)[1].lower()

        extensions = self._extensions
        if not current_ext and extensions:
            current_ext = tuple(extensions)[0]

        workdir = self._get_workdir(anatomy, template_key, fill_data)

        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        )
        file_template_str = file_template.template

        template_has_version = "{version" in file_template_str
        template_has_comment = "{comment" in file_template_str

        comment_hints, comment = self._get_comments_from_root(
            file_template,
            extensions,
            fill_data,
            workdir,
            current_filename,
        )
        last_version = self._get_last_workfile_version(
            workdir, file_template_str, fill_data, extensions
        )

        return {
            "template_key": template_key,
            "template_has_version": template_has_version,
            "template_has_comment": template_has_comment,
            "ext": current_ext,
            "workdir": workdir,
            "comment": comment,
            "comment_hints": comment_hints,
            "last_version": last_version,
            "extensions": extensions,
        }

    def fill_workarea_filepath(
        self,
        folder_id,
        task_id,
        extension,
        use_last_version,
        version,
        comment,
    ):
        """Fill workarea filepath based on context.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.
            extension (str): File extension.
            use_last_version (bool): Use last version.
            version (int): Version number.
            comment (str): Comment.

        Returns:
            WorkareaFilepathResult: Workarea filepath result.

        """
        anatomy = self._controller.project_anatomy
        fill_data = self._prepare_fill_data(folder_id, task_id)

        template_key = self._get_template_key(fill_data)

        workdir = self._get_workdir(anatomy, template_key, fill_data)

        file_template = anatomy.get_template_item(
            "work", template_key, "file"
        )

        if use_last_version:
            version = self._get_last_workfile_version(
                workdir, file_template.template, fill_data, self._extensions
            )
        fill_data["version"] = version
        fill_data["ext"] = extension.lstrip(".")

        if comment:
            fill_data["comment"] = comment

        filename = file_template.format(fill_data)
        if not filename.solved:
            filename = None

        exists = False
        if filename:
            filepath = os.path.join(workdir, filename)
            exists = os.path.exists(filepath)

        return WorkareaFilepathResult(
            workdir,
            filename,
            exists
        )


class WorkfileEntitiesModel:
    """Workfile entities model.

    Args:
        control (AbstractWorkfileController): Controller object.
    """

    def __init__(self, controller):
        self._controller = controller
        self._cache = {}
        self._items = {}
        self._current_username = _NOT_SET

    def _get_workfile_info_identifier(
        self, folder_id, task_id, rootless_path
    ):
        return "_".join([folder_id, task_id, rootless_path])

    def _get_rootless_path(self, filepath):
        anatomy = self._controller.project_anatomy

        workdir, filename = os.path.split(filepath)
        success, rootless_dir = anatomy.find_root_template_from_path(workdir)
        return "/".join([
            os.path.normpath(rootless_dir).replace("\\", "/"),
            filename
        ])

    def _prepare_workfile_info_item(
        self, folder_id, task_id, workfile_info, filepath
    ):
        note = ""
        created_by = None
        updated_by = None
        if workfile_info:
            note = workfile_info["attrib"].get("description") or ""
            created_by = workfile_info.get("createdBy")
            updated_by = workfile_info.get("updatedBy")

        filestat = os.stat(filepath)
        return WorkfileInfo(
            folder_id,
            task_id,
            filepath,
            filesize=filestat.st_size,
            creation_time=filestat.st_ctime,
            modification_time=filestat.st_mtime,
            created_by=created_by,
            updated_by=updated_by,
            note=note
        )

    def _get_workfile_info(self, folder_id, task_id, identifier):
        workfile_info = self._cache.get(identifier)
        if workfile_info is not None:
            return workfile_info

        for workfile_info in ayon_api.get_workfiles_info(
            self._controller.get_current_project_name(),
            task_ids=[task_id],
            fields=["id", "path", "attrib", "createdBy", "updatedBy"],
        ):
            workfile_identifier = self._get_workfile_info_identifier(
                folder_id, task_id, workfile_info["path"]
            )
            self._cache[workfile_identifier] = workfile_info
        return self._cache.get(identifier)

    def get_workfile_info(
        self, folder_id, task_id, filepath, rootless_path=None
    ):
        if not folder_id or not task_id or not filepath:
            return None

        if rootless_path is None:
            rootless_path = self._get_rootless_path(filepath)

        identifier = self._get_workfile_info_identifier(
            folder_id, task_id, rootless_path)
        item = self._items.get(identifier)
        if item is None:
            workfile_info = self._get_workfile_info(
                folder_id, task_id, identifier
            )
            item = self._prepare_workfile_info_item(
                folder_id, task_id, workfile_info, filepath
            )
            self._items[identifier] = item
        return item

    def save_workfile_info(self, folder_id, task_id, filepath, note):
        rootless_path = self._get_rootless_path(filepath)
        identifier = self._get_workfile_info_identifier(
            folder_id, task_id, rootless_path
        )
        workfile_info = self._get_workfile_info(
            folder_id, task_id, identifier
        )
        if not workfile_info:
            self._cache[identifier] = self._create_workfile_info_entity(
                task_id, rootless_path, note or "")
            self._items.pop(identifier, None)
            return

        old_note = workfile_info.get("attrib", {}).get("note")

        new_workfile_info = copy.deepcopy(workfile_info)
        update_data = {}
        if note is not None and old_note != note:
            update_data["attrib"] = {"description": note}
            attrib = new_workfile_info.setdefault("attrib", {})
            attrib["description"] = note

        username = self._get_current_username()
        # Automatically fix 'createdBy' and 'updatedBy' fields
        # NOTE both fields were not automatically filled by server
        #   until 1.1.3 release.
        if workfile_info.get("createdBy") is None:
            update_data["createdBy"] = username
            new_workfile_info["createdBy"] = username

        if workfile_info.get("updatedBy") != username:
            update_data["updatedBy"] = username
            new_workfile_info["updatedBy"] = username

        if not update_data:
            return

        self._cache[identifier] = new_workfile_info
        self._items.pop(identifier, None)

        project_name = self._controller.get_current_project_name()

        session = OperationsSession()
        session.update_entity(
            project_name,
            "workfile",
            workfile_info["id"],
            update_data,
        )
        session.commit()

    def _create_workfile_info_entity(self, task_id, rootless_path, note):
        extension = os.path.splitext(rootless_path)[1]

        project_name = self._controller.get_current_project_name()

        username = self._get_current_username()
        workfile_info = {
            "id": uuid.uuid4().hex,
            "path": rootless_path,
            "taskId": task_id,
            "attrib": {
                "extension": extension,
                "description": note
            },
            # TODO remove 'createdBy' and 'updatedBy' fields when server is
            #   or above 1.1.3 .
            "createdBy": username,
            "updatedBy": username,
        }

        session = OperationsSession()
        session.create_entity(project_name, "workfile", workfile_info)
        session.commit()
        return workfile_info

    def _get_current_username(self):
        if self._current_username is _NOT_SET:
            self._current_username = get_ayon_username()
        return self._current_username


class PublishWorkfilesModel:
    """Model for handling of published workfiles.

    Todos:
        Cache workfiles products and representations for some time.
            Note Representations won't change. Only what can change are
                versions.
    """

    def __init__(self, controller):
        self._controller = controller
        self._cached_extensions = None
        self._cached_repre_extensions = None

    @property
    def _extensions(self):
        if self._cached_extensions is None:
            exts = self._controller.get_workfile_extensions() or []
            self._cached_extensions = exts
        return self._cached_extensions

    @property
    def _repre_extensions(self):
        if self._cached_repre_extensions is None:
            self._cached_repre_extensions = {
                ext.lstrip(".") for ext in self._extensions
            }
        return self._cached_repre_extensions

    def _file_item_from_representation(
        self, repre_entity, project_anatomy, author, task_name=None
    ):
        if task_name is not None:
            task_info = repre_entity["context"].get("task")
            if not task_info or task_info["name"] != task_name:
                return None

        # Filter by extension
        extensions = self._repre_extensions
        workfile_path = None
        for repre_file in repre_entity["files"]:
            ext = (
                os.path.splitext(repre_file["name"])[1]
                .lower()
                .lstrip(".")
            )
            if ext in extensions:
                workfile_path = repre_file["path"]
                break

        if not workfile_path:
            return None

        try:
            workfile_path = workfile_path.format(
                root=project_anatomy.roots)
        except Exception as exc:
            print("Failed to format workfile path: {}".format(exc))

        dirpath, filename = os.path.split(workfile_path)
        created_at = arrow.get(repre_entity["createdAt"]).to("local")
        return FileItem(
            dirpath,
            filename,
            created_at.float_timestamp,
            author,
            None,
            repre_entity["id"]
        )

    def get_file_items(self, folder_id, task_name):
        # TODO refactor to use less server API calls
        project_name = self._controller.get_current_project_name()
        # Get subset docs of folder
        product_entities = ayon_api.get_products(
            project_name,
            folder_ids={folder_id},
            product_types={"workfile"},
            fields={"id", "name"}
        )

        output = []
        product_ids = {product["id"] for product in product_entities}
        if not product_ids:
            return output

        # Get version docs of products with their families
        version_entities = ayon_api.get_versions(
            project_name,
            product_ids=product_ids,
            fields={"id", "author"}
        )
        versions_by_id = {
            version["id"]: version
            for version in version_entities
        }
        if not versions_by_id:
            return output

        # Query representations of filtered versions and add filter for
        #   extension
        repre_entities = ayon_api.get_representations(
            project_name,
            version_ids=set(versions_by_id)
        )
        project_anatomy = self._controller.project_anatomy

        # Filter queried representations by task name if task is set
        file_items = []
        for repre_entity in repre_entities:
            version_id = repre_entity["versionId"]
            version_entity = versions_by_id[version_id]
            file_item = self._file_item_from_representation(
                repre_entity,
                project_anatomy,
                version_entity["author"],
                task_name,
            )
            if file_item is not None:
                file_items.append(file_item)

        return file_items


class WorkfilesModel:
    """Workfiles model."""

    def __init__(self, controller):
        self._controller = controller

        self._entities_model = WorkfileEntitiesModel(controller)
        self._workarea_model = WorkareaModel(controller)
        self._published_model = PublishWorkfilesModel(controller)

    def get_workfile_info(self, folder_id, task_id, filepath):
        return self._entities_model.get_workfile_info(
            folder_id, task_id, filepath
        )

    def save_workfile_info(self, folder_id, task_id, filepath, note):
        self._entities_model.save_workfile_info(
            folder_id, task_id, filepath, note
        )

    def get_workarea_dir_by_context(self, folder_id, task_id):
        """Workarea dir for passed context.

        The directory path is based on project anatomy templates.

        Args:
            folder_id (str): Folder id.
            task_id (str): Task id.

        Returns:
            Union[str, None]: Workarea dir path or None for invalid context.
        """

        return self._workarea_model.get_workarea_dir_by_context(
            folder_id, task_id)

    def get_workarea_file_items(self, folder_id, task_id, task_name):
        """Workfile items for passed context from workarea.

        Args:
            folder_id (Union[str, None]): Folder id.
            task_id (Union[str, None]): Task id.
            task_name (Union[str, None]): Task name.

        Returns:
            list[FileItem]: List of file items matching workarea of passed
                context.
        """
        return self._workarea_model.get_file_items(
            folder_id, task_id, task_name
        )

    def get_workarea_save_as_data(self, folder_id, task_id):
        return self._workarea_model.get_workarea_save_as_data(
            folder_id, task_id)

    def fill_workarea_filepath(self, *args, **kwargs):
        return self._workarea_model.fill_workarea_filepath(
            *args, **kwargs
        )

    def get_published_file_items(self, folder_id, task_name):
        """Published workfiles for passed context.

        Args:
            folder_id (str): Folder id.
            task_name (str): Task name.

        Returns:
            list[FileItem]: List of files for published workfiles.
        """

        return self._published_model.get_file_items(folder_id, task_name)
