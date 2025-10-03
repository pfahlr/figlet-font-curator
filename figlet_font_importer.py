#!/usr/bin/env python3
"""
figlet_font_importer_rich.py

Copy .flf (FIGlet font) files from --in to --out with content-based de-duplication,
versioning on same-name/different-content (_v02, _v03, ...), progress bars (Rich),
and JSONL operation logging.

Usage:
  python figlet_font_importer_rich.py --in /path/to/in_fonts --out /path/to/out_fonts
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from typing import Dict, Iterable, List, Optional, Tuple

# Third-party
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeElapsedColumn, TimeRemainingColumn, TaskID
import logging

try:
  import xxhash  # fast, non-crypto hash
except ImportError as e:
  print("Missing dependency 'xxhash'. Install with: pip install xxhash", file=sys.stderr)
  raise

CHUNK_SIZE = 1024 * 1024  # 1 MiB
LOG_BASENAME_PREFIX = "figlet_import"

console = Console()
logger = logging.getLogger("figlet_importer")

def setup_logging() -> None:
  logger.setLevel(logging.INFO)
  logger.handlers.clear()
  handler = RichHandler(console=console, show_time=False, show_level=False, rich_tracebacks=True)
  logger.addHandler(handler)

def now_iso() -> str:
  return datetime.now(timezone.utc).astimezone().isoformat()

def iter_flf_files(directory: Path) -> Iterable[Path]:
  # Only top-level .flf files (case-insensitive)
  for p in directory.iterdir():
    if p.is_file() and p.suffix.lower() == ".flf":
      yield p

def xxhash_file(path: Path) -> str:
  h = xxhash.xxh64()
  with path.open("rb") as f:
    while True:
      chunk = f.read(CHUNK_SIZE)
      if not chunk:
        break
      h.update(chunk)
  return h.hexdigest()

def next_versioned_name(out_dir: Path, stem: str, ext: str) -> str:
  n = 2
  while True:
    candidate = f"{stem}_v{n:02d}{ext}"
    if not (out_dir / candidate).exists():
      return candidate
    n += 1

def plan_destination(
  out_dir: Path,
  src_name: str,
  src_hash: str,
  existing_hash_to_path: Dict[str, Path],
) -> Tuple[Optional[Path], str, bool, bool]:
  """
  Returns:
    (dest_path_or_None, action, name_conflict, content_duplicate)
    action in {"COPY", "COPY_RENAMED", "SKIP_DUPLICATE"}
  """
  if src_hash in existing_hash_to_path:
    return None, "SKIP_DUPLICATE", False, True

  src_path = Path(src_name)
  stem, ext = src_path.stem, src_path.suffix or ".flf"
  candidate = out_dir / f"{stem}{ext}"
  if not candidate.exists():
    return candidate, "COPY", False, False

  versioned = out_dir / next_versioned_name(out_dir, stem, ext)
  return versioned, "COPY_RENAMED", True, False

def write_jsonl(logfile: Path, record: dict) -> None:
  logfile.parent.mkdir(parents=True, exist_ok=True)
  with logfile.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

def index_existing(out_dir: Path, progress: Progress, task: TaskID) -> Dict[str, Path]:
  existing_hash_to_path: Dict[str, Path] = {}
  existing_files = list(iter_flf_files(out_dir))
  progress.update(task, total=len(existing_files))

  for p in existing_files:
    try:
      h = xxhash_file(p)
      existing_hash_to_path.setdefault(h, p)
    except Exception as e:
      logger.info(f"[yellow]WARN[/]: failed to hash existing: {p.name} ({e})")
    finally:
      progress.advance(task, 1)

  return existing_hash_to_path

def process_inputs(
  in_files: List[Path],
  out_dir: Path,
  existing_hash_to_path: Dict[str, Path],
  logfile: Path,
  progress: Progress,
  task: TaskID,
) -> Tuple[int, int, int]:
  copied = 0
  renamed = 0
  skipped = 0
  progress.update(task, total=len(in_files))

  for src in in_files:
    # Hash input
    try:
      src_hash = xxhash_file(src)
    except Exception as e:
      event = {
        "ts": now_iso(),
        "input": str(src),
        "action": "ERROR_HASH",
        "error": str(e),
      }
      write_jsonl(logfile, event)
      logger.info(f"[red]ERROR[/]: cannot hash {src.name}: {e}")
      progress.advance(task, 1)
      continue

    dest, action, name_conflict, content_duplicate = plan_destination(
      out_dir, src.name, src_hash, existing_hash_to_path
    )

    event = {
      "ts": now_iso(),
      "input": str(src),
      "input_hash": f"xxh64:{src_hash}",
      "out_dir": str(out_dir),
      "existing_same_name": name_conflict,
      "existing_same_content": content_duplicate,
      "action": action,
    }

    if action == "SKIP_DUPLICATE":
      skipped += 1
      event["reason"] = "duplicate-content"
      write_jsonl(logfile, event)
      logger.info(f"[yellow]SKIP (dup)[/]: {src.name}")
      progress.advance(task, 1)
      continue

    assert dest is not None
    try:
      shutil.copy2(src, dest)
      # Update maps so later inputs see this content as existing
      existing_hash_to_path[src_hash] = dest
      event["dest"] = str(dest)
      write_jsonl(logfile, event)

      if action == "COPY":
        copied += 1
        logger.info(f"[green]COPY[/]: {src.name} → {dest.name}")
      else:
        renamed += 1
        logger.info(f"[cyan]RENAME+COPY[/]: {src.name} → {dest.name}")
    except Exception as e:
      event["action"] = "ERROR_COPY"
      event["error"] = str(e)
      write_jsonl(logfile, event)
      logger.info(f"[red]ERROR[/]: failed to copy {src.name} → {dest.name}: {e}")
    finally:
      progress.advance(task, 1)

  return copied, renamed, skipped

def main() -> None:
  setup_logging()

  parser = argparse.ArgumentParser(
    description="Import FIGlet .flf fonts with content-based deduplication, versioned naming, Rich progress, and JSONL logs."
  )
  parser.add_argument("--in", "-i", dest="in_dir", required=True, help="Input directory containing .flf files.")
  parser.add_argument("--out", "-o", dest="out_dir", required=True, help="Output directory to populate with unique .flf files.")
  args = parser.parse_args()

  in_dir = Path(args.in_dir).expanduser().resolve()
  out_dir = Path(args.out_dir).expanduser().resolve()

  if not in_dir.is_dir():
    console.print(f"[red]ERROR[/] --in directory does not exist or is not a directory: {in_dir}")
    sys.exit(2)

  if in_dir == out_dir:
    console.print("[red]ERROR[/] --in and --out must be different directories.")
    sys.exit(2)

  out_dir.mkdir(parents=True, exist_ok=True)

  timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  logfile = out_dir / f"{LOG_BASENAME_PREFIX}_{timestamp}.log.jsonl"

  logger.info(f"Starting import  •  in=[bold]{in_dir}[/]  out=[bold]{out_dir}[/]")
  logger.info(f"JSONL log: [italic]{logfile}[/]")

  in_files = sorted(list(iter_flf_files(in_dir)), key=lambda p: p.name.lower())

  with Progress(
    SpinnerColumn(),
    TextColumn("[progress.description]{task.description}"),
    BarColumn(),
    TextColumn("{task.completed}/{task.total}"),
    TimeElapsedColumn(),
    TextColumn("•"),
    TimeRemainingColumn(),
    console=console,
    transient=False,
  ) as progress:
    t_index = progress.add_task("Indexing existing output fonts", total=0)
    existing_hash_to_path = index_existing(out_dir, progress, t_index)

    t_process = progress.add_task("Processing input fonts", total=0)
    copied, renamed, skipped = process_inputs(
      in_files, out_dir, existing_hash_to_path, logfile, progress, t_process
    )

  # Summary
  console.rule("Summary")
  console.print(
    f"[green]copied={copied}[/], [cyan]renamed={renamed}[/], [yellow]skipped_duplicates={skipped}[/]"
  )
  console.print(f"Log file: [italic]{logfile}[/]")
  logger.info("Done.")

if __name__ == "__main__":
  main()
