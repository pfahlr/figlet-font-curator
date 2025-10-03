```
 ██████████████████████████████████████████████████████████
 █▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓█
 █▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▓█
 █▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓█
 █▓░                                                    ░▓█
 █▓░  ╭╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╮  ░▓█
 █▓░  ┊                      ###                     ┊  ░▓█
 █▓░  ┊ ####### ###  ###### ###    ######## ######## ┊  ░▓█
 █▓░  ┊         ### ###     ###                ###   ┊  ░▓█
 █▓░  ┊ ####### ### ###  ## ###     #######    ###   ┊  ░▓█
 █▓░  ┊ ##      ### ###  ## ###     ###        ###   ┊  ░▓█
 █▓░  ┊ ##      ###  ###### ####### #######    ###   ┊  ░▓█
 █▓░  ┊ ==========================================   ┊  ░▓█
 █▓░  ┊                           __                 ┊  ░▓█
 █▓░  ┊    _______  ___________ _/ /_____  _____     ┊  ░▓█
 █▓░  ┊   / ___/ / / / ___/ __ `/ __/ __ \/ ___/     ┊  ░▓█
 █▓░  ┊  / /__/ /_/ / /  / /_/ / /_/ /_/ / /         ┊  ░▓█
 █▓░  ┊  \___/\__,_/_/   \__,_/\__/\____/_/          ┊  ░▓█
 █▓░  ╰╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╌╯  ░▓█
 █▓░                                                    ░▓█
 █▓░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░░▓█
 █▓▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▒▓█
 █▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓▓█
 ██████████████████████████████████████████████████████████
```


# FIGlet Font Curator & Browser

A two-part toolkit for building and exploring a clean, well-organized **FIGlet** font collection:

1. **Curator (CLI)** — import `.flf`/`.tlf`/`.flc`, de-duplicate, organize into a repository, with optional *output-based* duplicate detection
2. **Browser (Textual TUI)** — preview `.flf`/`.tlf` fonts live, filter, and save previews; supports fonts packaged inside ZIP archives

> Built with [Rich](https://github.com/Textualize/rich) / [Textual](https://github.com/Textualize/textual).
> Rendering uses system `figlet` (and optionally `toilet` for `.tlf`).

---

## Features at a glance

**Curator — `figlet_font_curator.py`**

* Imports `.flf`, `.tlf`, and `.flc` files from `--in` into `--out`
* **Content-based de-duplication** using fast `xxhash`
* **Optional output-based de-duplication** (`--compare-output`): hashes the **rendered FIGlet output** for a fixed sample string to detect duplicates that produce identical text output
* **Versioned name collisions**: `name.ext` → `name_v02.ext`, `name_v03.ext`, …
* Optional **recursive** scan and **structure preservation** (`--maintain-structure` with `--outsub` + `-r`)
* **Rich** progress bars and pretty console logs
* **JSONL** audit log saved to `--out`

**Browser — `figlet_font_browser.py`**

* Recursively scans a font dir for `.flf` and `.tlf`
* **ZIP support**: transparently previews `.flf`/`.tlf` found *inside* `.zip` files (cached extraction)
* Live preview of your text (adjustable width)
* Optional **FIGlet charmap** (`.flc`) via `--flc` (passed to `figlet` with `-C`)
* Optional `--use-toilet` for `.tlf` rendering
* Filter/search list; save **current** or **all** previews
* Robust output normalization: CP437/Latin-1 fallbacks, ANSI repair, backspace overstrike handling

---

## Install

### System requirements

* Python 3.9+ (tested up to 3.13)
* `figlet` in your `PATH`
* Optionally `toilet` (only if you plan to render `.tlf` with `--use-toilet`)

### Python dependencies

```bash
# in your virtualenv
pip install rich textual xxhash
```

---

## 1) Curator (CLI)

**Script:** `figlet_font_curator.py`

Imports `.flf`, `.tlf`, and `.flc` from `--in` to `--out` with de-duplication and optional organization.
Duplicates are detected either by **raw file content** (fast, default), or by **rendered output** when `--compare-output` is set.

### Usage

```bash
python figlet_font_curator.py \
  --in /path/to/in_fonts \
  --out /path/to/out_fonts \
  [-r|--recursive] \
  [--outsub source_name] \
  [--maintain-structure] \
  [--compare-output]
