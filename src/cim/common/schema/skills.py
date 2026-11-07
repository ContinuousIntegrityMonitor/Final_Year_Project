"""Skills-side event payloads (T-02). Hashed payloads must contain no floats."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictInt

SHA256 = r"^[0-9a-f]{64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class SkillFile(_Strict):
    path: str  # relative to the skill root
    sha256: str = Field(pattern=SHA256)
    size_bytes: StrictInt = Field(ge=0)


class SkillArtefactPayload(_Strict):
    """kind = 'artefact': baseline record for one installed skill."""

    skill_id: str
    name: str  # SKILL.md frontmatter
    description: str  # SKILL.md frontmatter
    root: str
    files: list[SkillFile]  # SKILL.md + every helper script
    tree_digest: str = Field(pattern=SHA256)


class SkillIntegrityPayload(_Strict):
    """kind = 'integrity': a change under a skill root."""

    skill_id: str
    change: Literal["create", "modify", "delete", "rename"]
    path: str
    old_path: str | None = None  # rename only
    old_sha256: str | None = Field(default=None, pattern=SHA256)
    new_sha256: str | None = Field(default=None, pattern=SHA256)


class Egress(_Strict):
    dest_class: Literal["private_ip", "public_ip", "domain", "unix_socket"]
    port: StrictInt = Field(ge=0, le=65535)


class SkillBehaviourPayload(_Strict):
    """kind = 'behaviour': what one invocation did, attributed via its cgroup."""

    skill_id: str
    invocation_id: str
    cgroup_id: str
    binaries_executed: list[str]
    file_write_targets: list[str]  # path roots, not full paths
    egress: list[Egress]
    process_count: StrictInt = Field(ge=0)
    duration_us: StrictInt = Field(ge=0)  # integer microseconds, never float seconds
