"""Tests for pyxdg2.basedir."""
import contextlib
import importlib
import os
import pathlib
import shutil
import tempfile
from unittest import mock

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pytest_check import check

from pyxdg2 import basedir

VALID_SUB_PATHS = st.text(
    alphabet=st.characters(blacklist_categories=["C"]), min_size=1
).filter(lambda x: not x.startswith("/"))


@contextlib.contextmanager
def fake_environ(control=None):
    control = control or {}
    with mock.patch("os.environ", new=mock.MagicMock(spec_set=dict)):
        mock_env = os.environ
        mock_env.__setitem__.side_effect = control.__setitem__
        mock_env.__getitem__.side_effect = control.__getitem__
        mock_env.get.side_effect = control.get
        yield mock_env, control


class TestGetPath:
    @given(fallback=st.builds(pathlib.Path))
    def test_falls_back_when_none(self, fallback):
        with fake_environ() as (mock_env, control):
            actual = basedir.get_path(None, fallback)

        mock_env.get.assert_not_called()
        assert fallback == actual

    @given(fallback=st.builds(pathlib.Path))
    def test_falls_back_when_invalid(self, fallback):
        with fake_environ() as (mock_env, control):
            actual = basedir.get_path("PATH", fallback)

        mock_env.get.assert_called_once_with("PATH")
        assert fallback == actual

    def test_no_fallback_when_invalid(self):
        with fake_environ(), pytest.raises(KeyError):
            basedir.get_path("anything, really", None)

    @given(
        control=st.dictionaries(st.text(min_size=1), st.text(min_size=1), min_size=1),
        rng=st.randoms(),
    )
    def test_gets_from_environment(self, control, rng):
        with fake_environ(control) as (mock_env, _):
            variable = rng.choice(list(control.keys()))

            actual = basedir.get_path(variable, None)

        assert pathlib.Path(control[variable]) == actual


class TestGenPaths:
    path_params = [
        pytest.param(
            [pathlib.Path("/"), pathlib.Path("/usr"), pathlib.Path("/bin")], id="basic"
        )
    ]

    def test_falls_back(self):
        with fake_environ() as (mock_env, control):
            actual = list(basedir.gen_paths("", "/"))

        assert [pathlib.Path("/")] == actual

    def test_totally_invalid(self):
        with fake_environ(), pytest.raises(KeyError):
            list(basedir.gen_paths("", None))

    @pytest.mark.parametrize("paths", path_params)
    def test_fallback_outputs_same_as_inputs(self, paths):
        path_spec = ":".join(path.as_posix() for path in paths)

        with fake_environ() as (mock_env, _):
            actual = list(basedir.gen_paths("", path_spec))

        assert paths == actual

    @pytest.mark.parametrize("paths", path_params)
    @pytest.mark.parametrize("env_var", ["SOME_VAR"])
    def test_env_outputs_same_as_inputs(self, paths, env_var):
        path_spec = ":".join(path.as_posix() for path in paths)
        with fake_environ() as (mock_env, control):
            control[env_var] = path_spec

            actual = list(basedir.gen_paths(env_var))

        assert paths == actual


