"""MCP-side event payloads (T-02). Hashed payloads must contain no floats.

v1.1 (contract 1.1.0) only adds fields, each optional, so every v1.0 payload still validates.
"""

from __future__ import annotations

from typing import Any, Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

SHA256 = r"^[0-9a-f]{64}$"
# What the MCP envelope classes a string argument as (cim.mcp.envelope.value_classes).
ValueClass = Literal["private_ip", "public_ip", "domain", "path", "other"]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class McpToolDescriptor(_Strict):
    """One tool advertised by an MCP server (descriptor digest, not live args)."""

    name: str
    description: str
    input_schema_digest: str = Field(pattern=SHA256)
    # v1.1 (review D3): digest of the whole canonical tool object, so a change to `title`,
    # `annotations`, `outputSchema` or any other field changes the stored digest too.
    tool_digest: str | None = Field(default=None, pattern=SHA256)


class McpArtefactPayload(_Strict):
    """kind = 'artefact': baseline record for one MCP server or one tool."""

    # v1.1: tells the three MCP artefact shapes apart (baseline, session, pin).
    record: Literal["baseline"] = "baseline"
    server_id: str
    tool_id: str | None = None  # set only for artefact.type == mcp_tool
    name: str
    description: str
    root: str
    tools: list[McpToolDescriptor]
    manifest_digest: str = Field(pattern=SHA256)


class McpSessionPayload(_Strict):
    """kind = 'artefact', record = 'session': what one proxied session's `initialize` showed.

    v1.1 (Hamza's request, row 3). Lets C2 show which server build a session talked to.
    """

    record: Literal["session"]
    server_id: str
    session_id: str
    server_name: str
    server_version: str
    protocol_version: str
    capabilities_digest: str = Field(pattern=SHA256)


class McpPinPayload(_Strict):
    """kind = 'artefact', record = 'pin': the tools/list a server is compared with (T-12).

    v1.1 (review P4): the pin had no contract shape. `tools` holds the hashable tool objects
    as the server sent them, so any JSON value can appear inside.
    """

    record: Literal["pin"]
    code: Literal["mcp_pin"] = "mcp_pin"
    server_id: str
    name: str
    tools: list[dict[str, Any]]


class McpIntegrityPayload(_Strict):
    """kind = 'integrity': a change to a server install or tool descriptor."""

    server_id: str
    tool_id: str | None = None
    change: Literal["create", "modify", "delete", "rename"]
    path: str
    old_path: str | None = None  # rename only
    old_sha256: str | None = Field(default=None, pattern=SHA256)
    new_sha256: str | None = Field(default=None, pattern=SHA256)
    # v1.1 (review P4): what changed, in words, so `path` holds a path again.
    detail: str | None = None


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
    # v1.1, all optional (Hamza's request rows 1 and 2, as answered; T-16 scorer design 6):
    response_bytes: StrictInt | None = Field(default=None, ge=0)
    session_id: str | None = None
    seq: StrictInt | None = Field(default=None, ge=1)  # order inside the session, from 1
    argument_shape_digest: str | None = Field(default=None, pattern=SHA256)
    value_classes: list[ValueClass] | None = None  # sorted, no repeats

    @model_validator(mode="after")
    def _check_v11(self) -> Self:
        if (self.session_id is None) != (self.seq is None):
            raise ValueError("session_id and seq come together")
        if self.session_id is not None and self.invocation_id != f"{self.session_id}:{self.seq}":
            raise ValueError("invocation_id must be <session_id>:<seq> when both are set")
        if self.value_classes is not None and self.value_classes != sorted(set(self.value_classes)):
            raise ValueError("value_classes must be sorted, without repeats")
        return self
