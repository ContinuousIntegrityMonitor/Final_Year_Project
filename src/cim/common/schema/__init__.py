"""Versioned event schema contract (T-02; owned by Fasih)."""

# Written into every event. Changes when the shape of an event changes.
SCHEMA_VERSION = 1

# Revision of the validation rules for that shape.
# 1.0.1: canonical JSON rejects strings that are not valid Unicode text; an artefact may only
#        carry the identifiers of its own type; a timestamp must be a real date and time.
CONTRACT_VERSION = "1.0.1"