class TestEnvVarPaths:
    environment_specs = [
        pytest.param(
            {
                "HOME": "/",
                "XDG_DATA_HOME": "/",
                "XDG_CONFIG_HOME": "/",
                "XDG_STATE_HOME": "/",
                "XDG_CACHE_HOME": "/",
                "XDG_DATA_DIRS": "/",
                "XDG_CONFIG_DIRS": "/",
                "XDG_RUNTIME_DIR": "/",
            },
            id="everything_/",
        ),
    ]

    @pytest.mark.parametrize("control", environment_specs)
    def test_get_vars(self, control):
        patch_home = mock.patch(
            "pathlib.Path.home", return_value=pathlib.Path(control["HOME"])
        )
        with fake_environ(control) as (mock_env, _), patch_home:
            importlib.reload(basedir)

        check.equal(basedir.HOME.as_posix(), control["HOME"])
        check.equal(basedir.XDG_DATA_HOME.as_posix(), control["XDG_DATA_HOME"])
        check.equal(basedir.XDG_CONFIG_HOME.as_posix(), control["XDG_CONFIG_HOME"])
        check.equal(basedir.XDG_STATE_HOME.as_posix(), control["XDG_STATE_HOME"])
        check.equal(basedir.XDG_CACHE_HOME.as_posix(), control["XDG_CACHE_HOME"])
        check.equal(basedir.XDG_DATA_DIRS[0].as_posix(), control["XDG_DATA_DIRS"])
        check.equal(basedir.XDG_CONFIG_DIRS[0].as_posix(), control["XDG_CONFIG_DIRS"])
        check.equal(basedir.XDG_RUNTIME_DIR.as_posix(), control["XDG_RUNTIME_DIR"])

    @pytest.mark.parametrize("home_path", ["/"])
    def test_vars_unset(self, home_path):
        patch_getuid = mock.patch("os.getuid", return_value=1000)
        patch_home = mock.patch(
            "pathlib.Path.home", return_value=pathlib.Path(home_path)
        )
        with fake_environ({"HOME": home_path}), patch_getuid, patch_home:
            importlib.reload(basedir)

        check.equal(basedir.HOME.as_posix(), home_path)
        check.equal(basedir.XDG_DATA_HOME, pathlib.Path(home_path, ".local/share"))
        check.equal(basedir.XDG_CONFIG_HOME, pathlib.Path(home_path, ".config"))
        check.equal(basedir.XDG_STATE_HOME, pathlib.Path(home_path, ".local/state"))
        check.equal(basedir.XDG_CACHE_HOME, pathlib.Path(home_path, ".cache"))
        check.equal(
            basedir.XDG_DATA_DIRS,
            [pathlib.Path("/usr/local/share"), pathlib.Path("/usr/share")],
        )
        check.equal(basedir.XDG_CONFIG_DIRS, [pathlib.Path("/etc/xdg")])
        check.equal(
            basedir.XDG_RUNTIME_DIR, pathlib.Path("/tmp/user-1000")  # noqa=S108
        )


class TestEnsureResource:
    @given(
        st.lists(VALID_SUB_PATHS.filter(lambda x: x != "."), min_size=1)  # noqa=PLR2004
    )
    def test_creates_paths(self, sub_paths):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = pathlib.Path(tempdir)
            expected = temp_path.joinpath(*sub_paths)
            assert not expected.exists(), "Oops this path isn't supposed to exist"

            actual = basedir.ensure_resource(temp_path, *sub_paths)

            check.equal(expected, actual)
            check.is_true(actual.exists())

    @given(st.lists(VALID_SUB_PATHS, min_size=1))
    def test_returns_existing_path(self, sub_paths):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = pathlib.Path(tempdir)
            expected = temp_path.joinpath(*sub_paths)
            expected.mkdir(parents=True, exist_ok=True)

            actual = basedir.ensure_resource(temp_path, *sub_paths)

            check.equal(expected, actual)
            check.is_true(actual.exists())

    def test_fails_when_mkdir_fails(self):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = pathlib.Path(tempdir)
            expected = temp_path.joinpath("cant_touch_dis")
            expected.mkdir(mode=0)

            with pytest.raises(PermissionError):
                basedir.ensure_resource(temp_path, "cant_touch_dis/no")

    def test_fails_when_not_relative(self):
        with pytest.raises(ValueError, match=r"'/'.*'/home'"):
            basedir.ensure_resource(pathlib.Path("/home"), "/")


class TestFindResource:
    def test_empty_base_paths(self):
        assert not list(basedir.find_resource([]))

    @given(st.lists(VALID_SUB_PATHS, min_size=1))
    def test_sub_paths_nonexistent(self, sub_paths):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = pathlib.Path(tempdir)

            assert not list(basedir.find_resource([temp_path], *sub_paths))

    @given(st.lists(VALID_SUB_PATHS, min_size=1))
    def test_subpath_exists(self, sub_paths):
        with tempfile.TemporaryDirectory() as tempdir:
            temp_path = pathlib.Path(tempdir)
            expected = temp_path.joinpath(*sub_paths)
            expected.mkdir(parents=True, exist_ok=True)

            actual = list(basedir.find_resource([temp_path], *sub_paths))

            assert [expected] == actual

    @given(st.lists(VALID_SUB_PATHS, min_size=1), st.randoms())
    def test_some_subpaths(self, sub_paths, rng):
        temp_paths = []
        try:
            for _i in range(rng.randint(2, 10)):
                temp_paths.append(pathlib.Path(tempfile.mkdtemp()))
            expected_parents = rng.choices(temp_paths, rng.randint(0, len(temp_paths)))
            expected_paths = [path.joinpath(*sub_paths) for path in expected_parents]
            for path in expected_paths:
                path.mkdir(parents=True)

            actual = list(basedir.find_resource(temp_paths, *sub_paths))

            assert expected_paths == actual

        finally:
            for path in temp_paths:
                shutil.rmtree(path, ignore_errors=True)
