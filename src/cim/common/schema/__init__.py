"""Versioned event schema contract (T-02; owned by Fasih)."""

# Written into every event. Changes when the shape of an event changes.
SCHEMA_VERSION = 1

# Revision of the validation rules for that shape.
# 1.0.1: canonical JSON rejects strings that are not valid Unicode text; an artefact may only
#        carry the identifiers of its own type; a timestamp must be a real date and time.
# 1.1.0: fields and payloads added, all optional for existing writers (docs/CONTRACT_V1_1.md):
#        MCP behaviour response_bytes, session_id + seq, argument_shape_digest, value_classes;
#        MCP artefact `record` (baseline, session, pin) with McpSessionPayload and McpPinPayload;
#        MCP integrity `detail`; tool descriptor `tool_digest`; alert payloads validated by code;
#        artefact type `monitor`. Every 1.0 payload still validates, so SCHEMA_VERSION stays 1.
CONTRACT_VERSION = "1.1.0"
