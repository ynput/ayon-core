import os
import platform

from ayon_core.pipeline.anatomy.roots import AnatomyRoots


class DummyAnatomy:
    def __init__(self, roots_data):
        self.project_name = "TestProject"
        self._roots_data = roots_data

    def __getitem__(self, key):
        if key == "roots":
            return self._roots_data
        raise KeyError(key)


def test_root_values_expand_user_home(monkeypatch):
    platform_name = platform.system().lower()
    other_platform_name = "darwin" if platform_name != "darwin" else "linux"
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("USERPROFILE", "C:/Users/tester")

    roots_data = {
        "work": {
            platform_name: "~/foo/bar",
            other_platform_name: "~/other/foo",
        }
    }
    roots = AnatomyRoots._parse_dict(roots_data, DummyAnatomy(roots_data))

    work_root = roots["work"]
    expanded_root = os.path.expanduser("~/foo/bar")

    assert str(work_root) == expanded_root
    assert work_root.raw_data[platform_name] == expanded_root
    assert work_root.cleaned_data[platform_name] == (
        expanded_root.replace("\\", "/").rstrip("/")
    )


def test_root_helpers_use_expanded_user_home(monkeypatch):
    platform_name = platform.system().lower()
    monkeypatch.setenv("HOME", "/home/tester")
    monkeypatch.setenv("USERPROFILE", "C:/Users/tester")

    roots_data = {"work": {platform_name: "~/foo/bar"}}
    anatomy_roots = AnatomyRoots(DummyAnatomy(roots_data))

    expanded_root = os.path.expanduser("~/foo/bar")
    root_template_path = "{root[work]}/project/shot/file.ma"
    expanded_file_path = f"{expanded_root}/project/shot/file.ma"

    assert anatomy_roots.path_remapper(root_template_path) == expanded_file_path
    assert anatomy_roots.all_root_paths() == [expanded_root]
    assert anatomy_roots.root_environments() == {
        "AYON_PROJECT_ROOT_WORK": expanded_root
    }
