# FIGlet Font Importer

Copy FIGlet fonts (`.flf`, `.tlf`) from an input directory to an output directory with:

- **Content-based de-duplication** across the entire `--out` tree (recursive).
- **Versioned renaming** for same-name / different-content files (`_v02`, `_v03`, …).
- Optional **recursive** scanning of `--in`.
- Optional **outsub** routing (`--outsub`) to group this run’s copies into a subfolder.
- Optional **structure preservation** (`--maintain-structure`) to mirror `--in`’s subfolders under `--out/<outsub>/`.
- Pretty console output & progress bars via **Rich**.
- A **JSONL audit log** with one event per input file.

---

## Quickstart

```bash
# 1) (optional) create a virtualenv
python -m venv .venv && source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 2) install deps
pip install rich xxhash

# 3) run
python figlet_font_importer_rich.py --in ./fonts_in --out ./fonts_out

