# -*- coding: utf-8 -*-
"""Provide profiling decorator."""
import os
import cProfile
import functools


def do_profile(to_file=None, tool_name=None):
    """Wraps function in profiler run and print stat after it is done.

    Args:
        to_file (str, optional): If specified, dumps stats into the file
            instead of printing.
        tool_name (str, optional): A given name to your function. It will
            be checked against the 'ENABLE_PROFILING' environment variable.
            If None, the filtering is skipped and the function is
            always profiled.
    """
    if to_file:
        to_file = to_file.format(pid=os.getpid())

    def _do_profile(fn):
        env_val = os.getenv("AYON_ENABLE_PROFILING", "ALL").strip()
        if (
            tool_name and
            env_val != "ALL" and
            tool_name != env_val
        ):
            return fn

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
