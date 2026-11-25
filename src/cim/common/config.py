"""One config file for both sides: `cim.toml` (T-13; border file, both review).

docs/T13_PIPELINE_DESIGN.md, section 4. TOML, read with the standard library's `tomllib`.

- **Where it is found:** `--config` > `CIM_CONFIG` > `./cim.toml` > `$XDG_CONFIG_HOME/cim/cim.toml`
  (default `~/.config/cim/cim.toml`). With no file, the built-in defaults apply, which are
  today's defaults, so nothing changes for a caller that has no file.
- **What wins:** flag > environment variable > file > default. The loader applies the shared
  variable (`CIM_SKILL_ROOTS`) over the file; each command applies its own flags, and its own
  variables (`CIM_PROXY_*`, `CIM_HTTP_GATEWAY_TOKEN`), on top of what it is handed.
- **No secrets in the file:** a key whose name holds `token`, `secret`, `password` or
  `passwd` is refused, wherever it is. Secrets stay in the environment; a route names the
  variable that holds its Bearer (`authorization_env`), never the token (test report H1).
- **No silent typos:** an unknown section or key is refused, with its dotted name.
- **Paths in the file** are relative to the file's own directory; `~` is expanded. The
  built-in defaults stay relative to the working directory, as today.

Build it once (`load_config`) and pass it down: no module should read the environment for a
setting this file holds.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

CONFIG_ENV = "CIM_CONFIG"
SKILL_ROOTS_ENV = "CIM_SKILL_ROOTS"  # the same name cim.skills.inventory reads
FILE_NAME = "cim.toml"
DEFAULT_STORE = Path("logs/cim-store.sqlite")

_SECRET_KEY = re.compile(r"token|secret|password|passwd", re.IGNORECASE)
_ID = r"^[A-Za-z0-9][A-Za-z0-9._-]*$"  # usable in a URL path segment and a file name


class ConfigError(ValueError):
    """The config file could not be found, read or accepted. The message says which and why."""


class _Section(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class StoreSettings(_Section):
    path: Path = DEFAULT_STORE
    origin: str = Field(default="vm-mon", min_length=1)  # host name recorded with artefacts


class SkillsSettings(_Section):
    roots: tuple[Path, ...] = ()  # CIM_SKILL_ROOTS still overrides
    sweep_interval_s: int = Field(default=60, ge=1)
    inotify: bool = True


class McpServerSettings(_Section):
    """`[mcp.servers.<id>]`: what `cim proxy --server <id>` and the offline inventory read."""

    root: str = Field(default="unknown", min_length=1)
    origin: str | None = None  # defaults to [store].origin
    tools_list: Path | None = None  # optional: offline `cim inventory` / `cim sweep`
    minimum_tools: int = Field(default=0, ge=0)


class GatewayRouteSettings(_Section):
    """`[[mcp.gateway.routes]]`: one upstream behind `/s/<id>/`."""

    id: str = Field(pattern=_ID)
    upstream: str = Field(min_length=1)
    origin: str = Field(default="cursor", min_length=1)
    root: str | None = None  # defaults to "cursor-<id>", as the gateway JSON does
    authorization_env: str | None = Field(default=None, pattern=r"^[A-Za-z_][A-Za-z0-9_]*$")

    @property
    def root_name(self) -> str:
        return self.root or f"cursor-{self.id}"


class GatewaySettings(_Section):
    """`[mcp.gateway]`: present means `cim watch` starts the gateway."""

    host: str = "127.0.0.1"
    port: int = Field(default=8877, ge=1, le=65535)
    routes: tuple[GatewayRouteSettings, ...] = Field(min_length=1)

    @field_validator("routes")
    @classmethod
    def _unique_ids(
        cls, routes: tuple[GatewayRouteSettings, ...]
    ) -> tuple[GatewayRouteSettings, ...]:
        ids = [route.id for route in routes]
        repeated = sorted({rid for rid in ids if ids.count(rid) > 1})
        if repeated:
            raise ValueError(f"route ids must be unique: {', '.join(repeated)}")
        return routes


class McpSettings(_Section):
    servers: Mapping[str, McpServerSettings] = Field(default_factory=dict)
    gateway: GatewaySettings | None = None

    @field_validator("servers")
    @classmethod
    def _server_ids(cls, servers: Mapping[str, McpServerSettings]) -> dict[str, McpServerSettings]:
        bad = sorted(name for name in servers if re.fullmatch(_ID, name) is None)
        if bad:
            raise ValueError(f"server ids must match {_ID}: {', '.join(bad)}")
        return dict(sorted(servers.items()))


class DashboardSettings(_Section):
    host: str = "127.0.0.1"
    port: int = Field(default=8765, ge=1, le=65535)


class ScorerSettings(_Section):
    threshold_milli: int = Field(default=4000, ge=0, le=10_000)  # T-16: z >= 4.0


class WatchdogSettings(_Section):
    heartbeat_s: int = Field(default=10, ge=1)
    backoff_max_s: int = Field(default=60, ge=1)
    max_restarts: int = Field(default=5, ge=1)  # in 10 minutes; then give up on that child


class CimConfig(_Section):
    """Everything `cim.toml` can say, with today's defaults for whatever it leaves out."""

    source: Path | None = None  # the file it came from; None means built-in defaults only
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    store: StoreSettings = StoreSettings()
    skills: SkillsSettings = SkillsSettings()
    mcp: McpSettings = McpSettings()
    dashboard: DashboardSettings = DashboardSettings()
    scorer: ScorerSettings = ScorerSettings()
    watchdog: WatchdogSettings = WatchdogSettings()

    @property
    def store_path(self) -> Path:
        return self.store.path

    def server(self, server_id: str) -> McpServerSettings | None:
        """`[mcp.servers.<server_id>]`, or None when the file does not name that server."""
        return self.mcp.servers.get(server_id)


