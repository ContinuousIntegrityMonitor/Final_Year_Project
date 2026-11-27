"""Record and render the T-18 skills beat as an MP4 (called by record_skills_beat.sh).

`record`: runs a command in a 120x42 pseudo-terminal and keeps its output with timings
(`typescript` + `timing`, the classic format of util-linux `script`, which Fedora does not
install by default). `render`: turns that into the video.

Input, in --work: `typescript` + `timing` from util-linux `script` (classic timing format), with
invisible markers `ESC ] 777 ; cim:<what> BEL` written by the driver, and dashboard screenshots
in `shots/`. Output: a 1920x1080 H.264 video with caption cards before each step, a caption
strip under the terminal, and the dashboard's Skills panel after the steps that change it.

Needs pyte and pillow (the recorder runs it with `uv run --with pyte --with pillow`), ffmpeg,
and the Noto Sans Mono / Noto Sans fonts. Times: real, except that idle gaps are cut to
MAX_IDLE_S and each step's last screen is held so it can be read.
"""

from __future__ import annotations

import argparse
import codecs
import fcntl
import json
import os
import pty
import re
import select
import shutil
import struct
import subprocess
import sys
import termios
import time
from dataclasses import dataclass
from pathlib import Path

import pyte  # type: ignore[import-not-found]
from PIL import Image, ImageDraw, ImageFont

W, H = 1920, 1080
COLS, ROWS = 120, 42
FPS_SAMPLE = 0.1  # one frame per 0.1 s of recording at most
MAX_IDLE_S = 2.0
MONO = "/usr/share/fonts/google-noto-vf/NotoSansMono[wght].ttf"
SANS = "/usr/share/fonts/google-noto-vf/NotoSans[wght].ttf"
BG, FG, DIM, ACCENT = "#0f1419", "#d8dee9", "#7b8794", "#5fb3d9"
PALETTE = {
    "black": "#3b4252",
    "red": "#e06c75",
    "green": "#98c379",
    "brown": "#e5c07b",
    "yellow": "#e5c07b",
    "blue": "#61afef",
    "magenta": "#c678dd",
    "cyan": "#56b6c2",
    "white": "#e5e9f0",
    "default": FG,
}
MARKER = re.compile(r"\x1b\]777;cim:([^\x07]*)\x07")

STEPS = {
    "inventory": (
        "C1",
        "Inventory",
        [
            "cim inventory baselines every installed skill: a hash of each file",
            "and of the whole tree, in the append-only, hash-chained store.",
            "None has run yet, so every skill is 'learning, 0 of 30', never 'healthy'.",
        ],
    ),
    "watch": (
        "setup",
        "The monitor",
        [
            "cim watch supervises the skills watcher: if it dies it is restarted,",
            "and the restart is recorded.",
        ],
    ),
    "warmup": (
        "C2-style capture",
        "Warm-up, sped up",
        [
            "An agent harness calls cim skills exec instead of running the helper itself.",
            "Each run is traced in its own cgroup scope (strace): what it executed,",
            "wrote and connected to is recorded. 30 runs each of two skills.",
        ],
    ),
    "tamper": (
        "integrity",
        "A skill's file is edited",
        [
            "One line is appended to an installed helper.",
            "The watcher records the change within a second.",
        ],
    ),
    "a3": (
        "C4, skills side",
        "T-17 A3: trigger payload",
        [
            "meeting-brief reads notes that mention 'quarterly' and sends the NAMES of",
            "its environment variables to the lab listener. The skill's files do not change:",
            "the hashes are shown before and after. The behaviour alert names the",
            "drifted feature: a destination never seen during warm-up.",
        ],
    ),
    "a4": (
        "false-positive control",
        "T-17 A4: a legitimate update",
        [
            "word-count is updated (it now also reports the longest line).",
            "The update is recorded as two file changes; its behaviour is the same,",
            "so the scorer raises no alert.",
        ],
    ),
    "status": (
        "C5",
        "Status and the chain",
        [
            "cim status: what is installed, what changed, what behaved differently.",
            "cim verify-chain: the store's hash chain verifies.",
        ],
    ),
}
ORDER = list(STEPS)


@dataclass
class Clip:
    image: Image.Image
    seconds: float


