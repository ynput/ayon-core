import os
import sys
import collections


class _CustomSTD:
    def __init__(self, orig_std, write_callback):
        self.orig_std = orig_std
        self._valid_orig = bool(orig_std)
        self._write_callback = write_callback

    def __getattr__(self, attr):
        return getattr(self.orig_std, attr)

    def __setattr__(self, key, value):
        if key in ("orig_std", "_valid_orig", "_write_callback"):
            super().__setattr__(key, value)
        else:
            setattr(self.orig_std, key, value)

    def write(self, text):
        if self._valid_orig:
            self.orig_std.write(text)
        self._write_callback(text)


class StdOEWrap:
    def __init__(self):
        self.lines = collections.deque()
        self._listening = True

        self._stdout_wrap = _CustomSTD(sys.stdout, self._listener)
        self._stderr_wrap = _CustomSTD(sys.stderr, self._listener)

        sys.stdout = self._stdout_wrap
        sys.stderr = self._stderr_wrap

    def stop_listen(self):
        self._listening = False

    def _listener(self, text):
        if self._listening:
            self.lines.append(text)
