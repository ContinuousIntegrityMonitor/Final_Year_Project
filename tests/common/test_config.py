"""`cim.toml` loader (T-13, design note section 4; border)."""

from __future__ import annotations

import os
import re
import tomllib
from pathlib import Path

import pytest

from cim.common.config import (
    DEFAULT_STORE,
    CimConfig,
    ConfigError,
    find_config,
    load_config,
    parse_config,
    read_config,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLE = ROOT / "cim.example.toml"

FULL = """
log_level = "DEBUG"

[store]
path = "data/store.sqlite"
origin = "laptop"

[skills]
roots = ["skills", "/opt/skills"]
sweep_interval_s = 30
inotify = false

[mcp.servers.hexstrike]
root = "/opt/mcp/hexstrike"
tools_list = "corpora/tools_list.json"
minimum_tools = 150

[mcp.servers.demo]

[mcp.gateway]
port = 9000

[[mcp.gateway.routes]]
id = "graphiti"
upstream = "http://127.0.0.1:8000/mcp/"
authorization_env = "CIM_MCP_AUTH_GRAPHITI"

[[mcp.gateway.routes]]
id = "local"
upstream = "http://127.0.0.1:9001/mcp"
root = "lab-local"

[dashboard]
port = 8766

[scorer]
threshold_milli = 3000

[watchdog]
heartbeat_s = 5
"""


def _write(folder: Path, text: str, name: str = "cim.toml") -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_text(text, encoding="utf-8")
    return path


def _home(tmp_path: Path) -> dict[str, str]:
    """An environment whose home holds no config, so the user's own file never leaks in."""
    return {"HOME": str(tmp_path / "home")}


def test_no_file_gives_todays_defaults(tmp_path: Path) -> None:
    config = load_config(env=_home(tmp_path), cwd=tmp_path)
    assert config == CimConfig()
    assert config.source is None
    assert config.store_path == DEFAULT_STORE == Path("logs/cim-store.sqlite")
    assert config.store.origin == "vm-mon"
    assert config.skills.roots == () and config.skills.sweep_interval_s == 60
    assert config.mcp.servers == {} and config.mcp.gateway is None
    assert config.dashboard.port == 8765 and config.scorer.threshold_milli == 4000
    assert (config.watchdog.heartbeat_s, config.watchdog.max_restarts) == (10, 5)


def test_full_file_is_read_and_paths_follow_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path / "etc", FULL)
    config = load_config(path, env=_home(tmp_path))
    here = tmp_path / "etc"
    assert config.source == path and config.log_level == "DEBUG"
    assert config.store.path == here / "data/store.sqlite"
    assert config.store.origin == "laptop"
    assert config.skills.roots == (here / "skills", Path("/opt/skills"))
    assert (config.skills.sweep_interval_s, config.skills.inotify) == (30, False)
    hexstrike = config.server("hexstrike")
    assert hexstrike is not None
    assert hexstrike.tools_list == here / "corpora/tools_list.json"
    assert hexstrike.minimum_tools == 150 and hexstrike.origin is None
    assert config.server("demo") is not None and config.server("nope") is None
    assert list(config.mcp.servers) == ["demo", "hexstrike"]  # sorted
    gateway = config.mcp.gateway
    assert gateway is not None and (gateway.host, gateway.port) == ("127.0.0.1", 9000)
    assert [(r.id, r.root_name, r.authorization_env) for r in gateway.routes] == [
        ("graphiti", "cursor-graphiti", "CIM_MCP_AUTH_GRAPHITI"),
        ("local", "lab-local", None),
    ]
    assert config.dashboard.port == 8766 and config.scorer.threshold_milli == 3000
    assert config.watchdog.heartbeat_s == 5 and config.watchdog.backoff_max_s == 60


def test_home_and_absolute_paths_are_kept(tmp_path: Path) -> None:
    path = _write(tmp_path, '[store]\npath = "~/cim/store.sqlite"\n')
    assert read_config(path).store.path == Path("~/cim/store.sqlite").expanduser()


def test_where_the_file_is_found(tmp_path: Path) -> None:
    env = _home(tmp_path)
    user = _write(tmp_path / "home/.config/cim", "")
    assert find_config(env=env, cwd=tmp_path) == user
    xdg = _write(tmp_path / "xdg/cim", "")
    assert find_config(env={**env, "XDG_CONFIG_HOME": str(tmp_path / "xdg")}, cwd=tmp_path) == xdg
    here = _write(tmp_path / "work", "")
    assert find_config(env=env, cwd=tmp_path / "work") == here
    named = _write(tmp_path / "named", "", "other.toml")
    assert find_config(env={**env, "CIM_CONFIG": str(named)}, cwd=tmp_path / "work") == named
    flag = _write(tmp_path / "flag", "")
    assert find_config(flag, env={**env, "CIM_CONFIG": str(named)}, cwd=tmp_path) == flag