_FILE_KEYS = ("log_level", "store", "skills", "mcp", "dashboard", "scorer", "watchdog")


def find_config(
    explicit: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> Path | None:
    """The config file to read, or None when there is none.

    A file named by `--config` or `CIM_CONFIG` must exist; the two default places are only
    looked at.
    """
    source = os.environ if env is None else env
    if explicit is not None:
        if not explicit.expanduser().is_file():
            raise ConfigError(f"--config: no such file: {explicit}")
        return explicit.expanduser()
    named = source.get(CONFIG_ENV, "").strip()
    if named:
        path = Path(named).expanduser()
        if not path.is_file():
            raise ConfigError(f"{CONFIG_ENV}: no such file: {named}")
        return path
    here = (cwd or Path.cwd()) / FILE_NAME
    if here.is_file():
        return here
    config_home = source.get("XDG_CONFIG_HOME", "").strip()
    base = Path(config_home) if config_home else Path(source.get("HOME", "~")) / ".config"
    user = (base / "cim" / FILE_NAME).expanduser()
    return user if user.is_file() else None


def load_config(
    explicit: Path | None = None,
    *,
    env: Mapping[str, str] | None = None,
    cwd: Path | None = None,
) -> CimConfig:
    """Find, read and check the config, then apply the shared environment variable over it."""
    source = os.environ if env is None else env
    path = find_config(explicit, env=source, cwd=cwd)
    config = CimConfig() if path is None else read_config(path)
    roots = [Path(part) for part in source.get(SKILL_ROOTS_ENV, "").split(os.pathsep) if part]
    if roots:
        skills = config.skills.model_copy(update={"roots": tuple(roots)})
        config = config.model_copy(update={"skills": skills})
    return config


def read_config(path: Path) -> CimConfig:
    """One file, checked, with its paths resolved against its own directory. No environment."""
    try:
        raw = tomllib.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise ConfigError(f"{path}: cannot read: {exc.strerror or exc}") from None
    except tomllib.TOMLDecodeError as exc:
        raise ConfigError(f"{path}: not valid TOML: {exc}") from None
    return parse_config(raw, source=path)


def parse_config(raw: Mapping[str, Any], *, source: Path | None = None) -> CimConfig:
    """A parsed TOML document as a `CimConfig`. Relative paths are taken from `source`'s folder."""
    where = str(source) if source is not None else "config"
    secrets = _secret_keys(raw)
    if secrets:
        raise ConfigError(
            f"{where}: secrets do not belong in the config file: {', '.join(secrets)}. "
            "Put the value in an environment variable (a gateway route names it with "
            "authorization_env)."
        )
    unknown = [key for key in raw if key not in _FILE_KEYS]
    if unknown:
        raise ConfigError(f"{where}: unknown section or key: {', '.join(sorted(unknown))}")
    base = source.parent if source is not None else None
    try:
        config = CimConfig.model_validate({**_with_paths(raw, base), "source": source})
    except ValidationError as exc:
        raise ConfigError(f"{where}: " + "; ".join(_problems(exc))) from None
    return config


def _secret_keys(value: Any, prefix: str = "") -> list[str]:
    found: list[str] = []
    if isinstance(value, Mapping):
        for key, item in value.items():
            name = f"{prefix}{key}"
            if _SECRET_KEY.search(str(key)):
                found.append(name)
            found += _secret_keys(item, f"{name}.")
    elif isinstance(value, list):
        for index, item in enumerate(value):
            found += _secret_keys(item, f"{prefix[:-1]}[{index}].")
    return found


def _resolve(value: Any, base: Path | None) -> Any:
    if not isinstance(value, str):
        return value  # wrong type: validation says so
    path = Path(value).expanduser()
    return path if base is None or path.is_absolute() else base / path


def _with_paths(raw: Mapping[str, Any], base: Path | None) -> dict[str, Any]:
    """`raw` with every path-valued key turned into a Path against `base`."""
    out = dict(raw)
    store = out.get("store")
    if isinstance(store, Mapping) and "path" in store:
        out["store"] = {**store, "path": _resolve(store["path"], base)}
    skills = out.get("skills")
    if isinstance(skills, Mapping) and isinstance(skills.get("roots"), list):
        roots = tuple(_resolve(item, base) for item in skills["roots"])
        out["skills"] = {**skills, "roots": roots}
    mcp = out.get("mcp")
    if isinstance(mcp, Mapping):
        mcp = dict(mcp)
        servers = mcp.get("servers")
        if isinstance(servers, Mapping):
            mcp["servers"] = {
                name: (
                    {**item, "tools_list": _resolve(item["tools_list"], base)}
                    if isinstance(item, Mapping) and "tools_list" in item
                    else item
                )
                for name, item in servers.items()
            }
        gateway = mcp.get("gateway")
        if isinstance(gateway, Mapping) and isinstance(gateway.get("routes"), list):
            mcp["gateway"] = {**gateway, "routes": tuple(gateway["routes"])}
        out["mcp"] = mcp
    return out


def _problems(exc: ValidationError) -> list[str]:
    problems = []
    for error in exc.errors():
        where = ".".join(str(part) for part in error["loc"]) or "config"
        message = str(error["msg"])
        if error["type"] == "extra_forbidden":
            message = "unknown key"
        problems.append(f"{where}: {message}")
    return problems


def starter_toml(
    *, store: Path = DEFAULT_STORE, origin: str = "vm-mon", roots: tuple[Path, ...] = ()
) -> str:
    """A first `cim.toml` for `cim init`: store, origin and skill roots, the rest commented.

    The text is checked with `parse_config` before it is returned, so `cim init` never writes
    a file the loader would refuse.
    """

    def quoted(value: object) -> str:
        return '"' + str(value).replace("\\", "\\\\").replace('"', '\\"') + '"'

    listed = ", ".join(quoted(root) for root in roots)
    text = f"""# cim.toml, written by `cim init`. Every key is optional (cim.example.toml has all).
# Precedence: command-line flag > environment variable > this file > default.
# Relative paths are taken from this file's folder. No secrets here: tokens stay in the
# environment (a gateway route names its variable with authorization_env).

[store]
path = {quoted(store.as_posix())}
origin = {quoted(origin)}

[skills]
roots = [{listed}]  # CIM_SKILL_ROOTS still overrides

# [mcp.servers.hexstrike]               # `cim inventory` / `cim sweep` read tools_list
# root = "/opt/mcp/hexstrike"
# tools_list = "corpora/mcp/tools_list.json"
# minimum_tools = 150
"""
    parse_config(tomllib.loads(text))
    return text
