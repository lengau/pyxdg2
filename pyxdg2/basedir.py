"""XDG Base Directories.

Based on base directory spec version 0.8.
https://specifications.freedesktop.org/basedir-spec/basedir-spec-0.8.html
"""
import functools
import os
import pathlib
import stat
from typing import Iterable, Optional, Union

CreateMode = Union[bool, int]
_MODE_700 = stat.S_IRUSR | stat.S_IWUSR | stat.S_IXUSR


def get_path(
    environment_variable: Optional[str],
    fallback_path: Optional[pathlib.Path] = None,
) -> pathlib.Path:
    """Get a single path based on the value of an environment variable or fallback.

    :param environment_variable: The name of the environment variable to check
    :param fallback_path: An optional Path object to fall back to
    :raises ``KeyError`` if no ``fallback_path`` is specified and the environment
        variable is either empty or doesn't exist
    :returns A ``pathlib.Path`` object pointing to the relevant path.
    """
    env_path = os.environ.get(environment_variable) if environment_variable else None
    path = pathlib.Path(env_path) if env_path else fallback_path
    if not path:
        raise KeyError(
            f"Neither {environment_variable} nor the fallback path are valid"
        )
    return path


def gen_paths(
    environment_variable: str, fallback: Optional[str] = None
) -> Iterable[pathlib.Path]:
    """Generate paths from a colon-separated environment variable.

    :param environment_variable: The name of the variable to check
    :yields a series of Paths from this environment variable.
    :param fallback: A string to use as the fallback value.

    Check get_path for more behaviour detail, as this uses that function.
    """
    path_spec = os.environ.get(environment_variable) or fallback
    if not path_spec:
        raise KeyError(
            f"Neither {environment_variable} nor the fallback paths are valid"
        )
    paths = (pathlib.Path(p) for p in path_spec.split(":"))
    yield from (get_path(None, path) for path in paths)


# region Constants of the appropriate directories
HOME = pathlib.Path.home()
XDG_DATA_HOME = get_path("XDG_DATA_HOME", HOME / ".local/share")
XDG_CONFIG_HOME = get_path("XDG_CONFIG_HOME", HOME / ".config")
XDG_STATE_HOME = get_path("XDG_STATE_HOME", HOME / ".local/state")
XDG_CACHE_HOME = get_path("XDG_CACHE_HOME", HOME / ".cache")
XDG_DATA_DIRS = list(gen_paths("XDG_DATA_DIRS", "/usr/local/share/:/usr/share/"))
XDG_CONFIG_DIRS = list(gen_paths("XDG_CONFIG_DIRS", "/etc/xdg"))
# This is a valid directory if no runtime dir is detected
XDG_RUNTIME_DIR = get_path(
    "XDG_RUNTIME_DIR", pathlib.Path(f"/tmp/user-{os.getuid()}")  # noqa: S108
)
# endregion


def ensure_resource(
    base_path: pathlib.Path, *sub_paths: Union[os.PathLike, str]
) -> pathlib.Path:
    """Ensure that an appropriate resource exists and return a Path object for it.

    Note: the ``ensure_[type]_resource`` functions are similar to this, but do not take
    a base_path parameter, as those are pre-defined.

    :param base_path: A ``Path`` object as the root. Generally one of the paths
        defined as constants in this module.
    :param sub_paths: any subdirectory names to add, using the specification in
        ``pathlib.PurePath.joinpath()``
    :returns A ``Path`` object pointing to the resource
    :raises various ``OSError`` subclasses if anything goes wrong (see `pathlib`)
    :raises ``ValueError`` if the path it outside the base path.
        See: https://docs.python.org/3/library/pathlib.html#pathlib.PurePath.relative_to
    """
    path = base_path.joinpath(*sub_paths)
    path.relative_to(base_path)
    path.mkdir(parents=True, exist_ok=True)
    return path


ensure_data_resource = functools.partial(ensure_resource, XDG_DATA_HOME)
ensure_data_resource.__doc__ = (
    "Ensure an $XDG_DATA_HOME subdirectory exists. See ``ensure_resource``"
)
ensure_config_resource = functools.partial(ensure_resource, XDG_CONFIG_HOME)
ensure_config_resource.__doc__ = (
    "Ensure $XDG_CONFIG_HOME subdirectory exists. See ``ensure_resource``"
)
ensure_state_resource = functools.partial(ensure_resource, XDG_STATE_HOME)
ensure_state_resource.__doc__ = (
    "Ensure $XDG_STATE_HOME subdirectory exists. See ``ensure_resource``"
)
ensure_cache_resource = functools.partial(ensure_resource, XDG_CACHE_HOME)
ensure_cache_resource.__doc__ = (
    "Ensure $XDG_CACHE_HOME subdirectory exists. See ``ensure_resource``"
)


def find_resource(
    base_paths: Iterable[os.PathLike],
    *sub_paths: Union[os.PathLike, str],
) -> Iterable[pathlib.Path]:
    """Find a resource in a series of path resources.

    :param base_paths: The path locations to look through.
    :param sub_paths: any subdirectory names to add, using the specification in
        ``pathlib.PurePath.joinpath()``
    :yields: ``Path`` objects representing all existing subpaths, in descending order
        of priority.
    """
    sub_path = pathlib.Path(*sub_paths)
    for base in base_paths:
        path = base / sub_path
        path.relative_to(base)
        if path.exists():
            yield path


find_data_resource = functools.partial(find_resource, [XDG_DATA_HOME] + XDG_DATA_DIRS)
find_data_resource.__doc__ = (
    "Find the first data directory matching the given subpaths. See ``find_resource``"
)
find_config_resource = functools.partial(
    find_resource, [XDG_CONFIG_HOME] + XDG_CONFIG_DIRS
)
find_config_resource.__doc__ = (
    "Find the first config directory matching the given subpaths. See ``find_resource``"
)