def test_a_named_file_must_exist(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="--config: no such file"):
        find_config(tmp_path / "missing.toml", env=_home(tmp_path))
    with pytest.raises(ConfigError, match="CIM_CONFIG: no such file"):
        find_config(env={"CIM_CONFIG": str(tmp_path / "missing.toml")}, cwd=tmp_path)


def test_cim_skill_roots_beats_the_file(tmp_path: Path) -> None:
    path = _write(tmp_path, '[skills]\nroots = ["from-file"]\nsweep_interval_s = 5\n')
    env = {**_home(tmp_path), "CIM_SKILL_ROOTS": os.pathsep.join(["/a", "/b"])}
    config = load_config(path, env=env)
    assert config.skills.roots == (Path("/a"), Path("/b"))
    assert config.skills.sweep_interval_s == 5  # the rest of the section is kept
    assert load_config(path, env=_home(tmp_path)).skills.roots == (tmp_path / "from-file",)


@pytest.mark.parametrize(
    ("text", "named"),
    [
        ('[mcp.gateway]\naccess_token = "x"\n', "mcp.gateway.access_token"),
        ('[[mcp.gateway.routes]]\nid = "a"\nupstream = "u"\nBearer_Token = "x"\n', "routes[0]"),
        ('[store]\npassword = "x"\n', "store.password"),
        ('client_secret = "x"\n', "client_secret"),
    ],
)
def test_secrets_are_refused(tmp_path: Path, text: str, named: str) -> None:
    with pytest.raises(ConfigError, match="secrets do not belong") as caught:
        read_config(_write(tmp_path, text))
    assert named in str(caught.value)


def test_authorization_env_is_a_name_not_a_secret(tmp_path: Path) -> None:
    text = '[mcp.gateway]\n[[mcp.gateway.routes]]\nid = "a"\nupstream = "u"\n'
    text += 'authorization_env = "Bearer abc.def"\n'  # a token pasted where a name goes
    with pytest.raises(ConfigError, match="authorization_env"):
        read_config(_write(tmp_path, text))


@pytest.mark.parametrize(
    ("text", "problem"),
    [
        ("[skils]\nroots = []\n", "unknown section or key: skils"),
        ('[skills]\nroot = ["x"]\n', "skills.root: unknown key"),
        ('[skills]\nsweep_interval_s = "60"\n', "skills.sweep_interval_s"),
        ("[skills]\nsweep_interval_s = 0\n", "skills.sweep_interval_s"),
        ('[skills]\ninotify = "yes"\n', "skills.inotify"),
        ("[dashboard]\nport = 70000\n", "dashboard.port"),
        ("[scorer]\nthreshold_milli = 4.0\n", "scorer.threshold_milli"),
        ('log_level = "LOUD"\n', "log_level"),
        ('[mcp.servers."bad/id"]\n', "server ids must match"),
        ("[mcp.gateway]\nport = 1\n", "mcp.gateway.routes"),
        (
            '[[mcp.gateway.routes]]\nid = "a"\nupstream = "u"\n'
            '[[mcp.gateway.routes]]\nid = "a"\nupstream = "v"\n',
            "route ids must be unique: a",
        ),
        ('[[mcp.gateway.routes]]\nid = "a/b"\nupstream = "u"\n', "mcp.gateway.routes.0.id"),
    ],
)
def test_bad_values_are_named(tmp_path: Path, text: str, problem: str) -> None:
    with pytest.raises(ConfigError) as caught:
        read_config(_write(tmp_path, text))
    assert problem in str(caught.value)
    assert str(tmp_path / "cim.toml") in str(caught.value)  # the message names the file


def test_broken_toml_is_named(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="not valid TOML"):
        read_config(_write(tmp_path, "[store\n"))


def test_the_config_is_frozen() -> None:
    config = CimConfig()
    with pytest.raises(ValueError, match="frozen"):
        config.store.origin = "elsewhere"  # type: ignore[misc]


def test_the_example_file_is_valid_and_matches_the_defaults() -> None:
    """cim.example.toml must never go stale: what it shows uncommented is the default."""
    example = parse_config(tomllib.loads(EXAMPLE.read_text(encoding="utf-8")))
    assert example.model_dump(exclude={"source"}) == CimConfig().model_dump(exclude={"source"})


def test_the_examples_commented_tables_are_valid_too() -> None:
    """Uncomment every commented table and key in the example: it must still load."""
    lines = EXAMPLE.read_text(encoding="utf-8").splitlines()
    body = "\n".join(re.sub(r"^# (?=\[|[a-z_]+ = )", "", line) for line in lines)
    config = parse_config(tomllib.loads(body))
    hexstrike = config.server("hexstrike")
    assert hexstrike is not None and hexstrike.minimum_tools == 150
    assert config.mcp.gateway is not None
    assert [r.id for r in config.mcp.gateway.routes] == ["graphiti"]
    assert config.log_level == "INFO"
