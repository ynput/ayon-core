from __future__ import annotations
import os
import re
import platform
import typing
import collections
from string import Formatter
from typing import Optional

if typing.TYPE_CHECKING:
    from typing import Union, Literal

    PlatformName = Literal["windows", "linux", "darwin"]
    EnvValue = Union[str, list[str], dict[str, str], dict[str, list[str]]]

Results = collections.namedtuple(
    "Results",
    ["sorted", "cyclic"]
)


class CycleError(ValueError):
    """Raised when a cycle is detected in dynamic env variables compute."""
    pass


class DynamicKeyClashError(Exception):
    """Raised when dynamic key clashes with an existing key."""
    pass


def env_value_to_bool(
    env_key: Optional[str] = None,
    value: Optional[str] = None,
    default: bool = False,
) -> bool:
    """Convert environment variable value to boolean.

    Function is based on value of the environemt variable. Value is lowered
    so function is not case sensitive.

    Returns:
        bool: If value match to one of ["true", "yes", "1"] result if True
            but if value match to ["false", "no", "0"] result is False else
            default value is returned.

    """
    if value is None and env_key is None:
        return default

    if value is None:
        value = os.environ.get(env_key)

    if value is not None:
        value = str(value).lower()
        if value in ("true", "yes", "1", "on"):
            return True
        elif value in ("false", "no", "0", "off"):
            return False
    return default


def get_paths_from_environ(
    env_key: Optional[str] = None,
    env_value: Optional[str] = None,
    return_first: bool = False,
) -> Optional[Union[str, list[str]]]:
    """Return existing paths from specific environment variable.

    Args:
        env_key (str): Environment key where should look for paths.
        env_value (str): Value of environment variable. Argument `env_key` is
            skipped if this argument is entered.
        return_first (bool): Return first found value or return list of found
            paths. `None` or empty list returned if nothing found.

    Returns:
        Optional[Union[str, list[str]]]: Result of found path/s.

    """
    existing_paths = []
    if not env_key and not env_value:
        if return_first:
            return None
        return existing_paths

    if env_value is None:
        env_value = os.environ.get(env_key) or ""

    path_items = env_value.split(os.pathsep)
    for path in path_items:
        # Skip empty string
        if not path:
            continue
        # Normalize path
        path = os.path.normpath(path)
        # Check if path exists
        if os.path.exists(path):
            # Return path if `return_first` is set to True
            if return_first:
                return path
            # Store path
            existing_paths.append(path)

    # Return None if none of paths exists
    if return_first:
        return None
    # Return all existing paths from environment variable
    return existing_paths


def parse_env_variables_structure(
    env: dict[str, EnvValue],
    platform_name: Optional[PlatformName] = None
) -> dict[str, str]:
    """Parse environment for platform-specific values and paths as lists.

    Args:
        env (dict): The source environment to read.
        platform_name (Optional[PlatformName]): Name of platform to parse for.
            Defaults to current platform.

    Returns:
        dict: The flattened environment for a platform.

    """
    platform_name = platform_name or platform.system().lower()

    result = {}
    for variable, value in env.items():
        # Platform specific values
        if isinstance(value, dict):
            value = value.get(platform_name)

        # Allow to have lists as values in the tool data
        if isinstance(value, (list, tuple)):
            value = os.pathsep.join(value)

        if not value:
            continue

        if not isinstance(value, str):
            raise TypeError(f"Expected 'str' got '{type(value)}'")

        result[variable] = value

    return result


def _topological_sort(dependency_pairs):
    """Sort values subject to dependency constraints"""
    num_heads = collections.defaultdict(int)  # num arrows pointing in
    tails = collections.defaultdict(list)  # list of arrows going out
    heads = []  # unique list of heads in order first seen
    for h, t in dependency_pairs:
        num_heads[t] += 1
        if h in tails:
            tails[h].append(t)
        else:
            tails[h] = [t]
            heads.append(h)

    ordered = [h for h in heads if h not in num_heads]
    for h in ordered:
        for t in tails[h]:
            num_heads[t] -= 1
            if not num_heads[t]:
                ordered.append(t)
    cyclic = [n for n, heads in num_heads.items() if heads]
    return Results(ordered, cyclic)


