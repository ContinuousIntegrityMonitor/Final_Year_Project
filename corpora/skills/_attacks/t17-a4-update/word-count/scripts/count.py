"""Print line, word and character counts for one text file, and the longest line (v2)."""

import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
lines = text.splitlines()
longest = max((len(line) for line in lines), default=0)
print(f"lines={len(lines)} words={len(text.split())} chars={len(text)} longest={longest}")
