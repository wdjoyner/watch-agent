# Watch-Agent: Automated Mechanical Horology Database & Archivist

**Live Interactive Catalog (Datasette Lite):** [https://wdjoyner.github.io/watch-agent/](https://wdjoyner.github.io/watch-agent/)

`watch-agent` is an automated data engineering and archival pipeline for mechanical and automatic wristwatches and movements. It extracts unstructured horological notes into strictly validated YAML records using a local LLM (`qwen3:30b` via Ollama) paired with Pydantic self-correction, compiles the records into a normalized SQLite relational database (`horology.db`), and publishes both an interactive browser-based SQL catalog (via GitHub Pages and Datasette Lite) and a typeset LaTeX reference manual (`horology_catalog.pdf`).

---

## 1. System Architecture & Pipeline Overview

1. **Unstructured Note Ingestion (`src/agent_ingest.py`)**
   Accepts raw text descriptions of watch movements or wristwatch references and prompts a local Ollama model (`watch-agent` / `qwen3:30b`) to output structured YAML. If the generated YAML violates any horological constraint (e.g., invalid beat frequency, missing winding mechanism on an automatic caliber, or malformed reference list), Pydantic catches the `ValidationError` and feeds the exact field traceback back to the LLM to self-correct before saving to `data/movements/` or `data/watches/`.
2. **Strict Horological Schema (`src/schema.py`)**
   Enforces domain-specific invariants via Pydantic v2:
   - **`MovementSpec`**: Validates `caliber_id`, `manufacturer`, `caliber_number`, `winding_type` (`Manual` vs. `Automatic`), `winding_mechanism` (e.g., `Magic Lever`, `Reverser Gears`, `Pawl-Winding`), `escapement_type` (`Swiss Lever`, `Co-Axial`, `Chronergy`, `Detent`), `frequency_vph`, `jewels`, and `power_reserve_hours`.
   - **`WatchReference`**: Validates `watch_id`, `brand`, `model_name`, `model_family`, `reference_numbers`, foreign-key link to `caliber_id`, production years, and nested **`TestCertification`** records (`COSC`, `METAS`, `ISO 6425`, accuracy bounds in seconds/day, water resistance in bar, and magnetic resistance in Gauss).
3. **Relational SQLite Compiler (`src/build_db.py`)**
   Scans all YAML files under `data/`, validates every record against `src/schema.py`, and builds `horology.db` from scratch with foreign-key enforcement (`PRAGMA foreign_keys = ON`). Generates three core tables (`movements`, `watches`, `watch_tests`) and a pre-joined view (`v_watch_catalog`).
4. **Automated GitHub Actions & Datasette Lite Hosting (`.github/workflows/validate_and_build.yml`)**
   On every push to `main`, GitHub Actions validates all YAML files, compiles an updated `horology.db`, commits the binary database back to the repository, and deploys a static WebAssembly SQL interface powered by Datasette Lite and `metadata.json` to GitHub Pages.
5. **Typeset LaTeX Reference Catalog (`src/export_latex.py`)**
   Queries `horology.db` directly to generate `horology_catalog.tex` and `horology_catalog.pdf` using compact horological nomenclature codes and `longtable` multi-page layouts.

---

## 2. Repository Directory Structure

- `.github/workflows/validate_and_build.yml` — CI/CD: validates YAML, builds `horology.db`, deploys Pages
- `data/movements/` — Validated caliber YAML files (e.g., `eta_6497_1.yaml`)
- `data/watches/` — Validated watch reference YAML files
- `src/schema.py` — Pydantic v2 models & horological validation rules
- `src/build_db.py` — Compiles YAML records into SQLite (`horology.db`)
- `src/agent_ingest.py` — Ollama LLM text-to-YAML extractor with retry loop
- `src/export_latex.py` — Generates compact LaTeX catalog from `horology.db`
- `horology.db` — Compiled SQLite relational database
- `horology_catalog.tex` / `horology_catalog.pdf` — Typeset print catalog
- `metadata.json` — Datasette facets and canned SQL query definitions
- `requirements.txt` — Python dependencies (`pydantic`, `pyyaml`, `requests`)

---

## 3. Daily Workflows & Usage

### Ingesting a New Movement or Watch via Local Ollama Agent
Ensure Ollama is running locally (`ollama list`), activate your virtual environment, and run `src/agent_ingest.py`:

    python3 src/agent_ingest.py --build "Omega 1120 automatic movement (based on ETA 2892-A2), 28800 vph, 23 jewels, 44 hour power reserve, bidirectional rotor with reverser gears, Swiss lever escapement."

    python3 src/agent_ingest.py --type watch --build "Omega Seamaster Professional 300M Chronometer ref 2531.80.00, powered by caliber omega_1120, produced 1993 to 2006, COSC certified (-4 to +6 spd) and 30 bar water resistance."

### Manually Validating YAML & Building `horology.db`
If you create or edit YAML files by hand in `data/movements/` or `data/watches/`, run the compiler to verify schema compliance and rebuild the SQLite database:

    python3 src/build_db.py

### Generating the Typeset LaTeX Catalog (`horology_catalog.pdf`)
To keep multi-column specification tables readable within standard letter-page margins without overflowing, `src/export_latex.py` maps verbose horological descriptions to compact 2-to-4-character alphanumeric codes and wraps long reference lists inside fixed-width columns:

    python3 src/export_latex.py
    pdflatex -interaction=nonstopmode horology_catalog.tex
    pdflatex -interaction=nonstopmode horology_catalog.tex

#### Nomenclature & Technical Code Legend Used in the PDF Catalog

| Category | Code | Full Horological Description |
| :--- | :--- | :--- |
| **Winding (`Wnd`)** | `MW` | Manual Wind |
| | `A-ML` | Automatic — Seiko Magic Lever |
| | `A-RG` | Automatic — Reverser Gears (e.g., ETA 2824/2892, Omega 1120) |
| | `A-PW` | Automatic — Pawl-Winding / Pellaton |
| | `A-UN` | Automatic — Unidirectional Rotor (e.g., Valjoux 7750) |
| | `A-BI` | Automatic — Bidirectional (Generic) |
| **Escapement (`Esc`)** | `SL` | Swiss Lever |
| | `CX` | Co-Axial (George Daniels / Omega) |
| | `CH` | Chronergy |
| | `DT` | Detent |
| | `CYL` | Cylinder |
| **Certification (`Cert`)** | `COSC` | ISO 3159 Official Chronometer |
| | `MET` | METAS Master Chronometer |
| | `ISO-D` | ISO 6425 / DIN 8306 Diver's Watch |
| | `GVA` | Poincon de Geneve (Geneva Seal) |

---

## 4. Multi-Machine Git Synchronization & Troubleshooting

Because this repository is used across multiple machines (macOS and Ubuntu Linux) **and** features an automated GitHub Actions bot that compiles `horology.db` and commits it back to `main` after every push, follow these guidelines to avoid Git push/pull conflicts:

### Routine Sync Before Starting Work on Either Machine
Always pull with `--rebase` before making new changes locally so your machine downloads the latest `horology.db` compiled by the GitHub Actions bot:

    cd ~/Projects/watch-agent
    git pull origin main --rebase

### Standard Commit & Push After Adding Data or Code

    cd ~/Projects/watch-agent
    git pull origin main --rebase
    git add data/ src/ horology_catalog.tex horology_catalog.pdf
    git commit -m "data: update horological records and catalog"
    git push origin main

### Emergency Recovery (If Local Git State Gets Blocked on `horology.db`)
If Git refuses to pull or push because both your local machine and the GitHub Actions bot modified `horology.db` at the same time, run this safe recovery sequence to preserve your YAML/Python/LaTeX files while resetting the binary database conflict:

    cd ~/Projects/watch-agent
    mkdir -p /tmp/watch_backup/src
    cp -f src/*.py /tmp/watch_backup/src/ 2>/dev/null || true
    cp -f horology_catalog.* /tmp/watch_backup/ 2>/dev/null || true
    cp -rf data /tmp/watch_backup/ 2>/dev/null || true
    git merge --abort 2>/dev/null || true
    git rebase --abort 2>/dev/null || true
    git fetch origin
    git checkout main
    git reset --hard origin/main
    cp -f /tmp/watch_backup/src/*.py src/ 2>/dev/null || true
    cp -f /tmp/watch_backup/horology_catalog.* . 2>/dev/null || true
    cp -rf /tmp/watch_backup/data/* data/ 2>/dev/null || true
    python3 src/build_db.py
    git add .
    git commit -m "chore: sync local updates with remote main"
    git push origin main

### Checking GitHub Actions & GitHub Pages Status via CLI
- **List active workflows:** `gh workflow list`
- **Check recent build runs:** `gh run list --limit 3`
- **Inspect a specific run:** `gh run view <RUN_ID>`
- **Manually trigger a rebuild:** `gh workflow run "Validate, Build SQLite & Publish Datasette Pages"`

> **Note on GitHub Actions Node.js Warnings:** You may occasionally see an annotation in GitHub Actions stating *"Node.js 20 is deprecated... actions are being forced to run on Node.js 24"*. This is a harmless informational notice from GitHub's cloud runner environment regarding its internal JavaScript action wrappers and does not affect your build or deployment.

---

## 5. Acknowledgements

- **Coding Design & System Architecture:** Jointly designed by **David Joyner** and **Gemini Argon**, combining relational horological taxonomy, multi-machine Git workflows, and compact LaTeX cataloging.
- **Python Implementation & Automation:** Python scripts (`src/schema.py`, `src/build_db.py`, `src/agent_ingest.py`, `src/export_latex.py`, and `src/seed_core_calibers.py`), Pydantic validation loops, and GitHub Actions CI/CD pipelines developed with assistance from **Gemini Argon**.
