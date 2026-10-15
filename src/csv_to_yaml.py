# src/csv_to_yaml.py
"""
Turn spreadsheet rows into YAML record files in data/.

Fill in templates/movements.csv and/or templates/watches.csv (in Numbers,
Excel, or any text editor), export/save as CSV, then run:

    python3 src/csv_to_yaml.py templates/movements.csv templates/watches.csv
    python3 src/csv_to_yaml.py --dry-run templates/movements.csv   # preview only

The file type is detected from the header (caliber_id -> movements,
watch_id -> watches), so the CSV files can have any name.

Spreadsheet conventions
  * Leave a cell blank when the value is unknown (it becomes null).
  * Yes/no columns accept yes, no, true, false, y, n, 1, 0.
  * Enum values (winding_type, winding_mechanism, test_standard) are matched
    ignoring capitals. winding_mechanism may be left blank for a Manual movement.
  * reference_numbers: separate several numbers with a semicolon, e.g. 2254.50.00; 2254.50
  * test_accuracy: min/max seconds per day, e.g. -4/+6
  * A watch with several certifications: repeat the watch_id on extra rows and
    fill in only the test_* columns there.

Every record is checked against src/schema.py before anything is written.
If any row has a problem, all problems are listed and no files are written.
Existing YAML files are never overwritten unless --overwrite is given.
"""
import argparse
import csv
import sys
from pathlib import Path

import yaml
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parent))
from schema import (  # noqa: E402
    AutoWindingMechanism,
    CertificationStandard,
    MovementSpec,
    WatchReference,
    WindingType,
)

ROOT_DIR = Path(__file__).resolve().parent.parent
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"

TEST_COLUMNS = {
    "test_standard", "test_accuracy", "test_water_bar",
    "test_water_m", "test_gauss", "test_notes",
}


class RowError(Exception):
    pass


_cell_errors: list[str] = []   # problems found while parsing the current row


def _soft(fn, *a):
    """Run a cell parser; record its problem and return None instead of stopping."""
    try:
        return fn(*a)
    except RowError as e:
        _cell_errors.append(str(e))
        return None


# ----------------------------------------------------------- cell parsing
def _clean(v):
    if v is None:
        return None
    v = v.strip()
    return v or None


def _bool(v, col):
    if v is None:
        return None
    t = v.lower()
    if t in ("yes", "y", "true", "t", "1"):
        return True
    if t in ("no", "n", "false", "f", "0"):
        return False
    raise RowError(f"{col}: expected yes/no, got {v!r}")


def _num(v, col, kind=float):
    if v is None:
        return None
    try:
        x = float(v.replace(",", "").replace("+", ""))
    except ValueError:
        raise RowError(f"{col}: expected a number, got {v!r}")
    if kind is int:
        if not x.is_integer():
            raise RowError(f"{col}: expected a whole number, got {v!r}")
        return int(x)
    return x


def _enum(v, enum_cls, col):
    if v is None:
        return None
    for member in enum_cls:
        if member.value.lower() == v.lower():
            return member.value
    allowed = ", ".join(f"'{m.value}'" for m in enum_cls)
    raise RowError(f"{col}: {v!r} is not one of {allowed}")


def _accuracy(v):
    if v is None:
        return None
    parts = [p.strip() for p in v.replace(" to ", "/").split("/")]
    if len(parts) != 2:
        raise RowError(f"test_accuracy: expected min/max like -4/+6, got {v!r}")
    return [_num(parts[0], "test_accuracy"), _num(parts[1], "test_accuracy")]


# --------------------------------------------------------- row -> record
def movement_from_row(r):
    winding_type = _soft(_enum, r.get("winding_type"), WindingType, "winding_type")
    mech = _soft(_enum, r.get("winding_mechanism"), AutoWindingMechanism, "winding_mechanism")
    if mech is None and winding_type == WindingType.MANUAL.value:
        mech = AutoWindingMechanism.NONE.value
    rec = {
        "caliber_id": r.get("caliber_id"),
        "manufacturer": r.get("manufacturer"),
        "caliber_number": r.get("caliber_number"),
        "base_caliber": r.get("base_caliber"),
        "winding_type": winding_type,
        "winding_mechanism": mech,
        "escapement_type": r.get("escapement_type") or "Swiss Lever",
        "frequency_vph": _soft(_num, r.get("frequency_vph"), "frequency_vph", int),
        "jewels": _soft(_num, r.get("jewels"), "jewels", int),
        "power_reserve_hours": _soft(_num, r.get("power_reserve_hours"), "power_reserve_hours"),
        "hacking": _soft(_bool, r.get("hacking"), "hacking"),
        "hand_winding": _soft(_bool, r.get("hand_winding"), "hand_winding"),
        "description": r.get("description"),
    }
    if rec["hand_winding"] is None:
        rec["hand_winding"] = True
    return rec


def test_from_row(r):
    if not any(r.get(c) for c in TEST_COLUMNS):
        return None
    return {
        "standard": _soft(_enum, r.get("test_standard"), CertificationStandard, "test_standard"),
        "rated_accuracy_sec_per_day": _soft(_accuracy, r.get("test_accuracy")),
        "water_resistance_bar": _soft(_num, r.get("test_water_bar"), "test_water_bar"),
        "water_resistance_meters": _soft(_num, r.get("test_water_m"), "test_water_m", int),
        "magnetic_resistance_gauss": _soft(_num, r.get("test_gauss"), "test_gauss", int),
        "test_notes": r.get("test_notes"),
    }


