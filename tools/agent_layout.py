"""The normal ADF agent folder and the small, explicit configuration merge policy."""

from __future__ import annotations

import ast
import copy
import hashlib
import keyword
import re
import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]
TACTICS = {"at": "DefaultTacticsAmbulanceTeam", "fb": "DefaultTacticsFireBrigade"}
# Upstream FB reads the AT keys for these slots. Keep both roles at the
# distributed defaults so an AT submission cannot change FB behavior.
FIXED_SLOTS = {"ExtendActionMove", "CommandExecutorScout"}
NAME = re.compile(r"[a-z][a-z0-9_]*\Z")
FIXED = (
    "main.py",
    "pyproject.toml",
    "uv.lock",
    ".python-version",
    "LICENSE.adf-python",
    "config/launcher.yaml",
    "config/development.json",
    "src/__init__.py",
    "src/camp_default_2026",
)
IGNORED = shutil.ignore_patterns(
    ".git",
    ".venv",
    ".direnv",
    "__pycache__",
    "*.py[cod]",
    "agent.log*",
    "precompute",
    ".ruff_cache",
    ".pytest_cache",
    ".mypy_cache",
    ".coverage",
    ".coverage.*",
    "htmlcov",
    ".DS_Store",
    "Thumbs.db",
    "*.swp",
    "*.swo",
    "*~",
)


class UniqueLoader(yaml.SafeLoader):
    pass


def unique_mapping(loader, node, deep=False):
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if not isinstance(key, str) or key in result:
            raise ValueError(f"duplicate or non-string YAML key: {key!r}")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


UniqueLoader.add_constructor(yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG, unique_mapping)


def load_config(path):
    config = yaml.load(path.read_text(), Loader=UniqueLoader)
    if not isinstance(config, dict):
        raise ValueError(f"{path}: expected a YAML mapping")
    # ADF flattens nested YAML into dotted keys: reject collisions in that space too.
    flatten(config)
    return config


def flatten(config, prefix=""):
    result = {}
    for key, value in config.items():
        if not isinstance(key, str) or not key or "." in key:
            raise ValueError("use nested YAML mappings rather than dotted keys")
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            result.update(flatten(value, name))
        elif isinstance(value, str):
            result[name] = value
        else:
            raise ValueError(f"{name}: class reference must be a string")
    return result


def check_name(team):
    if (
        not NAME.fullmatch(team)
        or keyword.iskeyword(team)
        or team
        in {
            "team_name",
            "camp_default_2026",
            "src",
            "config",
            "vendor",
            "adf_core_python",
            "rcrscore",
        }
    ):
        raise ValueError("team must be a non-reserved lowercase Python identifier")


