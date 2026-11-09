# 2026-11-09 — status board and HexStrike tool list

- `cim dashboard` is the local status page. The home page shows four numbers: tools, calls, changes, and whether a new pattern appeared. The full list is behind "See the list".
- A line is drawn when a tool is used. The same tool stacks on the same shape. A change draws a red line and the page says "Something new showed up."
- Pinned HexStrike commit `d689933` was checked out on the dev PC. `tools/list` returned 150 tools and is saved in `corpora/mcp/tools_list.json`. Schemas with decimal defaults are stored by turning those numbers into strings before the digest, because the hash chain cannot hold floats. No scan was run. A tool call on VM-MON is still open.
- Fasih has not reviewed org PR #1. The next build is the behaviour alert, T-16.
