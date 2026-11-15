"""Print line, word and character counts for one text file."""

import sys
from pathlib import Path

text = Path(sys.argv[1]).read_text(encoding="utf-8")
print(f"lines={len(text.splitlines())} words={len(text.split())} chars={len(text)}")
