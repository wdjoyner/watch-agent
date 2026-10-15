# src/build_db.py
"""
Validate every YAML record in data/ against src/schema.py, then compile
horology.db (SQLite) and a static index.html for GitHub Pages.

    python3 src/build_db.py            # validate + build horology.db + index.html
    python3 src/build_db.py --check    # validate only (writes nothing)

If any file is invalid, ALL problems in ALL files are listed and nothing is
built, so a bad YAML file can never silently produce a broken database.
"""
import argparse
import html
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import MovementSpec, WatchReference  # noqa: E402

ROOT_DIR = Path(__file__).resolve().parent.parent
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"
DB_PATH = ROOT_DIR / "horology.db"
HTML_PATH = ROOT_DIR / "index.html"


# ---------------------------------------------------------------- validation
def _format_pydantic(e: ValidationError) -> list[str]:
    lines = []
    for err in e.errors():
        loc = ".".join(str(x) for x in err["loc"]) or "(file)"
        got = err.get("input")
        got_s = "" if isinstance(got, dict) else f"  (got: {got!r})"
        lines.append(f"{loc}: {err['msg']}{got_s}")
    return lines


def _load(path: Path, model, id_field: str, errors: dict):
    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as e:
        errors[path] = [f"YAML syntax error: {e}"]
        return None
    if not isinstance(raw, dict):
        errors[path] = ["File must contain a single YAML mapping (key: value lines)."]
        return None
    try:
        rec = model.model_validate(raw)
    except ValidationError as e:
        errors[path] = _format_pydantic(e)
        return None
    rec_id = getattr(rec, id_field)
    if rec_id != path.stem:
        errors.setdefault(path, []).append(
            f"{id_field} '{rec_id}' must match the file name (expected '{path.stem}')."
        )
        return None
    return rec


def load_all():
    errors: dict[Path, list[str]] = {}
    movements: dict[str, MovementSpec] = {}
    watches: dict[str, WatchReference] = {}

    for p in sorted(MOVEMENTS_DIR.glob("*.y*ml")):
        m = _load(p, MovementSpec, "caliber_id", errors)
        if m:
            movements[m.caliber_id] = m

    for p in sorted(WATCHES_DIR.glob("*.y*ml")):
        w = _load(p, WatchReference, "watch_id", errors)
        if not w:
            continue
        if w.caliber_id not in movements and (MOVEMENTS_DIR / f"{w.caliber_id}.yaml") not in errors:
            errors.setdefault(p, []).append(
                f"caliber_id '{w.caliber_id}' has no movement file. "
                f"Create data/movements/{w.caliber_id}.yaml (or fix the spelling)."
            )
            continue
        watches[w.watch_id] = w

    return movements, watches, errors


# ------------------------------------------------------------------- SQLite
SCHEMA_SQL = """
CREATE TABLE movements (
    caliber_id TEXT PRIMARY KEY,
    manufacturer TEXT NOT NULL,
    caliber_number TEXT NOT NULL,
    base_caliber TEXT,
    winding_type TEXT NOT NULL,
    winding_mechanism TEXT NOT NULL,
    escapement_type TEXT NOT NULL,
    frequency_vph INTEGER NOT NULL,
    jewels INTEGER,
    power_reserve_hours REAL,
    hacking INTEGER,
    hand_winding INTEGER NOT NULL,
    description TEXT NOT NULL
);
CREATE TABLE watches (
    watch_id TEXT PRIMARY KEY,
    brand TEXT NOT NULL,
    model_family TEXT NOT NULL,
    model_name TEXT NOT NULL,
    reference_numbers_json TEXT NOT NULL,
    caliber_id TEXT NOT NULL REFERENCES movements(caliber_id),
    production_year_start INTEGER,
    production_year_end INTEGER,
    notes TEXT
);
CREATE TABLE watch_tests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    watch_id TEXT NOT NULL REFERENCES watches(watch_id) ON DELETE CASCADE,
    standard TEXT NOT NULL,
    accuracy_min_spd REAL,
    accuracy_max_spd REAL,
    water_resistance_bar REAL,
    water_resistance_meters INTEGER,
    magnetic_resistance_gauss INTEGER,
    test_notes TEXT
);
CREATE VIEW v_watch_catalog AS
SELECT w.watch_id, w.brand, w.model_family, w.model_name,
       w.reference_numbers_json AS reference_numbers,
       w.production_year_start, w.production_year_end,
       m.manufacturer AS movement_manufacturer, m.caliber_number, m.base_caliber,
       m.winding_type, m.winding_mechanism, m.escapement_type,
       m.frequency_vph, m.jewels, m.power_reserve_hours
FROM watches w JOIN movements m ON w.caliber_id = m.caliber_id;
"""


