import os
import time
import collections

import ayon_api
import appdirs

from .cache import NestedCacheItem

FileInfo = collections.namedtuple(
    "FileInfo",
    ("path", "size", "modification_time")
)


class ThumbnailsCache:
    """Cache of thumbnails on local storage.

    Thumbnails are cached to appdirs to predefined directory. Each project has
    own subfolder with thumbnails -> that's because each project has own
    thumbnail id validation and file names are thumbnail ids with matching
    extension. Extensions are predefined (.png and .jpeg).

    Cache has cleanup mechanism which is triggered on initialized by default.

    The cleanup has 2 levels:
    1. soft cleanup which remove all files that are older then 'days_alive'
    2. max size cleanup which remove all files until the thumbnails folder
        contains less then 'max_filesize'
        - this is time consuming so it's not triggered automatically

    Args:
        cleanup (bool): Trigger soft cleanup (Cleanup expired thumbnails).
    """

    # Lifetime of thumbnails (in seconds)
    # - default 3 days
    days_alive = 3
    # Max size of thumbnail directory (in bytes)
    # - default 2 Gb
    max_filesize = 2 * 1024 * 1024 * 1024

    def __init__(self, cleanup=True):
        self._thumbnails_dir = None
        self._days_alive_secs = self.days_alive * 24 * 60 * 60
        if cleanup:
            self.cleanup()

    def get_thumbnails_dir(self):
        """Root directory where thumbnails are stored.

        Returns:
            str: Path to thumbnails root.
        """

        if self._thumbnails_dir is None:
            # TODO use generic function
            directory = appdirs.user_data_dir("AYON", "Ynput")
            self._thumbnails_dir = os.path.join(directory, "thumbnails")
        return self._thumbnails_dir

    thumbnails_dir = property(get_thumbnails_dir)

    def get_thumbnails_dir_file_info(self):
        """Get information about all files in thumbnails directory.

        Returns:
            List[FileInfo]: List of file information about all files.
        """

        thumbnails_dir = self.thumbnails_dir
        files_info = []
        if not os.path.exists(thumbnails_dir):
            return files_info

        for root, _, filenames in os.walk(thumbnails_dir):
            for filename in filenames:
                path = os.path.join(root, filename)
                files_info.append(FileInfo(
                    path, os.path.getsize(path), os.path.getmtime(path)
                ))
        return files_info

    def get_thumbnails_dir_size(self, files_info=None):
        """Got full size of thumbnail directory.

        Args:
            files_info (List[FileInfo]): Prepared file information about
                files in thumbnail directory.

        Returns:
            int: File size of all files in thumbnail directory.
        """

        if files_info is None:
            files_info = self.get_thumbnails_dir_file_info()

        if not files_info:
            return 0

        return sum(
            file_info.size
            for file_info in files_info
        )

    def cleanup(self, check_max_size=False):
        """Cleanup thumbnails directory.

        Args:
            check_max_size (bool): Also cleanup files to match max size of
                thumbnails directory.
        """

        thumbnails_dir = self.get_thumbnails_dir()
        # Skip if thumbnails dir does not exist yet
        if not os.path.exists(thumbnails_dir):
            return

        self._soft_cleanup(thumbnails_dir)
        if check_max_size:
            self._max_size_cleanup(thumbnails_dir)

    def _soft_cleanup(self, thumbnails_dir):
        current_time = time.time()
        for root, _, filenames in os.walk(thumbnails_dir):
            for filename in filenames:
                path = os.path.join(root, filename)
                modification_time = os.path.getmtime(path)
                if current_time - modification_time > self._days_alive_secs:
                    os.remove(path)

    def _max_size_cleanup(self, thumbnails_dir):
        files_info = self.get_thumbnails_dir_file_info()
        size = self.get_thumbnails_dir_size(files_info)
        if size < self.max_filesize:
            return

        sorted_file_info = collections.deque(
            sorted(files_info, key=lambda item: item.modification_time)
        )
        diff = size - self.max_filesize
        while diff > 0:
            if not sorted_file_info:
                break

            file_info = sorted_file_info.popleft()
            diff -= file_info.size
            os.remove(file_info.path)

    def get_thumbnail_filepath(self, project_name, thumbnail_id):
        """Get thumbnail by thumbnail id.

        Args:
            project_name (str): Name of project.
            thumbnail_id (str): Thumbnail id.

        Returns:
            Union[str, None]: Path to thumbnail image or None if thumbnail
                is not cached yet.
        """

        if not thumbnail_id:
            return None

        for ext in (
            ".png",
            ".jpeg",
        ):
            filepath = os.path.join(
                self.thumbnails_dir, project_name, thumbnail_id + ext
            )
            if os.path.exists(filepath):
                return filepath
        return None

    def get_project_dir(self, project_name):
        """Path to root directory for specific project.

        Args:
            project_name (str): Name of project for which root directory path
                should be returned.

        Returns:
            str: Path to root of project's thumbnails.
        """

        return os.path.join(self.thumbnails_dir, project_name)

    def make_sure_project_dir_exists(self, project_name):
        project_dir = self.get_project_dir(project_name)
        if not os.path.exists(project_dir):
            os.makedirs(project_dir)
        return project_dir

    def store_thumbnail(self, project_name, thumbnail_id, content, mime_type):
        """Store thumbnail to cache folder.

        Args:
            project_name (str): Project where the thumbnail belong to.
            thumbnail_id (str): Id of thumbnail.
            content (bytes): Byte content of thumbnail file.
            mime_data (str): Type of content.

        Returns:
            str: Path to cached thumbnail image file.
        """

        if mime_type == "image/png":
            ext = ".png"
        elif mime_type == "image/jpeg":
            ext = ".jpeg"
        else:
            raise ValueError(
                "Unknown mime type for thumbnail \"{}\"".format(mime_type))

        project_dir = self.make_sure_project_dir_exists(project_name)
        thumbnail_path = os.path.join(project_dir, thumbnail_id + ext)
        with open(thumbnail_path, "wb") as stream:
            stream.write(content)

        current_time = time.time()
        os.utime(thumbnail_path, (current_time, current_time))

        return thumbnail_path


