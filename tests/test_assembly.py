import shutil
import sys
from pathlib import Path

import pytest
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import agent_layout as layout

PROJECT = Path(__file__).resolve().parents[1]


@pytest.fixture
def workspace(tmp_path, monkeypatch):
    for role in ("at", "fb"):
        shutil.copytree(
            PROJECT / "starter" / role, tmp_path / "starter" / role, ignore=layout.IGNORED
        )
    monkeypatch.setattr(layout, "ROOT", tmp_path)
    return tmp_path


def test_normal_folder_and_independent_role_config(workspace):
    at = layout.create_team("at", "alice")
    fb = layout.create_team("fb", "bob")
    at_config = layout.validate(at, "at")
    fb_config = layout.validate(fb, "fb")
    assert at_config[layout.TACTICS["at"]]["HumanDetector"].startswith("src.alice.")
    assert at_config[layout.TACTICS["fb"]]["HumanDetector"].startswith("src.camp_default_2026.fb.")
    assert fb_config[layout.TACTICS["at"]]["HumanDetector"].startswith("src.camp_default_2026.at.")
    assert not (at / "submission.json").exists()
    result = workspace / "export" / "pair"
    layout.assemble_pair(at, fb, result)
    config = layout.load_config(result / "config/module.yaml")
    assert config[layout.TACTICS["at"]] == at_config[layout.TACTICS["at"]]
    assert config[layout.TACTICS["fb"]] == fb_config[layout.TACTICS["fb"]]
    assert (result / "main.py").read_bytes() == (at / "main.py").read_bytes()
    assert not (result / "vendor").exists()
    assert (result / "uv.lock").is_file()
    assert not any(p.is_symlink() for p in result.rglob("*"))


def test_all_four_distinct_pairs(workspace):
    ats = [layout.create_team("at", name) for name in ("alice", "amy")]
    fbs = [layout.create_team("fb", name) for name in ("bob", "bill")]
    for at in ats:
        for fb in fbs:
            output = workspace / "export" / f"{at.name}_{fb.name}"
            layout.assemble_pair(at, fb, output)
            assert (output / "src" / at.name).is_dir()
            assert (output / "src" / fb.name).is_dir()
            assert not (output / "src/team_name").exists()
    assert len(list((workspace / "export").iterdir())) == 4


@pytest.mark.parametrize(
    "change", ["shared", "other_role", "missing_dependency", "foreign_reference"]
)
def test_bad_config_is_rejected(workspace, change):
    agent = layout.create_team("at", "alice")
    path = agent / "config/module.yaml"
    config = layout.load_config(path)
    if change == "shared":
        config["DefaultSearch"]["PathPlanning"] = "src.alice.other.Class"
    elif change == "other_role":
        config[layout.TACTICS["fb"]]["Search"] = config[layout.TACTICS["at"]]["Search"]
    elif change == "missing_dependency":
        del config["alice"]["Search"]["PathPlanning"]
    else:
        config[layout.TACTICS["at"]]["Search"] = "src.another.search.Search"
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError):
        layout.validate(agent, "at")


def test_duplicate_yaml_keys_are_rejected(workspace):
    agent = layout.create_team("at", "alice")
    path = agent / "config/module.yaml"
    with path.open("a") as stream:
        stream.write("\nDefaultSearch: {}\n")
    with pytest.raises(ValueError, match="duplicate"):
        layout.validate(agent, "at")


def test_common_code_change_is_rejected(workspace):
    agent = layout.create_team("at", "alice")
    (agent / "main.py").write_text('print("changed")\n')
    with pytest.raises(ValueError, match="fixed file"):
        layout.validate(agent, "at")


def test_package_collision_and_overwrite_are_rejected(workspace):
    at = layout.create_team("at", "alice")
    fb = layout.create_team("fb", "alice")
    with pytest.raises(ValueError, match="collide"):
        layout.assemble_pair(at, fb, workspace / "pair")
    with pytest.raises(ValueError, match="already exists"):
        layout.create_team("at", "alice")


def test_local_environment_is_not_exported(workspace):
    at = layout.create_team("at", "alice")
    fb = layout.create_team("fb", "bob")
    (at / ".venv").mkdir()
    (at / ".venv/host-link").symlink_to("/tmp")
    result = workspace / "export/pair"
    layout.assemble_pair(at, fb, result)
    assert not (result / ".venv").exists()


def test_packaging_excludes_metadata_and_hashes_only_exported_files(workspace):
    at = layout.create_team("at", "alice")
    fb = layout.create_team("fb", "bob")
    package = at / "src/alice"
    for relative in (
        ".git/broken.py", ".DS_Store", "module/.DS_Store",
        "__pycache__/broken.py", ".pytest_cache/broken.py",
        ".mypy_cache/broken.py", ".coverage", ".coverage.local",
        "htmlcov/index.html", "utility.py.swp", "utility.py.swo", "utility.py~",
        "Thumbs.db", "agent.log.1", "precompute/data", "module/old.pyo",
    ):
        path = package / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("invalid python !")
    (at / "src/.DS_Store").write_text("metadata")
    (package / ".direnv").symlink_to(workspace, target_is_directory=True)
    (package / "utility.py").write_text("VALUE = 42\n")
    (package / "result").write_text("participant asset\n")
    output = workspace / "export/pair"
    record = layout.assemble_pair(at, fb, output)
    exported = output / "src/alice"
    assert record["at_sha256"] == layout.hashes(exported)
    assert (exported / "utility.py").read_text() == "VALUE = 42\n"
    assert (exported / "result").read_text() == "participant asset\n"
    assert not any(layout.IGNORED("", p.relative_to(output).parts) for p in output.rglob("*"))


def test_participant_symlink_is_rejected(workspace):
    agent = layout.create_team("at", "alice")
    (agent / "src/alice/asset").symlink_to(workspace)
    with pytest.raises(ValueError, match="symlinks"):
        layout.validate(agent, "at")


@pytest.mark.parametrize("role", ["at", "fb"])
@pytest.mark.parametrize("slot", ["ExtendActionMove", "CommandExecutorScout"])
def test_upstream_shared_slots_cannot_change_other_role(workspace, role, slot):
    agent = layout.create_team(role, "alice")
    path = agent / "config/module.yaml"
    config = layout.load_config(path)
    config[layout.TACTICS[role]][slot] = config[layout.TACTICS[role]]["Search"]
    path.write_text(yaml.safe_dump(config))
    with pytest.raises(ValueError, match="fixed for both roles"):
        layout.validate(agent, role)