def font(path: str, size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    face = ImageFont.truetype(path, size)
    try:
        face.set_variation_by_name("Bold" if bold else "Regular")
    except (OSError, ValueError):
        pass
    return face


MONO_R, MONO_B = font(MONO, 20), font(MONO, 20, bold=True)
CELL_W = round(MONO_R.getlength("M"))
CELL_H = 24
TERM_X = (W - COLS * CELL_W) // 2
STRIP_Y = ROWS * CELL_H + 8


def color(name: str, default: str) -> str:
    if name == "default":
        return default
    if re.fullmatch(r"[0-9a-fA-F]{6}", name):
        return "#" + name
    return PALETTE.get(name, default)


def strip(draw: ImageDraw.ImageDraw, left: str, right: str) -> None:
    draw.rectangle((0, STRIP_Y, W, H), fill="#161d24")
    draw.text((40, STRIP_Y + 18), left, font=font(SANS, 26, bold=True), fill=FG)
    small = font(SANS, 22)
    draw.text(
        (W - 40 - draw.textlength(right, font=small), STRIP_Y + 22), right, font=small, fill=DIM
    )


def terminal(screen: pyte.Screen, caption: str) -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    for y in range(ROWS):
        line = screen.buffer[y]
        x = 0
        while x < COLS:
            char = line[x]
            style = (char.fg, char.bg, char.bold, char.reverse)
            run = ""
            while x < COLS and (line[x].fg, line[x].bg, line[x].bold, line[x].reverse) == style:
                run += line[x].data
                x += 1
            fg, bg = color(style[0], FG), color(style[1], BG)
            if style[3]:
                fg, bg = bg, fg
            left = TERM_X + (x - len(run)) * CELL_W
            if bg != BG:
                draw.rectangle(
                    (left, y * CELL_H, left + len(run) * CELL_W, (y + 1) * CELL_H), fill=bg
                )
            if run.strip():
                draw.text((left, y * CELL_H + 2), run, font=MONO_B if style[2] else MONO_R, fill=fg)
    strip(draw, caption, "VM-MON (lab) · 2026-11-27 · T-18 skills beat, backup video")
    return image


def card(title: str, kicker: str, lines: list[str], footer: str = "") -> Image.Image:
    image = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(image)
    draw.text((160, 300), kicker.upper(), font=font(SANS, 30, bold=True), fill=ACCENT)
    draw.text((160, 350), title, font=font(SANS, 72, bold=True), fill=FG)
    body = font(SANS, 34)
    for i, line in enumerate(lines):
        draw.text((160, 480 + i * 52), line, font=body, fill=FG)
    if footer:
        draw.text((160, 960), footer, font=font(SANS, 24), fill=DIM)
    return image


def border_run(image: Image.Image, x: int, start: int = 0) -> tuple[int, int]:
    """The longest vertical run of 1-px border pixels in column x, from row `start` down."""
    pixels = image.load()

    def line(y: int) -> bool:
        here, left, right = (sum(pixels[i, y]) / 3 for i in (x, x - 1, x + 1))
        return abs(here - left) > 6 and abs(here - right) > 6

    best, run_start = (0, 0), None
    for y in range(start, image.height):
        if line(y):
            run_start = y if run_start is None else run_start
        elif run_start is not None:
            if y - run_start > best[1] - best[0]:
                best = (run_start, y)
            run_start = None
    return best


SHOT_NOTES = {
    "inventory": "All 15 installed skills are listed; each is 'learning, 0 of 30': none has run.",
    "warmup": "meeting-brief and word-count have 30 traced runs each: warmed up, 'healthy'.",
    "a3": "meeting-brief: warning, from the A3 alert; its files are unchanged. "
    "markdown-toc: warning, for the file edited in step 4.",
    "status": "Three skills in warning: markdown-toc (edited file), meeting-brief (A3 alert), "
    "word-count (the A4 update, a file change; no behaviour alert).",
}


def dividers(panel: Image.Image) -> list[int]:
    """Rows of `panel` that are the 1-px lines between its skill rows."""
    pixels = panel.load()
    found = []
    for y in range(1, panel.height - 1):
        hits = sum(
            1
            for x in range(30, panel.width - 30, 10)
            if abs(sum(pixels[x, y]) - sum(pixels[x, y - 1])) > 18
            and abs(sum(pixels[x, y]) - sum(pixels[x, y + 1])) > 18
        )
        if hits > (panel.width - 60) // 10 * 0.8:
            found.append(y)
    return found


def dashboard(shot: Path, name: str) -> Image.Image:
    """The dashboard's Skills panel, cut from a 1600-px-wide screenshot, in two columns.

    Only the Skills panel is shown: the page's summary card counts MCP alerts only, so on this
    skills-only store its Alerts tile reads 0 even after A3 (reported to Hamza).
    """
    page = Image.open(shot).convert("RGB")
    top, bottom = border_run(page, 807)
    panel = page.crop((808, top, 1355, bottom))
    lines = dividers(panel)
    first, middle = lines[0], min(lines, key=lambda y: abs(y - (lines[0] + panel.height) / 2))
    header = panel.crop((0, 0, panel.width, first - 52))  # title and summary line
    left = panel.crop((0, first - 52, panel.width, middle))
    right = panel.crop((0, middle, panel.width, panel.height))
    room = H - 110 - 130  # below the title, above the caption strip
    scale = min(1.55, room / (header.height + max(left.height, right.height)))

    def big(part: Image.Image) -> Image.Image:
        return part.resize((round(part.width * scale), round(part.height * scale)), Image.LANCZOS)

    header, left, right = big(header), big(left), big(right)
    image = Image.new("RGB", (W, H), "#11161c")
    draw = ImageDraw.Draw(image)
    title = f"Dashboard on VM-MON, after step {ORDER.index(name) + 1}: {STEPS[name][1]}"
    draw.text((60, 20), title, font=font(SANS, 34, bold=True), fill=FG)
    draw.text(
        (60, 66),
        "cim dashboard, opened on the laptop through an SSH tunnel: its Skills panel, "
        "shown in two columns",
        font=font(SANS, 22),
        fill=DIM,
    )
    x0 = (W - 2 * left.width - 40) // 2
    image.paste(header, (x0, 110))
    image.paste(left, (x0, 110 + header.height))
    image.paste(right, (x0 + left.width + 40, 110 + header.height))
    draw.rectangle((0, H - 120, W, H), fill="#161d24")
    note = SHOT_NOTES.get(name, "")
    words, rows, row = note.split(), [], ""
    body = font(SANS, 26)
    for word in words:
        trial = f"{row} {word}".strip()
        if draw.textlength(trial, font=body) > W - 120:
            rows.append(row)
            row = word
        else:
            row = trial
    rows.append(row)
    for i, text in enumerate(rows[:2]):
        draw.text((60, H - 106 + i * 36), text, font=body, fill=FG)
    data = shot.with_suffix(".json")
    if data.exists() and data.stat().st_size:
        summary = json.loads(data.read_text())["skills"]["summary"]
        numbers = (
            f"/api/board: {summary['skills']} skills, {summary['warning']} warning, "
            f"{summary['runs']} runs, {summary['alerts']} skills alert(s)"
        )
        small = font(SANS, 20)
        draw.text(
            (W - 60 - draw.textlength(numbers, font=small), 74), numbers, font=small, fill=ACCENT
        )
    return image


def chunks(work: Path) -> list[tuple[float, str]]:
    raw = (work / "typescript").read_bytes()
    if raw.startswith(b"Script started"):
        raw = raw[raw.index(b"\n") + 1 :]
    out, at, offset = [], 0.0, 0
    decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
    for row in (work / "timing").read_text().split("\n"):
        if not row.strip():
            continue
        delay, size = row.split()[:2]
        at += float(delay)
        out.append((at, decoder.decode(raw[offset : offset + int(size)])))
        offset += int(size)
    return out


def checks(work: Path) -> str:
    """How many OK and FAIL lines the demo script printed in the recording."""
    text = re.sub(r"\x1b\[[0-9;]*m", "", (work / "typescript").read_text(errors="replace"))
    ok = len(re.findall(r"^\s+OK ", text, re.MULTILINE))
    failed = len(re.findall(r"^\s+FAIL ", text, re.MULTILINE))
    return f"{ok} OK, {failed} FAIL"


def render(work: Path) -> list[Clip]:
    screen = pyte.Screen(COLS, ROWS)
    stream = pyte.Stream(screen)
    clips: list[Clip] = []
    step = ""
    last_frame_at: float | None = None

    def caption() -> str:
        if not step:
            return ""
        kicker, title, _ = STEPS[step]
        return f"Step {ORDER.index(step) + 1} of {len(ORDER)}: {title}  ·  {kicker}"

    def frame(at: float) -> None:
        nonlocal last_frame_at
        if not any(row.strip() for row in screen.display):
            return  # a cleared screen between steps: no blank flash
        if last_frame_at is not None and clips:
            clips[-1].seconds = min(max(at - last_frame_at, 0.04), MAX_IDLE_S)
        clips.append(Clip(terminal(screen, caption()), 0.04))
        last_frame_at = at

    for at, text in chunks(work):
        pieces = MARKER.split(text)
        for i, piece in enumerate(pieces):
            if i % 2 == 0:
                if piece:
                    stream.feed(piece)
                    if last_frame_at is None or at - last_frame_at >= FPS_SAMPLE:
                        frame(at)
                continue
            kind, _, name = piece.partition(":")
            if last_frame_at is not None and clips:  # close the running frame
                frame(at)
                clips[-1].seconds = 0.04
            if kind == "start":
                clips.append(
                    Clip(
                        card(
                            "CIM: the skills beat",
                            "T-18 December demo · backup video (C6)",
                            [
                                "Continuous Integrity Monitor, skills side, on the lab VM-MON.",
                                "Recorded live from the demo script; no sound. Each step is",
                                "introduced by a card; the strip at the bottom names the step.",
                            ],
                            "scripts/demo_skills_beat.sh · runbook docs/demo/T18_skills_beat.md",
                        ),
                        7.0,
                    )
                )
            elif kind == "step":
                step = name
                kicker, title, lines = STEPS[name]
                clips.append(
                    Clip(
                        card(
                            title,
                            f"Step {ORDER.index(name) + 1} of {len(ORDER)}  ·  {kicker}",
                            lines,
                        ),
                        3.0 + 1.3 * len(lines),
                    )
                )
                last_frame_at = None
            elif kind == "end":
                frame(at)
                lines = sum(1 for row in screen.display if row.strip())
                clips[-1].seconds = 3.0 + 0.15 * lines
                last_frame_at = None
            elif kind == "shot":
                path = work / "shots" / f"{name}.png"
                if path.exists():
                    clips.append(Clip(dashboard(path, name), 8.0))
            elif kind == "stop":
                clips.append(
                    Clip(
                        card(
                            "End of the skills beat",
                            "summary",
                            [
                                "15 skills inventoried; 60 traced runs; one file edit caught;",
                                "A3 alert with the skill's hashes unchanged; A4 update, no alert;",
                                "cim status and verify-chain.",
                                f"Checks printed in this recording: {checks(work)}.",
                            ],
                            "Not in this video: Hamza's MCP beats (HexStrike).",
                        ),
                        6.0,
                    )
                )
    return clips


def encode(clips: list[Clip], out: Path, work: Path) -> None:
    frames = work / "frames"
    shutil.rmtree(frames, ignore_errors=True)
    frames.mkdir()
    listing = []
    for i, clip in enumerate(clips):
        path = frames / f"{i:05d}.png"
        clip.image.save(path)
        listing.append(f"file '{path}'\nduration {clip.seconds:.3f}")
    listing.append(f"file '{frames / f'{len(clips) - 1:05d}.png'}'")
    (work / "frames.txt").write_text("\n".join(listing) + "\n")
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-loglevel",
            "error",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(work / "frames.txt"),
            "-vf",
            "fps=25,format=yuv420p",
            "-c:v",
            "libopenh264",
            "-b:v",
            "3M",
            "-movflags",
            "+faststart",
            str(out),
        ],
        check=True,
    )


