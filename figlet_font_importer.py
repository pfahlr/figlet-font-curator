#!/usr/bin/env python3
"""
figlet_font_importer_rich.py

Copy FIGlet fonts (.flf, .tlf) from --in to --out with:
- Content-based de-duplication across the entire --out (recursive)
- Versioning on same-name/different-content (_v02, _v03, ...)
- Optional recursive scan of --in (-r/--recursive)
- Optional --outsub to place this run's copies under a subfolder of --out
- Rich progress bars & pretty console logs
- JSONL audit log

Usage:
  python figlet_font_importer_rich.py --in /path/to/in_fonts --out /path/to/out_fonts [-r] [--outsub source_name]
"""

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from typing import Dict, Iterable, List, Optional, Tuple

# Third-party
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import (
  Progress, SpinnerColumn, BarColumn, TextColumn,
  TimeElapsedColumn, TimeRemainingColumn, TaskID
)
import logging

try:
  import xxhash  # fast, non-crypto hash
except ImportError as e:
  print("Missing dependency 'xxhash'. Install with: pip install xxhash", file=sys.stderr)
  raise

CHUNK_SIZE = 1024 * 1024  # 1 MiB
LOG_BASENAME_PREFIX = "figlet_import"
ALLOWED_EXTS = {".flf", ".tlf"}  # Supported font extensions

console = Console()
logger = logging.getLogger("figlet_importer")

def setup_logging() -> None:
  logger.setLevel(logging.INFO)
  logger.handlers.clear()
  handler = RichHandler(console=console, show_time=False, show_level=False, rich_tracebacks=True)
  logger.addHandler(handler)

def now_iso() -> str:
  return datetime.now(timezone.utc).astimezone().isoformat()

def _is_allowed_font(path: Path) -> bool:
  return path.is_file() and path.suffix.lower() in ALLOWED_EXTS

def iter_font_files(directory: Path, recursive: bool, exclude_subtree: Optional[Path] = None) -> Iterable[Path]:
  """
  Yield .flf/.tlf files from `directory`.
  - If `recursive` is True, descends into subdirectories.
  - If `exclude_subtree` is provided, skips any file under that subtree (useful when --out is inside --in).
  """
  it = directory.rglob("*") if recursive else directory.iterdir()
  for p in it:
    try:
      if exclude_subtree is not None and p.resolve().is_relative_to(exclude_subtree.resolve()):
        continue
    except Exception:
      pass
    if _is_allowed_font(p):
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

def next_versioned_name(out_target_dir: Path, stem: str, ext: str) -> str:
  n = 2
  while True:
    candidate = f"{stem}_v{n:02d}{ext}"
    if not (out_target_dir / candidate).exists():
      return candidate
    n += 1

def plan_destination(
  out_target_dir: Path,
  src_name: str,
  src_hash: str,
  existing_hash_to_path: Dict[str, Path],
) -> Tuple[Optional[Path], str, bool, bool]:
  """
  Decide destination inside out_target_dir.
  Returns: (dest_path_or_None, action, name_conflict, content_duplicate)
           action ∈ {"COPY", "COPY_RENAMED", "SKIP_DUPLICATE"}
  """
  if src_hash in existing_hash_to_path:
    return None, "SKIP_DUPLICATE", False, True

  src_path = Path(src_name)
  stem, ext = src_path.stem, (src_path.suffix if src_path.suffix else ".flf")
  candidate = out_target_dir / f"{stem}{ext}"
  if not candidate.exists():
    return candidate, "COPY", False, False

  versioned = out_target_dir / next_versioned_name(out_target_dir, stem, ext)
  return versioned, "COPY_RENAMED", True, False

def write_jsonl(logfile: Path, record: dict) -> None:
  logfile.parent.mkdir(parents=True, exist_ok=True)
  with logfile.open("a", encoding="utf-8") as f:
    f.write(json.dumps(record, ensure_ascii=False) + "\n")

def index_existing(out_dir: Path, progress: Progress, task: TaskID) -> Dict[str, Path]:
  """
  Index existing output fonts by content hash (recursive across the entire --out).
  """
  existing_hash_to_path: Dict[str, Path] = {}
  existing_files = list(iter_font_files(out_dir, recursive=True))
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
  out_target_dir: Path,
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
      out_target_dir, src.name, src_hash, existing_hash_to_path
    )

    event = {
      "ts": now_iso(),
      "input": str(src),
      "input_hash": f"xxh64:{src_hash}",
      "out_dir": str(out_dir),
      "out_target_dir": str(out_target_dir),
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
      out_target_dir.mkdir(parents=True, exist_ok=True)
      shutil.copy2(src, dest)
      # Update maps so later inputs (this run) see this content as existing
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
    description="Import FIGlet fonts (.flf, .tlf) with content-based de-duplication, versioned naming, Rich progress, and JSONL logs."
  )
  parser.add_argument("--in", "-i", dest="in_dir", required=True, help="Input directory containing .flf/.tlf files.")
  parser.add_argument("--out", "-o", dest="out_dir", required=True, help="Output directory to populate with unique fonts.")
  parser.add_argument("-r", "--recursive", action="store_true", help="Scan input directory recursively.")
  parser.add_argument("--outsub", dest="out_sub", help="Subdirectory under --out to place files from this run (comparisons still index entire --out).")
  args = parser.parse_args()

  in_dir = Path(args.in_dir).expanduser().resolve()
  out_dir = Path(args.out_dir).expanduser().resolve()

  if not in_dir.is_dir():
    console.print(f"[red]ERROR[/] --in directory does not exist or is not a directory: {in_dir}")
    sys.exit(2)

  if in_dir == out_dir:
    console.print("[red]ERROR[/] --in and --out must be different directories.")
    sys.exit(2)

  # Determine the target folder for this run
  out_target_dir = (out_dir / args.out_sub).resolve() if args.out_sub else out_dir
  out_dir.mkdir(parents=True, exist_ok=True)
  out_target_dir.mkdir(parents=True, exist_ok=True)

  # Prevent accidental self-ingestion if --out is inside --in and --recursive is used
  try:
    exclude_subtree = out_dir if args.recursive and out_dir.is_relative_to(in_dir) else None
  except AttributeError:
    # Fallback if is_relative_to isn't available
    exclude_subtree = out_dir if args.recursive and str(out_dir).startswith(str(in_dir)) else None

  timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  logfile = out_dir / f"{LOG_BASENAME_PREFIX}_{timestamp}.log.jsonl"

  logger.info(
    f"Starting import  •  in=[bold]{in_dir}[/]  out=[bold]{out_dir}[/]  "
    f"outsub=[bold]{args.out_sub or '(none)'}[/]  recursive=[bold]{args.recursive}[/]"
  )
  logger.info(f"JSONL log: [italic]{logfile}[/]")

  # Gather input files (optionally recursive), skipping anything under --out if nested
  in_files = sorted(
    list(iter_font_files(in_dir, recursive=args.recursive, exclude_subtree=exclude_subtree)),
    key=lambda p: p.name.lower(),
  )

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
      in_files, out_dir, out_target_dir, existing_hash_to_path, logfile, progress, t_process
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

