# -*- coding: utf-8 -*-
"""Provide profiling decorator."""
import os
import cProfile
import functools


def do_profile(fn=None, *, to_file=None):
    """Wraps function in profiler run and print stat after it is done.

    Can be used as `@do_profile`, `@do_profile()` or
    `@do_profile(to_file="profile_{pid}.prof")`.

    Args:
        fn (Optional[Callable]): Function to profile. Passed implicitly
            when used as `@do_profile` without parentheses.
        to_file (Optional[str]): If specified, dumps stats into the file
            instead of printing. Can contain `{pid}` placeholder.

    """
    if fn is not None and not callable(fn):
        raise TypeError(
            f"do_profile expects a callable, got {fn!r}."
            " Pass the output path as 'to_file' keyword."
        )

    if to_file:
        to_file = to_file.format(pid=os.getpid())

    def _do_profile(func):
        @functools.wraps(func)
        def profiled(*args, **kwargs):
            profiler = cProfile.Profile()
            profiler.enable()
            try:
                return func(*args, **kwargs)
            finally:
                profiler.disable()
                if to_file:
                    profiler.dump_stats(to_file)
                else:
                    profiler.print_stats()
        return profiled

    if fn is not None:
        return _do_profile(fn)
    return _do_profile