def record(work: Path, command: list[str]) -> int:
    """Run `command` in a COLS x ROWS pseudo-terminal; keep its output with timings."""
    pid, fd = pty.fork()
    if pid == 0:  # the child: the command, on the terminal's slave side
        os.execvp(command[0], command)
    fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack("HHHH", ROWS, COLS, 0, 0))
    last = time.monotonic()
    with (work / "typescript").open("wb") as out, (work / "timing").open("w") as timing:
        while True:
            ready, _, _ = select.select([fd], [], [], 1.0)
            if not ready:
                continue
            try:
                data = os.read(fd, 65536)
            except OSError:  # the command has ended and the terminal is closed
                break
            if not data:
                break
            now = time.monotonic()
            out.write(data)
            timing.write(f"{now - last:.6f} {len(data)}\n")
            last = now
            sys.stdout.buffer.write(data)  # also show it while it runs
            sys.stdout.buffer.flush()
    return os.waitstatus_to_exitcode(os.waitpid(pid, 0)[1])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("action", choices=("record", "render"))
    parser.add_argument("--work", type=Path, required=True, help="recording folder")
    parser.add_argument("--out", type=Path, help="render: the .mp4 to write")
    parser.add_argument("command", nargs="*", help="record: the command to run, after --")
    args = parser.parse_args()
    if args.action == "record":
        raise SystemExit(record(args.work, args.command))
    if args.out is None:
        parser.error("render needs --out")
    clips = render(args.work)
    encode(clips, args.out, args.work)
    total = sum(clip.seconds for clip in clips)
    print(f"render: {len(clips)} frames, {total:.0f} s -> {args.out}")


if __name__ == "__main__":
    main()
