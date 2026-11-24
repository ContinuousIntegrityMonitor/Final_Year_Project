"""Alert payloads (contract 1.1.0). Before v1.1, kind = 'alert' was not validated at all.

Every alert carries `code` (what was found) and `reason` (why), so each side can add codes
without changing how alerts are read. Codes not listed in `ALERT_PAYLOADS` still need a
string `code`; the rest of such a payload is not checked yet.
"""

from __future__ import annotations

from typing import Literal, Self

from pydantic import BaseModel, ConfigDict, Field, StrictInt, model_validator

SHA256 = r"^[0-9a-f]{64}$"


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class ProxyAlertPayload(_Strict):
    """A frame the proxy or gateway could not parse or record (T-09; Hamza's request, row 4).

    `direction`, `sha256` and `size` describe a frame; `stage`, `event` and `detail` describe
    a capture or store failure. Which are set depends on the code and stage.
    """

    code: Literal["proxy_malformed_frame", "proxy_capture_failed"]
    reason: str
    direction: Literal["client_to_server", "server_to_client"] | None = None
    sha256: str | None = Field(default=None, pattern=SHA256)
    size: StrictInt | None = Field(default=None, ge=0)
    stage: Literal["capture", "store", "score"] | None = None
    event: str | None = None
    detail: str | None = None


class DriftFeature(_Strict):
    """One drifted feature in a behaviour alert (docs/T16_SHARED_SCORER_DESIGN.md, section 2)."""

    feature: str
    how: Literal["never_seen", "z"]
    values: list[str]
    score_milli: StrictInt = Field(ge=0)  # thousandths of a standard deviation; never a float
    threshold_milli: StrictInt = Field(ge=0)


class BehaviourAlertPayload(_Strict):
    """A run or call that left the learned pattern (T-16, both sides).

    An MCP alert names `server_id` and `tool_id`; a skills alert names `skill_id`; never both.
    """

    code: Literal["mcp_behaviour_drift", "skill_behaviour_drift"]
    reason: Literal["behaviour_drift"] = "behaviour_drift"
    server_id: str | None = None
    tool_id: str | None = None
    skill_id: str | None = None
    observation_record_id: StrictInt = Field(ge=1)  # the behaviour record this alert judged
    composite_milli: StrictInt = Field(ge=0)
    features: list[DriftFeature] = Field(min_length=1, max_length=3)
    window: StrictInt = Field(ge=1)
    scorer_version: StrictInt = Field(ge=1)
    detail: str
    input_change: str | None = None  # MCP page text
    output_change: str | None = None

    @model_validator(mode="after")
    def _check_side(self) -> Self:
        if self.code == "mcp_behaviour_drift":
            if self.server_id is None or self.tool_id is None or self.skill_id is not None:
                raise ValueError("an MCP behaviour alert names server_id and tool_id only")
        elif self.skill_id is None or self.server_id is not None or self.tool_id is not None:
            raise ValueError("a skills behaviour alert names skill_id only")
        return self


class MonitorAlertPayload(_Strict):
    """The watchdog restarted a collector, or gave up on it (T-13 design, section 6)."""

    code: Literal["collector_restarted", "collector_failed"]
    reason: Literal["exited", "hung", "gave_up"]
    component: str  # for example "skills-watcher", "http-gateway"
    exit_code: StrictInt | None = None
    gap_s: StrictInt = Field(ge=0)  # how long it was not running
    restarts: StrictInt = Field(ge=0)


ALERT_PAYLOADS: dict[str, type[BaseModel]] = {
    "proxy_malformed_frame": ProxyAlertPayload,
    "proxy_capture_failed": ProxyAlertPayload,
    "mcp_behaviour_drift": BehaviourAlertPayload,
    "skill_behaviour_drift": BehaviourAlertPayload,
    "collector_restarted": MonitorAlertPayload,
    "collector_failed": MonitorAlertPayload,
}