def _partial_format(
    s: str,
    data: dict[str, str],
    missing: Optional[str] = None,
) -> str:
    """Return string `s` formatted by `data` allowing a partial format

    Arguments:
        s (str): The string that will be formatted
        data (dict): The dictionary used to format with.

    Example:
        >>> _partial_format("{d} {a} {b} {c} {d}", {'b': "and", 'd': "left"})
        'left {a} and {c} left'
    """

    if missing is None:
        missing = "{{{key}}}"

    class FormatDict(dict):
        """This supports partial formatting.

        Missing keys are replaced with the return value of __missing__.

        """

        def __missing__(self, key):
            return missing.format(key=key)

    formatter = Formatter()
    mapping = FormatDict(**data)
    try:
        f = formatter.vformat(s, (), mapping)
    except Exception:
        r_token = re.compile(r"({.*?})")
        matches = re.findall(r_token, s)
        f = s
        for m in matches:
            try:
                f = re.sub(m, m.format(**data), f)
            except (KeyError, ValueError):
                continue
    return f


def compute_env_variables_structure(
    env: dict[str, str],
    fill_dynamic_keys: bool = True,
) -> dict[str, str]:
    """Compute the result from recursive dynamic environment.

    Note: Keys that are not present in the data will remain unformatted as the
        original keys. So they can be formatted against the current user
        environment when merging. So {"A": "{key}"} will remain {key} if not
        present in the dynamic environment.

    """
    env = env.copy()

    # Collect dependencies
    dependencies = []
    for key, value in env.items():
        try:
            dependent_keys = re.findall("{(.+?)}", value)
            for dependency in dependent_keys:
                # Ignore direct references to itself because
                # we don't format with itself anyway
                if dependency == key:
                    continue

                dependencies.append((key, dependency))
        except Exception:
            dependencies.append((key, value))

    result = _topological_sort(dependencies)

    # Check cycle
    if result.cyclic:
        raise CycleError(f"A cycle is detected on: {result.cyclic}")

    # Format dynamic values
    for key in reversed(result.sorted):
        if key in env:
            if not isinstance(env[key], str):
                continue
            data = env.copy()
            data.pop(key)    # format without itself
            env[key] = _partial_format(env[key], data=data)

    # Format cyclic values
    for key in result.cyclic:
        if key in env:
            if not isinstance(env[key], str):
                continue
            data = env.copy()
            data.pop(key)   # format without itself
            env[key] = _partial_format(env[key], data=data)

    # Format dynamic keys
    if fill_dynamic_keys:
        formatted = {}
        for key, value in env.items():
            if not isinstance(value, str):
                formatted[key] = value
                continue

            new_key = _partial_format(key, data=env)
            if new_key in formatted:
                raise DynamicKeyClashError(
                    f"Key clashes on: {new_key} (source: {key})"
                )

            formatted[new_key] = value
        env = formatted

    return env


def merge_env_variables(
    src_env: dict[str, str],
    dst_env: dict[str, str],
    missing: Optional[str] = None,
):
    """Merge the tools environment with the 'current_env'.

    This finalizes the join with a current environment by formatting the
    remainder of dynamic variables with that from the current environment.

    Remaining missing variables result in an empty value.

    Args:
        src_env (dict): The dynamic environment
        dst_env (dict): The target environment variables mapping to merge
            the dynamic environment into.
        missing (str): Argument passed to '_partial_format' during merging.
            `None` should keep missing keys unchanged.

    Returns:
        dict: The resulting environment after the merge.

    """
    result = dst_env.copy()
    for key, value in src_env.items():
        result[key] = _partial_format(
            str(value), data=dst_env, missing=missing
        )

    return result
