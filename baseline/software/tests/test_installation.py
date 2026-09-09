from pathlib import Path
import pytest
from cc_repro.cli import parser
from cc_repro.resources import prepare_workspace, verify_workspace, manifest


def test_resources_and_reuse(tmp_path):
    workspace = tmp_path / "work"
    project, vault = prepare_workspace(workspace)
    assert manifest()["schema"] == "cc-public-resources/1.0"
    assert not (project / "paper").exists()
    assert not (project / "figures").exists()
    assert vault.is_file()
    output = project / "build/runs/example/result.txt"
    output.parent.mkdir(parents=True)
    output.write_text("result")
    assert verify_workspace(workspace) == (project, vault)
    assert prepare_workspace(workspace) == (project, vault)


def test_tampering_and_shadow_modules_rejected(tmp_path):
    workspace = tmp_path / "work"
    project, _ = prepare_workspace(workspace)
    source = project / "README.md"
    before = source.read_bytes()
    source.write_bytes(before + b"modified")
    with pytest.raises(ValueError, match="hash mismatch"):
        verify_workspace(workspace)
    source.write_bytes(before)
    (project / "numpy.py").write_text("raise RuntimeError('shadow')")
    with pytest.raises(ValueError, match="unexpected file"):
        verify_workspace(workspace)


def test_unbound_directory_and_symlinks_rejected(tmp_path):
    with pytest.raises(FileNotFoundError):
        prepare_workspace(tmp_path)
    workspace = tmp_path / "work"
    project, _ = prepare_workspace(workspace)
    (project / "build").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError, match="symlink"):
        verify_workspace(workspace)


@pytest.mark.parametrize("argument,value", [("--run-id", "../escape"), ("--timeout", "nan"),
                                             ("--timeout", "0"), ("--L", "5")])
def test_bad_cli_input(argument, value):
    argv = ["potts", "--workspace", "work", "--run-id", "valid", "--L", "6", argument, value]
    with pytest.raises(SystemExit) as error:
        parser().parse_args(argv)
    assert error.value.code == 2

