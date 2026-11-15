"""Pretty-print one JSON document with sorted keys."""

import json
import sys
from pathlib import Path

document = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
print(json.dumps(document, indent=2, sort_keys=True))