def watch_from_row(r):
    refs = r.get("reference_numbers")
    return {
        "watch_id": r.get("watch_id"),
        "brand": r.get("brand"),
        "model_family": r.get("model_family"),
        "model_name": r.get("model_name"),
        "reference_numbers": [x.strip() for x in refs.split(";") if x.strip()] if refs else [],
        "caliber_id": r.get("caliber_id"),
        "production_year_start": _soft(_num, r.get("production_year_start"), "production_year_start", int),
        "production_year_end": _soft(_num, r.get("production_year_end"), "production_year_end", int),
        "tests_passed": [],
        "notes": r.get("notes"),
    }


# ---------------------------------------------------------------- reading
def read_csv(path: Path):
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        headers = [h.strip() for h in (reader.fieldnames or [])]
        rows = []
        for lineno, raw in enumerate(reader, start=2):
            row = {(k or "").strip(): _clean(v) for k, v in raw.items()}
            if any(row.values()):
                rows.append((lineno, row))
    return headers, rows


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv_files", nargs="+", type=Path)
    ap.add_argument("--dry-run", action="store_true", help="check and list what would be written, but write nothing")
    ap.add_argument("--overwrite", action="store_true", help="replace YAML files that already exist")
    args = ap.parse_args()

    errors: list[str] = []
    bad_cells: dict[str, set[str]] = {}   # columns already reported per row
    movements: dict[str, tuple[str, dict]] = {}
    watches: dict[str, tuple[str, dict]] = {}

    for path in args.csv_files:
        if not path.exists():
            errors.append(f"{path}: file not found")
            continue
        headers, rows = read_csv(path)
        if "caliber_id" in headers and "watch_id" not in headers:
            kind = "movement"
        elif "watch_id" in headers:
            kind = "watch"
        else:
            errors.append(f"{path}: header must contain caliber_id (movements) or watch_id (watches)")
            continue

        for lineno, r in rows:
            where = f"{path.name} line {lineno}"
            _cell_errors.clear()
            try:
                if kind == "movement":
                    rec = movement_from_row(r)
                    if rec["caliber_id"] in movements:
                        raise RowError(f"caliber_id '{rec['caliber_id']}' appears twice")
                    movements[rec["caliber_id"]] = (where, rec)
                else:
                    wid = r.get("watch_id")
                    test = test_from_row(r)
                    if wid in watches and not any(
                        r.get(c) for c in r if c not in TEST_COLUMNS and c != "watch_id"
                    ):
                        # continuation row: extra certification for the same watch
                        if test:
                            watches[wid][1]["tests_passed"].append(test)
                        continue
                    if wid in watches:
                        raise RowError(
                            f"watch_id '{wid}' appears twice; extra rows for the same watch "
                            "should fill in only the test_* columns"
                        )
                    rec = watch_from_row(r)
                    if test:
                        rec["tests_passed"].append(test)
                    watches[wid] = (where, rec)
            except RowError as e:
                errors.append(f"{where}: {e}")
            for msg in _cell_errors:
                errors.append(f"{where}: {msg}")
            if _cell_errors:
                bad_cells.setdefault(where, set()).update(m.split(":")[0] for m in _cell_errors)

    # Validate with the real schema and prepare output
    existing_calibers = {p.stem for p in MOVEMENTS_DIR.glob("*.yaml")}
    outputs: list[tuple[Path, dict]] = []
    for model, items, out_dir, id_field in (
        (MovementSpec, movements, MOVEMENTS_DIR, "caliber_id"),
        (WatchReference, watches, WATCHES_DIR, "watch_id"),
    ):
        for rec_id, (where, rec) in items.items():
            try:
                obj = model.model_validate(rec)
            except ValidationError as e:
                for err in e.errors():
                    loc = ".".join(str(x) for x in err["loc"])
                    col = {"standard": "test_standard", "rated_accuracy_sec_per_day": "test_accuracy"}.get(
                        str(err["loc"][-1]) if err["loc"] else "", loc)
                    if loc in bad_cells.get(where, ()) or col in bad_cells.get(where, ()):
                        continue  # already reported with the cell's own message
                    errors.append(f"{where} ({rec_id}): {loc}: {err['msg']}")
                continue
            if model is WatchReference and obj.caliber_id not in existing_calibers | set(movements):
                errors.append(
                    f"{where} ({rec_id}): caliber_id '{obj.caliber_id}' has no movement; "
                    "add it to the movements spreadsheet or data/movements/ first"
                )
                continue
            outputs.append((out_dir / f"{getattr(obj, id_field)}.yaml", obj.model_dump(mode="json")))

    if errors:
        print(f"\n[FAILED] {len(errors)} problem(s). No files were written.\n", file=sys.stderr)
        for e in errors:
            print(f"  - {e}", file=sys.stderr)
        return 1

    written = skipped = 0
    for out_path, data in outputs:
        rel = out_path.relative_to(ROOT_DIR)
        if out_path.exists() and not args.overwrite:
            print(f"  skip   {rel} (already exists; use --overwrite to replace)")
            skipped += 1
            continue
        if args.dry_run:
            print(f"  would write {rel}")
            continue
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, default_flow_style=False, width=88),
            encoding="utf-8",
        )
        print(f"  wrote  {rel}")
        written += 1

    verb = "would be written" if args.dry_run else "written"
    count = len(outputs) - skipped if args.dry_run else written
    print(f"\n[OK] {count} file(s) {verb}, {skipped} skipped.")
    if not args.dry_run and written:
        print("Next: python3 src/build_db.py --check, then commit and push.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
