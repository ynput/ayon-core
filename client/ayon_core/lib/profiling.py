# -*- coding: utf-8 -*-
"""Provide profiling decorator."""
import os
import cProfile
import functools


def do_profile(to_file=None):
    """Wraps function in profiler run and print stat after it is done.

    Args:
        to_file (str, optional): If specified, dumps stats into the file
        instead of printing.

    """
    if to_file:
        to_file = to_file.format(pid=os.getpid())

    def _do_profile(fn):
        @functools.wraps(fn)
        def profiled(*args, **kwargs):
            profiler = cProfile.Profile()
            try:
                profiler.enable()
                res = fn(*args, **kwargs)
                profiler.disable()
                return res
            finally:
                if to_file:
                    profiler.dump_stats(to_file)
                else:
                    profiler.print_stats()
        return profiled
    return _do_profile
