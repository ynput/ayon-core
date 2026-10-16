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

    # If used as @do_profile, to_file is the function
    if callable(to_file):
        fn = to_file
        to_file = None
        return _do_profile(fn)

    if to_file:
        to_file = to_file.format(pid=os.getpid())

    return _do_profile