class ThumbnailsModel:
    entity_cache_lifetime = 240  # In seconds

    def __init__(self):
        self._thumbnail_cache = ThumbnailsCache()
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime)
        self._versions_cache = NestedCacheItem(
            levels=2, lifetime=self.entity_cache_lifetime)

    def reset(self):
        self._paths_cache = collections.defaultdict(dict)
        self._folders_cache.reset()
        self._versions_cache.reset()

    def get_thumbnail_path(self, project_name, thumbnail_id):
        return self._get_thumbnail_path(project_name, thumbnail_id)

    def get_folder_thumbnail_ids(self, project_name, folder_ids):
        project_cache = self._folders_cache[project_name]
        output = {}
        missing_cache = set()
        for folder_id in folder_ids:
            cache = project_cache[folder_id]
            if cache.is_valid:
                output[folder_id] = cache.get_data()
            else:
                missing_cache.add(folder_id)
        self._query_folder_thumbnail_ids(project_name, missing_cache)
        for folder_id in missing_cache:
            cache = project_cache[folder_id]
            output[folder_id] = cache.get_data()
        return output

    def get_version_thumbnail_ids(self, project_name, version_ids):
        project_cache = self._versions_cache[project_name]
        output = {}
        missing_cache = set()
        for version_id in version_ids:
            cache = project_cache[version_id]
            if cache.is_valid:
                output[version_id] = cache.get_data()
            else:
                missing_cache.add(version_id)
        self._query_version_thumbnail_ids(project_name, missing_cache)
        for version_id in missing_cache:
            cache = project_cache[version_id]
            output[version_id] = cache.get_data()
        return output

    def _get_thumbnail_path(self, project_name, thumbnail_id):
        if not thumbnail_id:
            return None

        project_cache = self._paths_cache[project_name]
        if thumbnail_id in project_cache:
            return project_cache[thumbnail_id]

        filepath = self._thumbnail_cache.get_thumbnail_filepath(
            project_name, thumbnail_id
        )
        if filepath is not None:
            project_cache[thumbnail_id] = filepath
            return filepath

        # 'ayon_api' had a bug, public function
        #   'get_thumbnail_by_id' did not return output of
        #   'ServerAPI' method.
        con = ayon_api.get_server_api_connection()
        result = con.get_thumbnail_by_id(project_name, thumbnail_id)
        if result is None:
            pass

        elif result.is_valid:
            filepath = self._thumbnail_cache.store_thumbnail(
                project_name,
                thumbnail_id,
                result.content,
                result.content_type
            )
        project_cache[thumbnail_id] = filepath
        return filepath

    def _query_folder_thumbnail_ids(self, project_name, folder_ids):
        if not project_name or not folder_ids:
            return

        folders = ayon_api.get_folders(
            project_name,
            folder_ids=folder_ids,
            fields=["id", "thumbnailId"]
        )
        project_cache = self._folders_cache[project_name]
        for folder in folders:
            project_cache[folder["id"]] = folder["thumbnailId"]

    def _query_version_thumbnail_ids(self, project_name, version_ids):
        if not project_name or not version_ids:
            return

        versions = ayon_api.get_versions(
            project_name,
            version_ids=version_ids,
            fields=["id", "thumbnailId"]
        )
        project_cache = self._versions_cache[project_name]
        for version in versions:
            project_cache[version["id"]] = version["thumbnailId"]