```

### Options

* `--in, -i <dir>`
  Input directory containing `.flf` / `.tlf` / `.flc`
* `--out, -o <dir>`
  Output directory (the master repo)
* `-r, --recursive`
  Recurse into `--in` subdirectories
* `--outsub <name>`
  Place this run’s copies under `--out/<name>/` (still de-dups against **all of `--out`**)
* `--maintain-structure`
  Effective **only** with `--outsub` **and** `--recursive`; preserves the input’s subdirectory layout under `--out/<outsub>/`
* `--compare-output`
  Compare fonts by the **FIGlet-rendered output** for a fixed sample string (`"FIGLET FONT CURATOR"`) instead of raw file content
  *(Requires `figlet` to be installed.)*

### How de-duplication works

* **Default (content-based):** A fast `xxhash` digest of the file bytes is used. If a match is found anywhere under `--out` (scanned recursively), the file is skipped.
* **`--compare-output`:** The Curator runs `figlet` with `-d <font_dir> -f <font_name>` using a fixed sample string, and hashes the resulting text. Files that produce **identical output** are treated as duplicates even if their bytes differ.

  * This is useful to collapse near-identical `.flf` files that render the same.
  * **Important:** Output comparison applies to **`.flf` fonts only**. Non-FIGlet files like `.tlf` or `.flc` **can’t** be rendered by `figlet`; those will be **skipped** (logged as `ERROR_FINGERPRINT`) when `--compare-output` is enabled. If your set includes `.tlf`/`.flc`, prefer the default content-based mode.

### Naming & versioning

If a filename collision occurs (same name, different content/output), Curator writes the next available versioned name in the destination folder:

```
font.flf → font_v02.flf → font_v03.flf → ...
```

### Logging

* A JSONL audit log is written to:

  ```
  --out/figlet_import_YYYYMMDD_HHMMSS.log.jsonl
  ```

  Each event includes timestamps, inputs, destination, fingerprint method, and action (`COPY`, `COPY_RENAMED`, `SKIP_DUPLICATE`, errors, etc.).
* Console progress and summaries use **Rich**.

### Examples

```bash
# Simple flat import (content-based de-dup)
python figlet_font_curator.py --in ./fonts_in --out ./fonts_repo

# Recursive import grouped under 'dump_2025_10_03' and preserve input tree
python figlet_font_curator.py --in ./dump --out ./repo -r --outsub dump_2025_10_03 --maintain-structure

# Output-based duplicate detection (FIGlet-rendered equivalence), .flf-only
python figlet_font_curator.py --in ./flf_only --out ./repo --compare-output
```

**Notes & caveats**

* If `--out` is nested inside `--in` and you pass `-r`, Curator automatically **excludes** the `--out` subtree to avoid re-ingesting its own output.
* `--compare-output` uses a fixed sample string (`"FIGLET FONT CURATOR"`). To change the sample text, edit `DEFAULT_COMPARE_TEXT` in the script.

---

## 2) Browser (Textual TUI)

**Script:** `figlet_font_browser.py`

A terminal UI for browsing and previewing FIGlet fonts. It recursively scans a font directory for `.flf` and `.tlf` files, **including those inside ZIP archives**, renders a live preview of your text, and (optionally) applies a FIGlet charmap (`.flc`) via `--flc`. You can filter, page through results, and save outputs.

### Usage

```bash
python figlet_font_browser.py \
  --font-dir ~/figlet-fonts \
  --text "Hello World" \
  [--width 80] \
  [--flc /path/to/latin1.flc] \
  [--out-dir ./out] \
  [--out-prefix run_] \
  [--use-toilet]
