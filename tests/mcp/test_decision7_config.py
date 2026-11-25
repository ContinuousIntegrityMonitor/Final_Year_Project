"""T-13 decision 7: proxy/gateway --config, session file, gateway heartbeat."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from typer.testing import CliRunner

from cim.cli import app
from cim.mcp.cli import resolve_proxy_config
from cim.mcp.http_gateway import load_gateway_config, looks_like_cim_toml
from cim.mcp.runtime import (
    HeartbeatThread,
    clear_session,
    heartbeat_path,
    proxy_session,
    session_path,
    touch_heartbeat,
)

runner = CliRunner()


def _toml(tmp_path: Path, text: str) -> Path:
    path = tmp_path / "cim.toml"
    path.write_text(text, encoding="utf-8")
    return path


def test_resolve_proxy_config_reads_server_table(tmp_path: Path) -> None:
    cfg = _toml(
        tmp_path,
        '[store]\npath = "logs/from-toml.sqlite"\norigin = "lab"\n'
        '[mcp.servers.hexstrike]\nroot = "/opt/hex"\norigin = "vm-mon"\n',
    )
    env: dict[str, str] = {}
    got = resolve_proxy_config(config_path=cfg, server="hexstrike", env=env)
    assert got.server_id == "hexstrike"
    assert got.root == "/opt/hex"
    assert got.origin == "vm-mon"
    assert got.db == tmp_path / "logs" / "from-toml.sqlite"


def test_resolve_proxy_env_beats_file(tmp_path: Path) -> None:
    cfg = _toml(
        tmp_path,
        '[store]\npath = "logs/from-toml.sqlite"\n[mcp.servers.hexstrike]\nroot = "/opt/hex"\n',
    )
    env = {
        "CIM_PROXY_DB": str(tmp_path / "env.sqlite"),
        "CIM_PROXY_ROOT": "/from-env",
        "CIM_PROXY_ORIGIN": "env-origin",
        "CIM_PROXY_SERVER_ID": "hexstrike",
    }
    got = resolve_proxy_config(config_path=cfg, env=env)
    assert got.db == tmp_path / "env.sqlite"
    assert got.root == "/from-env"
    assert got.origin == "env-origin"


def test_resolve_proxy_db_flag_wins(tmp_path: Path) -> None:
    cfg = _toml(tmp_path, '[store]\npath = "logs/from-toml.sqlite"\n')
    flag = tmp_path / "flag.sqlite"
    got = resolve_proxy_config(config_path=cfg, db=flag, env={})
    assert got.db == flag


def test_looks_like_cim_toml(tmp_path: Path) -> None:
    toml = _toml(tmp_path, '[mcp.gateway]\nhost = "127.0.0.1"\n')
    assert looks_like_cim_toml(toml)
    json_path = tmp_path / "routes.json"
    json_path.write_text('{"routes":[{"id":"a","upstream":"http://x/"}]}', encoding="utf-8")
    assert looks_like_cim_toml(json_path) is False


def test_load_gateway_from_cim_toml(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CIM_HTTP_GATEWAY_TOKEN", raising=False)
    cfg = _toml(
        tmp_path,
        '[store]\npath = "gw.sqlite"\n'
        '[mcp.gateway]\nhost = "127.0.0.1"\nport = 9999\n'
        '[[mcp.gateway.routes]]\nid = "demo"\n'
        'upstream = "http://127.0.0.1:8000/mcp/"\n',
    )
    loaded = load_gateway_config(cfg)
    assert loaded.port == 9999
    assert loaded.db == tmp_path / "gw.sqlite"
    assert loaded.routes[0].id == "demo"
    assert loaded.routes[0].root == "cursor-demo"
    assert loaded.heartbeat_s == 10


def test_load_gateway_json_still_works(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("CIM_HTTP_GATEWAY_TOKEN", raising=False)
    path = tmp_path / "routes.json"
    path.write_text(
        json.dumps(
            {
                "db": str(tmp_path / "j.sqlite"),
                "port": 8878,
                "routes": [{"id": "g", "upstream": "http://127.0.0.1:9/"}],
            }
        ),
        encoding="utf-8",
    )
    loaded = load_gateway_config(path)
    assert loaded.port == 8878
    assert loaded.routes[0].id == "g"


def test_proxy_session_file_lifecycle(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    with proxy_session(db, server_id="hexstrike", command=["echo", "hi"]) as path:
        assert path.is_file()
        body = json.loads(path.read_text(encoding="utf-8"))
        assert body["server_id"] == "hexstrike"
        assert body["command"] == ["echo", "hi"]
        assert path == session_path(db, "proxy", os.getpid())
    assert not path.exists()


def test_heartbeat_thread_writes_and_clears(tmp_path: Path) -> None:
    db = tmp_path / "store.sqlite"
    thread = HeartbeatThread(db, "http-gateway", interval_s=0.5)
    thread.start()
    deadline = time.time() + 2
    path = heartbeat_path(db, "http-gateway")
    while time.time() < deadline and not path.is_file():
        time.sleep(0.05)
    assert path.is_file()
    thread.stop()
    thread.join(timeout=2)
    assert not path.exists()


def test_cli_proxy_help_mentions_config_and_server() -> None:
    # Wide COLUMNS: rich help on CI otherwise truncates the Options block.
    result = runner.invoke(
        app, ["proxy", "--help"], env={**os.environ, "COLUMNS": "120", "NO_COLOR": "1"}
    )
    assert result.exit_code == 0
    text = result.stdout + result.stderr
    assert "--config" in text
    assert "--server" in text


def test_cli_http_gateway_rejects_toml_without_gateway(tmp_path: Path) -> None:
    cfg = _toml(tmp_path, '[store]\npath = "x.sqlite"\n')
    result = runner.invoke(app, ["http-gateway", "--config", str(cfg)])
    assert result.exit_code == 2
    assert "[mcp.gateway]" in result.stderr


def test_touch_heartbeat_creates_run_dir(tmp_path: Path) -> None:
    db = tmp_path / "s.sqlite"
    path = touch_heartbeat(db, "http-gateway")
    assert path.is_file()
    clear_session(db, "proxy")  # no-op when missing
