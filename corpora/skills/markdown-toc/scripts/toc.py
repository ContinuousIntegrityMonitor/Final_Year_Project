"""Print an indented table of contents from Markdown headings."""

import sys
from pathlib import Path

for line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    if line.startswith("#"):
        level = len(line) - len(line.lstrip("#"))
        print("  " * (level - 1) + "- " + line.lstrip("#").strip())
