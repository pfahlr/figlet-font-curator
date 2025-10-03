#!/usr/bin/env python3
"""
Figlet Font Browser (Textual TUI)

Changes in this version
- REMOVED interactive .flc picker; use --flc <path/to/file.flc>
- Keeps recursive scan for .flf/.tlf fonts; optional TOIlet support for .tlf
- Live preview, filtering, width changes, save current/all outputs

Dependencies
  pip install textual rich

Usage
  python figlet_font_browser_tui.py \
    --font-dir ~/figlet-fonts \
    --text "Hello World" \
    --width 80 \
    --out-dir ./out \
    --out-prefix run_ \
    [--flc ./charmaps/latin1.flc] \
    [--use-toilet]

Notes
- We shell out to the system figlet to preserve support for -C with .flc files.
- If toilet is enabled and present, .tlf fonts are previewed with toilet; otherwise we try figlet (and show errors if it fails).
- Indentation uses 2 spaces to match requested style.
"""
from __future__ import annotations

import argparse
import asyncio
import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional, Tuple

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import Footer, Header, Input, Label, ListItem, ListView, Log
from rich.text import Text

FIGLET_DEFAULT = shutil.which("figlet") or "/usr/bin/figlet"
TOILET_DEFAULT = shutil.which("toilet") or "/usr/bin/toilet"


@dataclass
class Config:
  font_dir: Path
  text: str
  width: int
  out_dir: Optional[Path]
  out_prefix: str
  use_toilet: bool
  flc: Optional[Path]


@dataclass
class FontEntry:
  path: Path  # full path to .flf or .tlf
  kind: str   # "flf" or "tlf"

  @property
  def font_dir(self) -> Path:
    return self.path.parent

  @property
  def base_name(self) -> str:
    return self.path.stem


# -------------------------
# Utility functions
# -------------------------

ALLOWED_EXTS = {
  ".flf": "flf",
  ".tlf": "tlf",
}


def scan_fonts(base: Path) -> List[FontEntry]:
  fonts: List[FontEntry] = []
  for p in base.rglob("*"):
    if not p.is_file():
      continue
    kind = ALLOWED_EXTS.get(p.suffix.lower())
    if kind is None:
      continue
    fonts.append(FontEntry(p, kind))

  fonts.sort(key=lambda f: str(f.path).lower())
  return fonts


async def run_figlet(
  text: str,
  width: int,
  font: FontEntry,
  charmap: Optional[Path],
  use_toilet: bool,
) -> Tuple[int, str, str]:
  """Run figlet (or toilet) and return (exit_code, stdout, stderr)."""
  # Prefer toilet for .tlf when enabled and present (note: toilet lacks -C support)
  if font.kind == "tlf" and use_toilet and (shutil.which("toilet") or Path(TOILET_DEFAULT).exists()):
    toilet_cmd = shutil.which("toilet") or TOILET_DEFAULT
    cmd = [toilet_cmd, "-f", str(font.path), "-w", str(width), text]
  else:
    figlet_cmd = shutil.which("figlet") or FIGLET_DEFAULT
    cmd = [figlet_cmd, "-d", str(font.font_dir), "-w", str(width), "-f", font.base_name]
    if charmap is not None:
      cmd.extend(["-C", str(charmap)])
    cmd.append(text)

  proc = await asyncio.create_subprocess_exec(
    *cmd,
    stdout=asyncio.subprocess.PIPE,
    stderr=asyncio.subprocess.PIPE,
  )
  out_b, err_b = await proc.communicate()
  return proc.returncode, out_b.decode(errors="replace"), err_b.decode(errors="replace")