def hashes(path):
    if path.is_file():
        return {path.name: hashlib.sha256(path.read_bytes()).hexdigest()}
    if not path.is_dir():
        raise ValueError(f"missing required path: {path}")
    return {
        str(p.relative_to(path)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted(path.rglob("*"))
        if p.is_file() and not IGNORED("", p.relative_to(path).parts)
    }


def template_config(role, team):
    path = ROOT / "starter" / role / "config/module.yaml"
    return yaml.load(path.read_text().replace("team_name", team), Loader=UniqueLoader)


def baseline_config():
    config = copy.deepcopy(template_config("at", "team_name"))
    del config["team_name"]
    for slot, file, cls in [
        ("HumanDetector", "sample_human_detector", "SampleHumanDetector"),
        ("Search", "sample_search", "SampleSearch"),
    ]:
        config[TACTICS["at"]][slot] = f"src.camp_default_2026.at.module.complex.{file}.{cls}"
    return config


def local_class_exists(agent, ref, allowed):
    parts = ref.split(".")
    if not all(p.isidentifier() for p in parts):
        raise ValueError(f"invalid class reference: {ref}")
    if ref.startswith("adf_core_python.implement."):
        if ref not in set(flatten(baseline_config()).values()):
            raise ValueError(f"upstream class is not part of the fixed baseline: {ref}")
        return
    if len(parts) < 4 or parts[0] != "src" or parts[1] not in allowed:
        raise ValueError(f"foreign package reference: {ref}")
    module = agent.joinpath(*parts[:-1]).with_suffix(".py")
    if not module.is_file():
        module = agent.joinpath(*parts[:-1], "__init__.py")
    if not module.is_file():
        raise ValueError(f"missing module for {ref}")
    body = ast.parse(module.read_text(), filename=str(module)).body
    names = {n.name for n in body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    for node in body:
        if isinstance(node, (ast.ImportFrom, ast.Import)):
            names.update(alias.asname or alias.name for alias in node.names)
    if parts[-1] not in names:
        raise ValueError(f"missing class definition or import: {ref}")


def validate(agent, role):
    agent = Path(agent).resolve()
    team = agent.name
    check_name(team)
    template = ROOT / "starter" / role
    # Ignore ordinary local environments and runtime outputs; they are never exported.
    paths = [
        p
        for p in agent.rglob("*")
        if not IGNORED("", p.relative_to(agent).parts)
    ]
    if any(p.is_symlink() for p in paths):
        raise ValueError(f"{agent}: symlinks are not accepted")
    for name in FIXED:
        expected = template / name
        actual = agent / name
        if name == "config/launcher.yaml":
            if not actual.is_file() or actual.read_text() != expected.read_text().replace(
                "team_name", team
            ):
                raise ValueError(f"{agent}: fixed launcher.yaml was changed")
        elif hashes(actual) != hashes(expected):
            raise ValueError(f"{agent}: fixed file or directory changed: {name}")
    if {p.name for p in (agent / "src").iterdir() if not IGNORED("", [p.name])} != {
        "__init__.py",
        "camp_default_2026",
        team,
    }:
        raise ValueError(f"{agent}: src must contain only own package and fixed baseline")
    if not (agent / "src" / team / "__init__.py").is_file():
        raise ValueError(f"{agent}: missing team package")
    config = load_config(agent / "config/module.yaml")
    expected = template_config(role, team)
    if config.keys() != expected.keys():
        raise ValueError(f"{agent}: unexpected or missing top-level configuration")
    for key in expected:
        if key not in {TACTICS[role], team} and config[key] != expected[key]:
            raise ValueError(f"{agent}: fixed configuration was changed: {key}")
    slots = config[TACTICS[role]]
    if not isinstance(slots, dict) or slots.keys() != expected[TACTICS[role]].keys():
        raise ValueError(f"{agent}: invalid tactics slots")
    for slot, ref in slots.items():
        if slot in FIXED_SLOTS and ref != expected[TACTICS[role]][slot]:
            raise ValueError(f"{agent}: {slot} is fixed for both roles (upstream shared key)")
        if not isinstance(ref, str):
            raise ValueError(f"{agent}: invalid class reference")
        if ref != expected[TACTICS[role]][slot] and not ref.startswith(f"src.{team}."):
            raise ValueError(f"{agent}: {slot} must refer to own package")
    for ref in flatten(config).values():
        local_class_exists(agent, ref, {team, "camp_default_2026"})
    flat = flatten(config)
    for path in (agent / "src" / team).rglob("*.py"):
        if IGNORED("", path.relative_to(agent).parts):
            continue
        tree = ast.parse(path.read_text(), filename=str(path))
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr in {"get_module", "get_extend_action", "get_command_executor"}
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)
            ):
                key = node.args[0].value
                if not key.startswith(team + "."):
                    raise ValueError(f"{path}: use team-specific configuration keys: {key}")
                if key not in flat:
                    raise ValueError(f"{path}: missing module configuration: {key}")
    return config


def create_team(role, team, destination=None):
    check_name(team)
    destination = destination or ROOT / "submissions" / role / team
    if destination.exists():
        raise ValueError(f"already exists: {destination}")
    if destination.name != team:
        raise ValueError("destination folder must have the team name")
    shutil.copytree(ROOT / "starter" / role, destination, ignore=IGNORED)
    (destination / "src/team_name").rename(destination / "src" / team)
    for path in [
        *(destination / "src" / team).rglob("*.py"),
        destination / "config/module.yaml",
        destination / "config/launcher.yaml",
    ]:
        path.write_text(path.read_text().replace("team_name", team))
    validate(destination, role)
    return destination


def assemble_pair(at, fb, destination):
    at, fb = Path(at).resolve(), Path(fb).resolve()
    if at.name == fb.name:
        raise ValueError("AT and FB package names collide")
    configurations = {role: validate(path, role) for role, path in [("at", at), ("fb", fb)]}
    if destination.exists():
        raise ValueError(f"already exists: {destination}")
    config = baseline_config()
    for role, agent in [("at", at), ("fb", fb)]:
        config[TACTICS[role]] = configurations[role][TACTICS[role]]
        config[agent.name] = configurations[role][agent.name]
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Publish only after all files are assembled and checked.
    import tempfile

    with tempfile.TemporaryDirectory(prefix=".assembling-", dir=destination.parent) as tmp:
        staged = Path(tmp) / "agent"
        shutil.copytree(ROOT / "starter/at", staged, ignore=IGNORED)
        shutil.rmtree(staged / "src/team_name")
        for agent in (at, fb):
            shutil.copytree(agent / "src" / agent.name, staged / "src" / agent.name, ignore=IGNORED)
        (staged / "config/module.yaml").write_text(yaml.safe_dump(config, sort_keys=False))
        launcher = staged / "config/launcher.yaml"
        launcher.write_text(launcher.read_text().replace("team_name", destination.name))
        for ref in flatten(config).values():
            local_class_exists(staged, ref, {at.name, fb.name, "camp_default_2026"})
        staged.rename(destination)
    return {
        "at": at.name,
        "fb": fb.name,
        "folder": destination.name,
        "at_sha256": hashes(at / "src" / at.name),
        "fb_sha256": hashes(fb / "src" / fb.name),
        "at_module_yaml_sha256": hashes(at / "config/module.yaml"),
        "fb_module_yaml_sha256": hashes(fb / "config/module.yaml"),
    }
