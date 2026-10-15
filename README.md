# Watch-Agent: Automated Mechanical Horology Database & Archivist

**Live Catalog:** [https://wdjoyner.github.io/watch-agent/](https://wdjoyner.github.io/watch-agent/)

`watch-agent` is an automated data engineering and archival pipeline for mechanical and automatic wristwatches and movements. It extracts unstructured horological notes into strictly validated YAML records using a local LLM (`qwen3:30b` via Ollama) paired with Pydantic self-correction, compiles the records into a normalized SQLite relational database (`horology.db`), and publishes both a searchable web catalog on GitHub Pages (with a link to query the database in Datasette Lite) and a typeset LaTeX reference manual (`horology_catalog.pdf`).

---

## 1. System Architecture & Pipeline Overview

1. **Unstructured Note Ingestion (`src/agent_ingest.py`)**
   Accepts raw text descriptions of watch movements or wristwatch references and prompts a local Ollama model (`watch-agent` / `qwen3:30b`) to output structured YAML. If the generated YAML violates any horological constraint (e.g., invalid beat frequency, missing winding mechanism on an automatic caliber, or malformed reference list), Pydantic catches the `ValidationError` and feeds the exact field traceback back to the LLM to self-correct before saving to `data/movements/` or `data/watches/`.
2. **Strict Horological Schema (`src/schema.py`)**
   Enforces domain-specific invariants via Pydantic v2:
   - **`MovementSpec`**: Validates `caliber_id`, `manufacturer`, `caliber_number`, `winding_type` (`Manual` vs. `Automatic`), `winding_mechanism` (e.g., `Magic Lever`, `Reverser Gears`, `Pawl-Winding`), `escapement_type` (`Swiss Lever`, `Co-Axial`, `Chronergy`, `Detent`), `frequency_vph`, `jewels`, and `power_reserve_hours`.
   - **`WatchReference`**: Validates `watch_id`, `brand`, `model_name`, `model_family`, `reference_numbers`, foreign-key link to `caliber_id`, production years, and nested **`TestCertification`** records (`COSC`, `METAS`, `ISO 6425`, accuracy bounds in seconds/day, water resistance in bar, and magnetic resistance in Gauss).
3. **Relational SQLite Compiler (`src/build_db.py`)**
   Scans all YAML files under `data/`, validates every record against `src/schema.py`, and builds `horology.db` from scratch with foreign-key enforcement (`PRAGMA foreign_keys = ON`). Generates three core tables (`movements`, `watches`, `watch_tests`), a pre-joined view (`v_watch_catalog`), and the static web page `index.html`. If any file is invalid it lists **every** problem in **every** file and builds nothing.
4. **GitHub Actions & GitHub Pages (`.github/workflows/build_and_deploy.yml`)**
   On every push to `main`, GitHub Actions validates all YAML files, builds `horology.db` and `index.html`, and publishes them to GitHub Pages. Nothing is committed back to the repository, so there are no bot commits to pull. If validation fails, the run is marked red, the error list is in its log, and the website keeps showing the last good version. (One-time setting: *Settings → Pages → Build and deployment → Source = GitHub Actions*.)
5. **Typeset LaTeX Reference Catalog (`src/export_latex.py`)**
   Queries `horology.db` directly to generate `horology_catalog.tex` and `horology_catalog.pdf` using compact horological nomenclature codes and `longtable` multi-page layouts.

---

## 2. Repository Directory Structure

- `.github/workflows/build_and_deploy.yml` — CI/CD: validates YAML, builds `horology.db` + `index.html`, deploys Pages
- `docs/YAML_FORMAT.md` — complete record format; paste this into an AI when asking it to write YAML
- `data/movements/` — Validated caliber YAML files (e.g., `eta_6497_1.yaml`)
- `data/watches/` — Validated watch reference YAML files
- `src/schema.py` — Pydantic v2 models & horological validation rules
- `src/build_db.py` — Compiles YAML records into SQLite (`horology.db`)
- `src/agent_ingest.py` — Ollama LLM text-to-YAML extractor with retry loop
- `src/export_latex.py` — Generates compact LaTeX catalog from `horology.db`
- `horology.db`, `index.html` — built locally or by CI; not committed (listed in `.gitignore`)
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
If you create or edit YAML files by hand (or with an AI) in `data/movements/` or `data/watches/`, check them before pushing:

    python3 src/build_db.py --check     # report problems only
    python3 src/build_db.py             # also build horology.db and index.html (open index.html to preview the site)

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

`horology.db` and `index.html` are no longer committed (CI builds them), so the old conflicts on the binary database cannot happen. The routine is:

    cd ~/Projects/watch-agent
    git pull                                # get changes made on the other machine
    # ... add or edit YAML files ...
    python3 src/build_db.py --check         # fix anything it reports
    git add data/
    git commit -m "data: add <what you added>"
    git push

### Is the website up to date?
The page header shows the build time and the number of watches and movements. If it is older than your last push, open the **Actions** tab on GitHub (or run `gh run list --limit 3`). A red run means a YAML problem; click it and open the *Validate YAML and build database + web page* step to see the list of errors. Fix the files, push again, and the site updates within a minute or two.

To rebuild by hand: `gh workflow run "Validate, Build & Deploy Pages"`.

---

## 5. Acknowledgements

- **Coding Design & System Architecture:** Jointly designed by **David Joyner** and **Gemini Argon**, combining relational horological taxonomy, multi-machine Git workflows, and compact LaTeX cataloging.
- **Python Implementation & Automation:** Python scripts (`src/schema.py`, `src/build_db.py`, `src/agent_ingest.py`, `src/export_latex.py`, and `src/seed_core_calibers.py`), Pydantic validation loops, and GitHub Actions CI/CD pipelines developed with assistance from **Gemini Argon**.

---

## 6. Asking an AI (ChatGPT, Gemini, Claude) to Write YAML Records

The complete, authoritative format is in **[`docs/YAML_FORMAT.md`](docs/YAML_FORMAT.md)**. It lists every allowed key, every allowed enum value, how to write unknown values, and gives one full valid example of each record type.

1. Open `docs/YAML_FORMAT.md` (on GitHub, use the *Raw* button) and copy all of it.
2. Paste it into the AI, followed by:

   ```text
   Using exactly the format above, convert the following notes into YAML files.
   Use null for anything the notes do not state; do not guess.

   [your notes here]
   ```

3. Save each block the AI returns as the file name it gives (e.g. `data/movements/omega_861.yaml`).
4. Run `python3 src/build_db.py --check`. If it reports problems, paste the error list back to the AI and ask it to correct the files.
5. Commit and push.

Good notes include: manufacturer and caliber number, ebauche ancestry, manual vs. automatic and the winding mechanism, escapement, frequency (vph), jewels, power reserve; and for a watch: brand, family, model, reference numbers, production years, and any certifications (COSC, METAS, ISO 6425, ...) with their accuracy, water and magnetic ratings.