```

### Features

* Recursively scans `--font-dir` for:

  * `.flf` (FIGlet fonts)
  * `.tlf` (TOIlet fonts)
  * **Inside ZIPs**: `.flf`/`.tlf` files are extracted to a temp cache and previewed seamlessly
* `--flc`: pass a **FIGlet charmap** via `-C` (FIGlet-only; ignored for `toilet`)
* Live preview with adjustable width (`w`)
* Quick filter/search of font list (`/`)
* Save the current preview (`s`) or **all** filtered previews (`a`)
* Output normalization:

  * Fixes ANSI sequences that get split by FIGlet’s wrapping
  * Applies backspace overstrikes (for classic shading/bold tricks)
  * Decodes with UTF-8, CP437, and Latin-1 fallbacks to preserve block characters

### CLI Options

* `--font-dir <dir>`: Base directory to scan recursively (default: `~/figlet-fonts`)
* `--text <string>` **(required)**: The text to render
* `--width <cols>`: Render width (default: TTY width or `80`)
* `--flc <path>`: Path to a `.flc` charmap (FIGlet-only; `toilet` doesn’t support `-C`)
* `--out-dir <dir>`: Where to save previews (`s` / `a` actions)
* `--out-prefix <str>`: Filename prefix when saving
* `--use-toilet`: Use `toilet` to render `.tlf` (if installed)

### Keybindings

* `/` — focus filter input
* `w` — change width (type a number, press Enter)
* `j` / `k` or ↓ / ↑ — move selection
* `s` — save **current** preview to `--out-dir/<prefix>N.asc`
* `a` — save **all** filtered previews (with headers) to `--out-dir`
* `r` — rescan fonts
* `q` — quit

### Examples

```bash
# Browse a collection (recursively)
python figlet_font_browser.py --font-dir ~/figlet-fonts --text JSON

# Apply a specific charmap (FIGlet-only)
python figlet_font_browser.py --font-dir ~/figlet-fonts --text "Café déjà vu" \
  --flc ~/figlet-fonts/charmaps/latin1.flc

# Prefer 'toilet' for .tlf fonts
python figlet_font_browser.py --font-dir ~/figlet-fonts --text "HELLO" --use-toilet

# Save previews as you browse
python figlet_font_browser.py --font-dir ~/figlet-fonts --text "Hello" \
  --out-dir ./out --out-prefix run_
```

---

## Recommended workflow

1. **Curate**
   Use the Curator to gather fonts into a de-duplicated repo at `--out`, optionally grouping each run with `--outsub` and mirroring structure with `--maintain-structure`.

2. **Browse**
   Point the Browser at your curated repo (or any folder/ZIP collection), try `.flc` charmaps, and export previews to share or compare.

---

## Troubleshooting

**Curator**

* *“It’s ingesting its own output”* → If `--out` is under `--in` and you used `-r`, the Curator excludes `--out` automatically.
* *“Why are `.tlf` / `.flc` skipped in `--compare-output` mode?”* → Output-comparison renders with `figlet` and is intended for `.flf`; non-FIGlet files can’t be rendered there and are skipped (with error logs). Use the default content-based mode for mixed sets.

**Browser**

* *Charmap not applied* → `--flc` only applies to `.flf` (FIGlet); `toilet` does not support `-C`.
* *Garbled blocks/ANSI noise* → The app repairs split ANSI, handles backspace overstrikes, and tries CP437/Latin-1 if UTF-8 fails. If a specific font still looks off, try a different width.

---

## Project structure (suggested)

```
.
├─ figlet_font_curator.py      # CLI import/dedupe (content or output-based)
├─ figlet_font_browser.py      # Textual TUI w/ ZIP support
├─ README.md
└─ requirements.txt            # rich, textual, xxhash
```

---

## Contributing

* Code style: Python with **2-space** indents (project preference).
* Keep CLI (Curator) and TUI (Browser) concerns decoupled.
* PRs welcome for:

  * Making the Curator’s sample text configurable at runtime
  * Optional watch mode for Curator (e.g., `watchfiles`)
  * Fuzzy/regex filter in the Browser
  * Export presets, batch selection, or side-by-side comparisons in the Browser

---

## License

MIT.
