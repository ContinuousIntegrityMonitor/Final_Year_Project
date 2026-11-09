"""Read-only December status board.

Shows the hash chain, pinned tools, schema changes, recent calls, and
call-pattern warm-up for one baseline store. The April review screen
(trust scores, quarantine, attestation) stays T-34.
"""

from cim.dashboard.board import Board, load_board
from cim.dashboard.page import render_page

__all__ = ["Board", "load_board", "render_page"]