def _b(v):
    return None if v is None else int(v)


def compile_sqlite(movements, watches) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    conn.executescript(SCHEMA_SQL)
    for m in movements.values():
        conn.execute(
            "INSERT INTO movements VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (m.caliber_id, m.manufacturer, m.caliber_number, m.base_caliber,
             m.winding_type.value, m.winding_mechanism.value, m.escapement_type,
             m.frequency_vph, m.jewels, m.power_reserve_hours,
             _b(m.hacking), _b(m.hand_winding), m.description),
        )
    for w in watches.values():
        conn.execute(
            "INSERT INTO watches VALUES (?,?,?,?,?,?,?,?,?)",
            (w.watch_id, w.brand, w.model_family, w.model_name,
             json.dumps(w.reference_numbers), w.caliber_id,
             w.production_year_start, w.production_year_end, w.notes),
        )
        for t in w.tests_passed:
            lo, hi = t.rated_accuracy_sec_per_day or (None, None)
            conn.execute(
                "INSERT INTO watch_tests (watch_id, standard, accuracy_min_spd, accuracy_max_spd,"
                " water_resistance_bar, water_resistance_meters, magnetic_resistance_gauss, test_notes)"
                " VALUES (?,?,?,?,?,?,?,?)",
                (w.watch_id, t.standard.value, lo, hi, t.water_resistance_bar,
                 t.water_resistance_meters, t.magnetic_resistance_gauss, t.test_notes),
            )
    conn.commit()
    conn.close()


# ------------------------------------------------------------------ HTML page
def _e(v, unit: str = "") -> str:
    if v is None or v == "" or v == []:
        return '<span class="na">—</span>'
    if isinstance(v, bool):
        return "Yes" if v else "No"
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return html.escape(f"{v}{unit}")


def _years(a, b) -> str:
    if a is None and b is None:
        return _e(None)
    return html.escape(f"{a or '?'}–{b or 'present'}")


def _test_summary(t) -> str:
    parts = [t.standard.value]
    if t.rated_accuracy_sec_per_day:
        lo, hi = t.rated_accuracy_sec_per_day
        parts.append(f"{lo:+g}/{hi:+g} s/d")
    if t.water_resistance_meters:
        parts.append(f"{t.water_resistance_meters} m")
    elif t.water_resistance_bar:
        parts.append(f"{t.water_resistance_bar:g} bar")
    if t.magnetic_resistance_gauss:
        parts.append(f"{t.magnetic_resistance_gauss:,} G")
    return html.escape(", ".join(parts))


def generate_html(movements, watches) -> None:
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    w_rows = []
    for w in sorted(watches.values(), key=lambda w: (w.brand, w.model_family, w.model_name)):
        m = movements[w.caliber_id]
        tests = "<br>".join(_test_summary(t) for t in w.tests_passed) or _e(None)
        note = f"<div class=note>{_e(w.notes)}</div>" if w.notes else ""
        w_rows.append(
            f"<tr><td>{_e(w.brand)}</td><td>{_e(w.model_family)}</td><td>{_e(w.model_name)}{note}</td>"
            f"<td>{_e(', '.join(w.reference_numbers))}</td>"
            f"<td><a href='#{m.caliber_id}'>{_e(m.manufacturer + ' ' + m.caliber_number)}</a></td>"
            f"<td>{_years(w.production_year_start, w.production_year_end)}</td><td>{tests}</td></tr>"
        )
    m_rows = []
    for m in sorted(movements.values(), key=lambda m: (m.manufacturer, m.caliber_number)):
        m_rows.append(
            f"<tr id='{m.caliber_id}'><td>{_e(m.manufacturer)}</td><td>{_e(m.caliber_number)}"
            f"<div class=note>{_e(m.description)}</div></td><td>{_e(m.base_caliber)}</td>"
            f"<td>{_e(m.winding_type.value)}</td><td>{_e(m.winding_mechanism.value)}</td>"
            f"<td>{_e(m.escapement_type)}</td><td class=num>{m.frequency_vph:,}</td>"
            f"<td class=num>{_e(m.jewels)}</td><td class=num>{_e(m.power_reserve_hours, ' h')}</td>"
            f"<td>{_e(m.hacking)}</td></tr>"
        )

    page = f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Watch-Agent Horology Database</title>
