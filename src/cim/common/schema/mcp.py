"""MCP-side event payloads (T-02). Hashed payloads must contain no floats."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

SHA256 = r"^[0-9a-f]{64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class McpToolDescriptor(_Strict):
    """One tool advertised by an MCP server (descriptor digest, not live args)."""

    name: str
    description: str
    input_schema_digest: str = Field(pattern=SHA256)


class McpArtefactPayload(_Strict):
    """kind = 'artefact': baseline record for one MCP server or one tool."""

    server_id: str
    tool_id: str | None = None  # set only for artefact.type == mcp_tool
    name: str
    description: str
    root: str
    tools: list[McpToolDescriptor]
    manifest_digest: str = Field(pattern=SHA256)


class McpIntegrityPayload(_Strict):
    """kind = 'integrity': a change to a server install or tool descriptor."""

    server_id: str
    tool_id: str | None = None
    change: Literal["create", "modify", "delete", "rename"]
    path: str
    old_path: str | None = None  # rename only
    old_sha256: str | None = Field(default=None, pattern=SHA256)
    new_sha256: str | None = Field(default=None, pattern=SHA256)


class McpEgress(_Strict):
    dest_class: Literal["private_ip", "public_ip", "domain", "unix_socket"]
    port: StrictInt = Field(ge=0, le=65535)


class McpBehaviourPayload(_Strict):
    """kind = 'behaviour': one MCP tool invocation observed on the host."""

    server_id: str
    tool_id: str
    invocation_id: str
    request_digest: str = Field(pattern=SHA256)
    response_digest: str | None = Field(default=None, pattern=SHA256)
    binaries_executed: list[str]
    file_write_targets: list[str]
    egress: list[McpEgress]
    process_count: StrictInt = Field(ge=0)
    duration_us: StrictInt = Field(ge=0)
    outcome: Literal["ok", "error", "timeout"]