class FontBrowserApp(App[None]):
  CSS = """
  #root Horizontal { height: 1fr; }
  #left Vertical { width: 44%; min-width: 30; border: solid $surface; }
  #right Vertical { width: 56%; min-width: 40; border: solid $surface; }
  #search Input { margin: 1 1; }
  #font-list ListView { height: 1fr; }
  #preview Log { height: 1fr; padding: 1 1; }
  """

  BINDINGS = [
    Binding("q", "quit", "Quit"),
    Binding("/", "focus_search", "Search"),
    Binding("w", "change_width", "Width"),
    Binding("s", "save_current", "Save current"),
    Binding("a", "save_all", "Save all"),
    Binding("r", "rescan", "Rescan"),
    Binding("j", "down", show=False),
    Binding("k", "up", show=False),
  ]

  def __init__(self, config: Config):
    super().__init__()
    self.config = config
    self.all_fonts: List[FontEntry] = []
    self.filtered_fonts: List[FontEntry] = []
    self.counter: int = 0
    self.last_render: str = ""
    self._width_mode: bool = False

    self.font_list: ListView | None = None
    self.preview: Log | None = None
    self.search_input: Input | None = None

  def compose(self) -> ComposeResult:
    yield Header(show_clock=False)
    with Horizontal(id="root"):
      with Vertical(id="left"):
        yield Input(placeholder="Filter fonts (substring)", id="search")
        self.font_list = ListView(id="font-list")
        yield self.font_list
      with Vertical(id="right"):
        yield Label(self._status_text(), id="status")
        self.preview = Log(id="preview")
        yield self.preview
    yield Footer()

  def on_mount(self) -> None:
    self.search_input = self.query_one("#search", Input)
    self.font_list = self.query_one("#font-list", ListView)
    self.preview = self.query_one("#preview", Log)

    self._rescan()

    # Focus list & render first item if present
    self.font_list.focus()
    if self.filtered_fonts:
      self.font_list.index = 0
      self.call_after_refresh(self._render_selected)

  # ----- Status helpers -----
  def _status_text(self) -> str:
    flc = str(self.config.flc) if self.config.flc else "<none>"
    return (
      f"Text: {self.config.text!r}  |  Width: {self.config.width}  |  .flc: {flc}  |  "
      f"Out: {self.config.out_dir or '<none>'}"
    )

  def _refresh_status(self) -> None:
    self.query_one("#status", Label).update(self._status_text())

  # ----- Actions -----
  def action_quit(self) -> None:
    self.exit()

  def action_focus_search(self) -> None:
    self._width_mode = False
    self.search_input.placeholder = "Filter fonts (substring)"
    self.search_input.focus()

  def action_change_width(self) -> None:
    # Reuse search input as a simple width prompt
    self.search_input.placeholder = f"Width (current {self.config.width}) — type number and press Enter"
    self.search_input.value = ""
    self._width_mode = True
    self.search_input.focus()

  def action_save_current(self) -> None:
    if not self.config.out_dir:
      self.bell(); self.toast("No --out-dir provided."); return
    cur = self._current_font()
    if cur is None or self.preview is None:
      return
    out = self._next_output_path()
    out.write_text(self.last_render or "")
    self.toast(f"Saved {out}")

  def action_save_all(self) -> None:
    if not self.config.out_dir:
      self.bell(); self.toast("No --out-dir provided."); return

    fonts = list(self.filtered_fonts)
    if not fonts:
      self.toast("No fonts to save.")
      return

    async def worker() -> None:
      assert self.preview is not None
      self._clear_preview("Saving all fonts…")
      saved = 0
      failures: list[FontEntry] = []
      name_counts: dict[str, int] = {}

      for fe in fonts:
        code, out, err = await run_figlet(
          self.config.text,
          self.config.width,
          fe,
          self.config.flc,
          self.config.use_toilet,
        )

        header = f"{'='*78}\n{fe.path}\n{'-'*78}\n"
        if code == 0:
          body = out
        else:
          body = "[ERROR]\n" + out + "\n" + err
          failures.append(fe)
        footer = "\n" + "-"*78
        rendered = header + body + footer
        self.last_render = rendered

        base = self._sanitise_name(fe)
        out_path = self._next_output_path(base, name_counts)
        out_path.write_text(rendered)
        saved += 1
        self._append_preview(f"Saved {out_path}")

      if failures:
        self._append_preview("\nErrors encountered:")
        for fe in failures:
          self._append_preview(f"- {fe.path}: see saved file for details")
      self.toast(f"Saved {saved} fonts to {self.config.out_dir}")

    self.run_worker(worker())

  def action_rescan(self) -> None:
    self._rescan()

  def action_down(self) -> None:
    if self.font_list is not None:
      self.font_list.action_cursor_down()

  def action_up(self) -> None:
    if self.font_list is not None:
      self.font_list.action_cursor_up()

  # ----- Input & list handlers -----
  def on_input_submitted(self, event: Input.Submitted) -> None:
    if event.input.id != "search":
      return
    value = event.value.strip()
    if self._width_mode:
      if value:
        try:
          self.config.width = max(1, int(value))
          self._refresh_status()
          self._render_selected()
        except ValueError:
          self.bell()
          self.toast("Width must be an integer")
      self._width_mode = False
      self.search_input.placeholder = "Filter fonts (substring)"
      self.search_input.value = ""
      return

    self._apply_filter(value)
    self.search_input.placeholder = "Filter fonts (substring)"

  def on_input_changed(self, event: Input.Changed) -> None:
    if event.input.id == "search" and not self._width_mode:
      self._apply_filter(event.value)

  def on_list_view_highlighted(self, _event: ListView.Highlighted) -> None:
    self._render_selected()

  # ----- Helpers -----
  def _apply_filter(self, needle: str) -> None:
    n = needle.strip().lower()
    if not n:
      self.filtered_fonts = list(self.all_fonts)
    else:
      self.filtered_fonts = [f for f in self.all_fonts if n in str(f.path).lower()]
    self._rebuild_list()

  def _rebuild_list(self) -> None:
    if self.font_list is None:
      return
    prev_index = self.font_list.index or 0
    self.font_list.clear()
    for fe in self.filtered_fonts:
      try:
        rel = fe.path.relative_to(self.config.font_dir)
      except Exception:
        rel = fe.path
      self.font_list.append(ListItem(Label(str(rel))))
    if self.filtered_fonts:
      self.font_list.index = min(prev_index, len(self.filtered_fonts) - 1)
      self.call_after_refresh(self._render_selected)
    else:
      self._clear_preview("No font selected.")

  def _rescan(self) -> None:
    self.all_fonts = scan_fonts(self.config.font_dir)
    self.filtered_fonts = list(self.all_fonts)
    self._rebuild_list()
    self._refresh_status()

  def _current_font(self) -> Optional[FontEntry]:
    if not self.filtered_fonts or self.font_list is None:
      return None
    idx = self.font_list.index or 0
    if 0 <= idx < len(self.filtered_fonts):
      return self.filtered_fonts[idx]
    return None

  def _clear_preview(self, msg: str = "") -> None:
    if self.preview is None:
      return
    self.preview.clear()
    if msg:
      self.preview.write_line(msg, markup=False, highlight=False)

  def _append_preview(self, s: str, *, interpret_ansi: bool = False) -> None:
    if self.preview is None:
      return
    if interpret_ansi:
      text = Text.from_ansi(s, strip=False)
      self.preview.write(text)
      if not s.endswith("\n"):
        self.preview.write("\n", markup=False, highlight=False)
      return

    for line in s.splitlines():
      self.preview.write_line(line, markup=False, highlight=False)

  def _next_output_path(
    self,
    base: Optional[str] = None,
    counts: Optional[dict[str, int]] = None,
  ) -> Path:
    if not self.config.out_dir:
      raise RuntimeError("Output directory not configured")
    out_dir = self.config.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if base is None:
      while True:
        candidate = out_dir / f"{self.config.out_prefix}{self.counter}.asc"
        if not candidate.exists():
          self.counter += 1
          return candidate
        self.counter += 1

    if counts is None:
      counts = {}

    used = counts.get(base, 0)
    while True:
      suffix = "" if used == 0 else f"_{used+1:02d}"
      candidate = out_dir / f"{self.config.out_prefix}{base}{suffix}.asc"
      if not candidate.exists():
        counts[base] = used + 1
        return candidate
      used += 1

  def _sanitise_name(self, font: FontEntry) -> str:
    try:
      rel = font.path.relative_to(self.config.font_dir)
    except Exception:
      rel = Path(font.path.name)
    rel_path = Path(rel)
    safe = rel_path.with_suffix("").as_posix().replace("/", "__")
    chars = [c if c.isalnum() or c in {"-", "_"} else "_" for c in safe]
    cleaned = "".join(chars).strip("_")
    return cleaned or font.base_name

  def _render_selected(self) -> None:
    fe = self._current_font()
    if not fe:
      self._clear_preview("No font selected.")
      return

    async def worker() -> None:
      self._clear_preview("Rendering…")
      code, out, err = await run_figlet(
        self.config.text,
        self.config.width,
        fe,
        self.config.flc,
        self.config.use_toilet,
      )
      self.preview.clear()
      header = f"{'='*78}\n{fe.path}\n{'-'*78}\n"
      self._append_preview(header)
      if code == 0:
        self._append_preview(out, interpret_ansi=True)
        body = out
      else:
        err_text = "[ERROR]\n" + out + "\n" + err

        self._append_preview(err_text)

        body = err_text
      footer = "\n" + "-"*78
      self._append_preview(footer)
      self.last_render = header + body + footer

    self.run_worker(worker())