<style>
:root {{ --bg:#fafaf8; --fg:#1d1d1b; --muted:#6b6b66; --line:#e2e2dc; --head:#f0efe9; --link:#1f5fa8; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#141413; --fg:#e8e6df; --muted:#9a988f; --line:#2e2d2a; --head:#1f1e1c; --link:#7db3ef; }} }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background:var(--bg); color:var(--fg); margin:0; padding:1.5rem 16px; line-height:1.4; }}
main {{ max-width: 1400px; margin: 0 auto; }}
h1 {{ margin:0 0 .25rem; font-size:1.6rem; }} h2 {{ margin-top:2rem; font-size:1.2rem; }}
.meta {{ color:var(--muted); font-size:.9rem; }} a {{ color:var(--link); }}
input {{ font:inherit; padding:.45rem .6rem; width:100%; max-width:420px; box-sizing:border-box; border:1px solid var(--line); border-radius:6px; background:var(--bg); color:var(--fg); margin-top:1rem; }}
.wrap {{ overflow-x:auto; border:1px solid var(--line); border-radius:6px; }}
table {{ border-collapse:collapse; width:100%; font-size:.9rem; }}
th, td {{ padding:.5rem .7rem; text-align:left; vertical-align:top; border-bottom:1px solid var(--line); }}
th {{ background:var(--head); cursor:pointer; white-space:nowrap; }}
.num {{ text-align:right; font-variant-numeric:tabular-nums; white-space:nowrap; }}
.note {{ color:var(--muted); font-size:.82rem; margin-top:.2rem; max-width:48ch; }}
.na {{ color:var(--muted); }} tr:target {{ background:var(--head); }}
</style></head><body><main>
<h1>Watch-Agent Horology Database</h1>
<div class="meta">{len(watches)} watches · {len(movements)} movements · built {stamp} ·
<a href="horology.db">download SQLite</a> ·
<a href="https://lite.datasette.io/?url=https://wdjoyner.github.io/watch-agent/horology.db">query with SQL (Datasette Lite)</a> ·
<a href="https://github.com/wdjoyner/watch-agent">source</a></div>
<input id="q" type="search" placeholder="Filter rows (e.g. Omega, Co-Axial, 28800)…">
<h2>Watches</h2><div class="wrap"><table class="sortable"><thead><tr>
<th>Brand</th><th>Family</th><th>Model</th><th>Reference(s)</th><th>Movement</th><th>Years</th><th>Tests</th>
</tr></thead><tbody>
{chr(10).join(w_rows)}
</tbody></table></div>
<h2>Movements</h2><div class="wrap"><table class="sortable"><thead><tr>
<th>Maker</th><th>Caliber</th><th>Base</th><th>Winding</th><th>Mechanism</th><th>Escapement</th>
<th class=num>vph</th><th class=num>Jewels</th><th class=num>Reserve</th><th>Hacking</th>
</tr></thead><tbody>
{chr(10).join(m_rows)}
</tbody></table></div>
</main>
<script>
document.getElementById('q').addEventListener('input', e => {{
  const q = e.target.value.toLowerCase();
  document.querySelectorAll('tbody tr').forEach(r => r.style.display = r.textContent.toLowerCase().includes(q) ? '' : 'none');
}});
document.querySelectorAll('table.sortable th').forEach((th, i) => th.addEventListener('click', () => {{
  const tb = th.closest('table').tBodies[0], asc = th.dataset.asc !== '1';
  th.closest('tr').querySelectorAll('th').forEach(h => delete h.dataset.asc); th.dataset.asc = asc ? '1' : '0';
  const key = r => {{ const t = r.cells[i].textContent.trim(), n = parseFloat(t.replace(/,/g, '')); return isNaN(n) ? t.toLowerCase() : n; }};
  [...tb.rows].sort((a, b) => {{ const x = key(a), y = key(b); return (x > y ? 1 : x < y ? -1 : 0) * (asc ? 1 : -1); }}).forEach(r => tb.appendChild(r));
}}));
</script></body></html>
"""
    HTML_PATH.write_text(page, encoding="utf-8")


# ---------------------------------------------------------------------- main
def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true", help="validate only; do not write horology.db or index.html")
    args = ap.parse_args()

    movements, watches, errors = load_all()
    if errors:
        print(f"\n[FAILED] {len(errors)} file(s) have problems. Nothing was built.\n", file=sys.stderr)
        for path, msgs in errors.items():
            print(f"  {path.relative_to(ROOT_DIR)}", file=sys.stderr)
            for msg in msgs:
                print(f"      - {msg}", file=sys.stderr)
        print("\nSee docs/YAML_FORMAT.md for the required format.", file=sys.stderr)
        return 1

    print(f"[OK] {len(movements)} movements and {len(watches)} watches are valid.")
    if args.check:
        return 0
    compile_sqlite(movements, watches)
    generate_html(movements, watches)
    print(f"[OK] Wrote {DB_PATH.name} and {HTML_PATH.name}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
