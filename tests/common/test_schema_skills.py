"""Round-trip and contract tests for skills-side payload models (T-02)."""

from __future__ import annotations

from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from cim.common.schema.skills import (
    Egress,
    SkillArtefactPayload,
    SkillBehaviourPayload,
    SkillFile,
    SkillIntegrityPayload,
)

SHA_A = "a" * 64
SHA_B = "b" * 64

SAMPLES: list[BaseModel] = [
    SkillArtefactPayload(
        skill_id="pdf-tools",
        name="pdf-tools",
        description="Work with PDF files",
        root="/skills/pdf-tools",
        files=[SkillFile(path="SKILL.md", sha256=SHA_A, size_bytes=812)],
        tree_digest=SHA_B,
    ),
    SkillIntegrityPayload(
        skill_id="pdf-tools",
        change="modify",
        path="scripts/run.py",
        old_sha256=SHA_A,
        new_sha256=SHA_B,
    ),
    SkillBehaviourPayload(
        skill_id="pdf-tools",
        invocation_id="inv-0001",
        cgroup_id="cim-skill-pdf-tools-inv-0001.scope",
        binaries_executed=["/usr/bin/python3"],
        file_write_targets=["/tmp"],
        egress=[Egress(dest_class="private_ip", port=8080)],
        process_count=2,
        duration_us=1_250_000,
    ),
]


def contains_float(obj: Any) -> bool:
    """True if any value anywhere in a nested structure is a float."""
    if isinstance(obj, float):
        return True
    if isinstance(obj, dict):
        return any(contains_float(v) for v in obj.values())
    if isinstance(obj, list):
        return any(contains_float(v) for v in obj)
    return False


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_round_trip(sample: BaseModel) -> None:
    again = type(sample).model_validate_json(sample.model_dump_json())
    assert again == sample


@pytest.mark.parametrize("sample", SAMPLES, ids=lambda s: type(s).__name__)
def test_no_floats_in_payload(sample: BaseModel) -> None:
    assert not contains_float(sample.model_dump(mode="json"))


def test_float_rejected_for_integer_field() -> None:
    with pytest.raises(ValidationError):
        SkillFile(path="SKILL.md", sha256=SHA_A, size_bytes=1.5)  # type: ignore[arg-type]


def test_bad_digest_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillFile(path="SKILL.md", sha256="not-a-digest", size_bytes=1)


def test_unknown_field_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillIntegrityPayload.model_validate(
            {"skill_id": "x", "change": "create", "path": "a", "surprise": 1}
        )


def test_invalid_change_rejected() -> None:
    with pytest.raises(ValidationError):
        SkillIntegrityPayload.model_validate({"skill_id": "x", "change": "chmod", "path": "a"})