# -------------------------
# CLI wiring
# -------------------------

def parse_args(argv: Optional[List[str]] = None) -> Config:
  p = argparse.ArgumentParser(description="Browse figlet fonts in a TUI and preview outputs.")
  p.add_argument("--font-dir", type=Path, default=Path.home() / "figlet-fonts", help="Base directory to scan recursively for fonts")
  p.add_argument("--text", required=True, help="Text to render in previews")
  p.add_argument("--width", type=int, default=os.get_terminal_size().columns if sys.stdout.isatty() else 80, help="Render width (columns)")
  p.add_argument("--out-dir", type=Path, default=None, help="Directory to save outputs (used by 's'/'a' actions)")
  p.add_argument("--out-prefix", dest="out_prefix", default="", help="Filename prefix when saving outputs")
  p.add_argument("--use-toilet", action="store_true", help="Use 'toilet' for .tlf fonts if available")
  p.add_argument("--flc", type=Path, default=None, help="Path to .flc charmap to pass to figlet via -C")

  ns = p.parse_args(argv)

  if not ns.font_dir.exists():
    p.error(f"--font-dir does not exist: {ns.font_dir}")

  if shutil.which("figlet") is None and not Path(FIGLET_DEFAULT).exists():
    p.error("figlet not found on PATH and /usr/bin/figlet not present")

  if ns.flc is not None:
    if not ns.flc.exists():
      p.error(f"--flc path does not exist: {ns.flc}")
    if ns.flc.suffix.lower() != ".flc":
      p.error("--flc must point to a .flc file")

  if ns.out_dir is not None:
    try:
      ns.out_dir.mkdir(parents=True, exist_ok=True)
    except Exception as e:
      p.error(f"unable to create --out-dir {ns.out_dir}: {e}")

  return Config(
    font_dir=ns.font_dir,
    text=ns.text,
    width=int(ns.width),
    out_dir=ns.out_dir,
    out_prefix=ns.out_prefix,
    use_toilet=bool(ns.use_toilet),
    flc=ns.flc,
  )


def main(argv: Optional[List[str]] = None) -> int:
  cfg = parse_args(argv)
  app = FontBrowserApp(cfg)
  app.run()
  return 0


if __name__ == "__main__":
  raise SystemExit(main())
