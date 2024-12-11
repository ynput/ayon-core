import os
import sys
import collections


class StdOEWrap:
    def __init__(self):
        self._origin_stdout_write = None
        self._origin_stderr_write = None
        self._listening = False
        self.lines = collections.deque()

        if not sys.stdout:
            sys.stdout = open(os.devnull, "w")

        if not sys.stderr:
            sys.stderr = open(os.devnull, "w")

        if self._origin_stdout_write is None:
            self._origin_stdout_write = sys.stdout.write

        if self._origin_stderr_write is None:
            self._origin_stderr_write = sys.stderr.write

        self._listening = True
        sys.stdout.write = self._stdout_listener
        sys.stderr.write = self._stderr_listener

    def stop_listen(self):
        self._listening = False

    def _stdout_listener(self, text):
        if self._listening:
            self.lines.append(text)
        if self._origin_stdout_write is not None:
            self._origin_stdout_write(text)

    def _stderr_listener(self, text):
        if self._listening:
            self.lines.append(text)
        if self._origin_stderr_write is not None:
            self._origin_stderr_write(text)
