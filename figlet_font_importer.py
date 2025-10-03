#!/usr/bin/env python3
"""
figlet_font_importer.py

Copy .flf (FIGlet font) files from --in to --out with content-based de-duplication.
- If an input file's content matches any .flf in --out (including ones copied earlier
  in the same run), it is SKIPPED.
- If a file name collides but contents differ, write with a versioned suffix:
  name_v02.flf, name_v03.flf, ... (next available).
- Logs every operation to a timestamped JSONL log file under --out and echoes a summary.

Usage:
  python figlet_font_importer.py --in /path/to/in_fonts --out /path/to/out_fonts
"""

import argparse
import hashlib
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
import shutil
import sys
from typing import Dict, Optional, Tuple

CHUNK_SIZE = 1024 * 1024  # 1 MiB
LOG_BASENAME_PREFIX = "figlet_import"

def sha256_file(path: Path) -> str:
  h = hashlib.sha256()
  with path.open("rb") as f:
    for chunk in iter(lambda: f.read(CHUNK_SIZE), b""):
      h.update(chunk)
  return h.hexdigest()

def iter_flf_files(directory: Path):
  # Only top-level .flf files (case-insensitive)
  for p in directory.iterdir():
    if p.is_file() and p.suffix.lower() == ".flf":
      yield p

def prepare_logger(log_path: Path) -> logging.Logger:
  logger = logging.getLogger("figlet_importer")
  logger.setLevel(logging.INFO)
  logger.handlers.clear()

  # Console for human-readable progress
  ch = logging.StreamHandler(sys.stdout)
  ch.setLevel(logging.INFO)
  ch.setFormatter(logging.Formatter("%(message)s"))
  logger.addHandler(ch)

  # File handler emits JSONL entries (we'll write JSON manually per event)
  fh = logging.FileHandler(log_path, encoding="utf-8")
  fh.setLevel(logging.INFO)
  fh.setFormatter(logging.Formatter("%(message)s"))
  logger.addHandler(fh)

  return logger

def jsonl_log(file_handle: logging.FileHandler, record: dict):
  # Route JSONL only to the file handler; the main logger writes strings to both.
  # We'll emit the JSON string via the logger but tag lines to filter where needed.
  logging.getLogger("figlet_importer").info(json.dumps(record, ensure_ascii=False))

def now_iso() -> str:
  return datetime.now(timezone.utc).astimezone().isoformat()

def next_versioned_name(out_dir: Path, stem: str, ext: str) -> str:
  """
  Returns the next available versioned filename like stem_v02.ext, stem_v03.ext, ...
  Assumes stem.ext is already taken.
  """
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
  Decide where (and whether) to copy the file.

  Returns:
    (dest_path_or_None, action, name_conflict, content_duplicate)
    - action in {"COPY", "COPY_RENAMED", "SKIP_DUPLICATE"}
  """
  # Duplicate by content?
  if src_hash in existing_hash_to_path:
    return None, "SKIP_DUPLICATE", False, True

  # Not a content duplicate. Check for name collision.
  src_path = Path(src_name)
  stem, ext = src_path.stem, src_path.suffix
  if not ext:
    ext = ".flf"  # be defensive; but .flf should exist

  candidate = out_dir / f"{stem}{ext}"
  if not candidate.exists():
    return candidate, "COPY", False, False

  # Name exists but different content: version it.
  versioned = out_dir / next_versioned_name(out_dir, stem, ext)
  return versioned, "COPY_RENAMED", True, False

def main():
  parser = argparse.ArgumentParser(
    description="Import FIGlet .flf fonts with content-based deduplication and versioned naming."
  )
  parser.add_argument("--in", "-i", dest="in_dir", required=True, help="Input directory containing .flf files.")
  parser.add_argument("--out", "-o", dest="out_dir", required=True, help="Output directory to populate with unique .flf files.")
  args = parser.parse_args()

  in_dir = Path(args.in_dir).expanduser().resolve()
  out_dir = Path(args.out_dir).expanduser().resolve()

  if not in_dir.is_dir():
    print(f"ERROR: --in directory does not exist or is not a directory: {in_dir}", file=sys.stderr)
    sys.exit(2)

  if in_dir == out_dir:
    print("ERROR: --in and --out must be different directories.", file=sys.stderr)
    sys.exit(2)

  out_dir.mkdir(parents=True, exist_ok=True)

  # Prepare logger and JSONL log file
  timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  log_path = out_dir / f"{LOG_BASENAME_PREFIX}_{timestamp}.log.jsonl"
  logger = prepare_logger(log_path)

  logger.info(f"Starting import  •  in={in_dir}  out={out_dir}")
  logger.info(f"Log file: {log_path}")

  # Index existing out_dir .flf files by content hash
  existing_hash_to_path: Dict[str, Path] = {}
  existing_count = 0
  for existing in iter_flf_files(out_dir):
    try:
      h = sha256_file(existing)
      # If collisions in out_dir (same content multiple files), first one wins; that's fine for our purposes.
      existing_hash_to_path.setdefault(h, existing)
      existing_count += 1
    except Exception as e:
      logger.info(f"WARNING: Failed to hash existing file: {existing} ({e})")

  logger.info(f"Found {existing_count} existing .flf in output.")

  # Gather input files
  in_files = list(iter_flf_files(in_dir))
  logger.info(f"Found {len(in_files)} input .flf files.")

  copied = 0
  renamed = 0
  skipped_dups = 0

  for src in sorted(in_files, key=lambda p: p.name.lower()):
    try:
      src_hash = sha256_file(src)
    except Exception as e:
      event = {
        "ts": now_iso(),
        "input": str(src),
        "action": "ERROR_HASH",
        "error": str(e),
      }
      jsonl_log(None, event)
      logger.info(f"ERROR: Cannot hash {src.name}: {e}")
      continue

    dest, action, name_conflict, content_duplicate = plan_destination(
      out_dir, src.name, src_hash, existing_hash_to_path
    )

    event = {
      "ts": now_iso(),
      "input": str(src),
      "input_hash": f"sha256:{src_hash}",
      "out_dir": str(out_dir),
      "existing_same_name": name_conflict,
      "existing_same_content": content_duplicate,
      "action": action,
    }

    if action == "SKIP_DUPLICATE":
      skipped_dups += 1
      event["reason"] = "duplicate-content"
      jsonl_log(None, event)
      logger.info(f"SKIP (dup): {src.name}")
      continue

    # COPY or COPY_RENAMED
    assert dest is not None
    dest.parent.mkdir(parents=True, exist_ok=True)

    try:
      shutil.copy2(src, dest)
      existing_hash_to_path[src_hash] = dest
      event["dest"] = str(dest)
      jsonl_log(None, event)

      if action == "COPY":
        copied += 1
        logger.info(f"COPY: {src.name} -> {dest.name}")
      else:
        renamed += 1
        logger.info(f"RENAME+COPY: {src.name} -> {dest.name}")

    except Exception as e:
      event["action"] = "ERROR_COPY"
      event["error"] = str(e)
      jsonl_log(None, event)
      logger.info(f"ERROR: Failed to copy {src.name} -> {dest.name}: {e}")

  # Summary
  logger.info("—" * 50)
  logger.info(f"Summary: copied={copied}, renamed={renamed}, skipped_duplicates={skipped_dups}")
  logger.info("Done.")

if __name__ == "__main__":
  main()
