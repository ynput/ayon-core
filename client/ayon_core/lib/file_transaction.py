import concurrent.futures
import os
import logging
import errno
from concurrent.futures import ThreadPoolExecutor, Future
from typing import List, Optional

from ayon_core.lib import create_hard_link

from speedcopy import copyfile


class DuplicateDestinationError(ValueError):
    """Error raised when transfer destination already exists in queue.

    The error is only raised if `allow_queue_replacements` is False on the
    FileTransaction instance and the added file to transfer is of a different
    src file than the one already detected in the queue.

    """


class FileTransaction:
    """File transaction with rollback options.

    The file transaction is a three-step process.

    1) Rename any existing files to a "temporary backup" during `process()`
    2) Copy the files to final destination during `process()`
    3) Remove any backed up files (*no rollback possible!) during `finalize()`

    Step 3 is done during `finalize()`. If not called the .bak files will
    remain on disk.

    These steps try to ensure that we don't overwrite half of any existing
    files e.g. if they are currently in use.

    Note:
        A regular filesystem is *not* a transactional file system and even
        though this implementation tries to produce a 'safe copy' with a
        potential rollback do keep in mind that it's inherently unsafe due
        to how filesystem works and a myriad of things could happen during
        the transaction that break the logic. A file storage could go down,
        permissions could be changed, other machines could be moving or writing
        files. A lot can happen.

    Warning:
        Any folders created during the transfer will not be removed.
    """

    MODE_COPY = 0
    MODE_HARDLINK = 1

    def __init__(self, log=None, allow_queue_replacements=False):
        if log is None:
            log = logging.getLogger("FileTransaction")

        self.log = log

        # The transfer queue
        # todo: make this an actual FIFO queue?
        self._transfers = {}

        # Destination file paths that a file was transferred to
        self._transferred = []

        # Backup file location mapping to original locations
        self._backup_to_original = {}

        self._allow_queue_replacements = allow_queue_replacements

    def add(self, src, dst, mode=MODE_COPY):
        """Add a new file to transfer queue.

        Args:
            src (str): Source path.
            dst (str): Destination path.
            mode (MODE_COPY, MODE_HARDLINK): Transfer mode.
        """

        opts = {"mode": mode}

        src = os.path.normpath(os.path.abspath(src))
        dst = os.path.normpath(os.path.abspath(dst))

        if dst in self._transfers:
            queued_src = self._transfers[dst][0]
            if src == queued_src:
                self.log.debug(
                    "File transfer was already in queue: {} -> {}".format(
                        src, dst))
                return
            else:
                if not self._allow_queue_replacements:
                    raise DuplicateDestinationError(
                        "Transfer to destination is already in queue: "
                        "{} -> {}. It's not allowed to be replaced by "
                        "a new transfer from {}".format(
                            queued_src, dst, src
                        ))

                self.log.warning("File transfer in queue replaced..")
                self.log.debug(
                    "Removed from queue: {} -> {} replaced by {} -> {}".format(
                        queued_src, dst, src, dst))

        self._transfers[dst] = (src, opts)

    def process(self):
        with ThreadPoolExecutor(max_workers=8) as executor:
            # Submit backup tasks
            backup_futures = [
                executor.submit(self._backup_file, dst, src)
                for dst, (src, _) in self._transfers.items()
            ]
            wait_for_future_errors(
                executor, backup_futures, logger=self.log)

            # Submit transfer tasks
            transfer_futures = [
                executor.submit(self._transfer_file, dst, src, opts)
                for dst, (src, opts) in self._transfers.items()
            ]
            wait_for_future_errors(
                executor, transfer_futures, logger=self.log)

    def _backup_file(self, dst, src):
        self.log.debug(f"Checking file ... {src} -> {dst}")
        path_same = self._same_paths(src, dst)
        if path_same or not os.path.exists(dst):
            return

        # Backup original file
        backup = dst + ".bak"
        self._backup_to_original[backup] = dst
        self.log.debug(f"Backup existing file: {dst} -> {backup}")
        os.rename(dst, backup)

    def _transfer_file(self, dst, src, opts):
        path_same = self._same_paths(src, dst)
        if path_same:
            self.log.debug(
                f"Source and destination are same files {src} -> {dst}")
            return

        self._create_folder_for_file(dst)

        if opts["mode"] == self.MODE_COPY:
            self.log.debug(f"Copying file ... {src} -> {dst}")
            copyfile(src, dst)
        elif opts["mode"] == self.MODE_HARDLINK:
            self.log.debug(f"Hardlinking file ... {src} -> {dst}")
            create_hard_link(src, dst)

        self._transferred.append(dst)

    def finalize(self):
        # Delete any backed up files
        for backup in self._backup_to_original.keys():
            try:
                os.remove(backup)
            except OSError:
                self.log.error(
                    "Failed to remove backup file: {}".format(backup),
                    exc_info=True)

    def rollback(self):
        errors = 0
        last_exc = None
        # Rollback any transferred files
        for path in self._transferred:
            try:
                os.remove(path)
            except OSError as exc:
                last_exc = exc
                errors += 1
                self.log.error(
                    "Failed to rollback created file: {}".format(path),
                    exc_info=True)

        # Rollback the backups
        for backup, original in self._backup_to_original.items():
            try:
                os.rename(backup, original)
            except OSError as exc:
                last_exc = exc
                errors += 1
                self.log.error(
                    "Failed to restore original file: {} -> {}".format(
                        backup, original),
                    exc_info=True)

        if errors:
            self.log.error(
                "{} errors occurred during rollback.".format(errors),
                exc_info=True)
            raise last_exc

    @property
    def transferred(self):
        """Return the processed transfers destination paths"""
        return list(self._transferred)

    @property
    def backups(self):
        """Return the backup file paths"""
        return list(self._backup_to_original.keys())

    def _create_folder_for_file(self, path):
        dirname = os.path.dirname(path)
        try:
            os.makedirs(dirname)
        except OSError as e:
            if e.errno != errno.EEXIST:
                self.log.critical("An unexpected error occurred.")
                raise e

    def _same_paths(self, src, dst):
        # handles same paths but with C:/project vs c:/project
        if os.path.exists(src) and os.path.exists(dst):
            return os.stat(src) == os.stat(dst)

        return src == dst


def wait_for_future_errors(
        executor: ThreadPoolExecutor,
        futures: List[Future],
        logger: Optional[logging.Logger] = None):
    """For the ThreadPoolExecutor shutdown and cancel futures as soon one of
    the workers raises an error as they complete.

    The ThreadPoolExecutor only cancels pending futures on exception but will
    still complete those that are running - each which also themselves could
    fail. We log all exceptions but re-raise the last exception only.
    """
    if logger is None:
        logger = logging.getLogger(__name__)

    for future in concurrent.futures.as_completed(futures):
        exception = future.exception()
        if exception:
            # As soon as an error occurs, stop executing more futures.
            # Running workers, however, will still be complete, so we also want
            # to log those errors if any occurred on them.
            executor.shutdown(wait=True, cancel_futures=True)
            break
    else:
        # Futures are completed, no exceptions occurred
        return

    # An exception occurred in at least one future. Get exceptions from
    # all futures that are done and ended up failing until that point.
    exceptions = []
    for future in futures:
        if not future.cancelled() and future.done():
            exception = future.exception()
            if exception:
                exceptions.append(exception)

    # Log any exceptions that occurred in all workers
    for exception in exceptions:
        logger.error("Error occurred in worker", exc_info=exception)

    # Raise the last exception
    raise exceptions[-1]
