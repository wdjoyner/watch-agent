# src/build_db.py
import json
import sqlite3
import sys
from pathlib import Path
from typing import Dict, List
import yaml
from pydantic import ValidationError

from schema import MovementSpec, WatchReference

ROOT_DIR = Path(__file__).resolve().parent.parent
MOVEMENTS_DIR = ROOT_DIR / "data" / "movements"
WATCHES_DIR = ROOT_DIR / "data" / "watches"
DB_PATH = ROOT_DIR / "horology.db"


def load_movements() -> Dict[str, MovementSpec]:
    movements: Dict[str, MovementSpec] = {}
    if not MOVEMENTS_DIR.exists():
        return movements

    for yaml_path in sorted(MOVEMENTS_DIR.glob("*.y*ml")):
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
        try:
            spec = MovementSpec.model_validate(raw_data)
        except ValidationError as e:
            print(f"[ERROR] Validation failed in {yaml_path.name}:\n{e}", file=sys.stderr)
            sys.exit(1)

        if spec.caliber_id in movements:
            print(f"[ERROR] Duplicate caliber_id '{spec.caliber_id}' in {yaml_path.name}", file=sys.stderr)
            sys.exit(1)

        movements[spec.caliber_id] = spec
    return movements


def load_watches(valid_calibers: Dict[str, MovementSpec]) -> List[WatchReference]:
    watches: List[WatchReference] = []
    seen_ids = set()
    if not WATCHES_DIR.exists():
        return watches

    for yaml_path in sorted(WATCHES_DIR.glob("*.y*ml")):
        with open(yaml_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
        try:
            watch = WatchReference.model_validate(raw_data)
        except ValidationError as e:
            print(f"[ERROR] Validation failed in {yaml_path.name}:\n{e}", file=sys.stderr)
            sys.exit(1)

        if watch.watch_id in seen_ids:
            print(f"[ERROR] Duplicate watch_id '{watch.watch_id}' in {yaml_path.name}", file=sys.stderr)
            sys.exit(1)

        if watch.caliber_id not in valid_calibers:
            print(
                f"[ERROR] Watch '{watch.watch_id}' ({yaml_path.name}) references unknown "
                f"caliber_id '{watch.caliber_id}'. Create data/movements/{watch.caliber_id}.yaml first.",
                file=sys.stderr,
            )
            sys.exit(1)

        seen_ids.add(watch.watch_id)
        watches.append(watch)
    return watches


def compile_sqlite(movements: Dict[str, MovementSpec], watches: List[WatchReference]) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()

    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cur = conn.cursor()

    cur.executescript(
        """
        CREATE TABLE movements (
            caliber_id TEXT PRIMARY KEY,
            manufacturer TEXT NOT NULL,
            caliber_number TEXT NOT NULL,
            base_caliber TEXT,
            winding_type TEXT NOT NULL,
            winding_mechanism TEXT NOT NULL,
            escapement_type TEXT NOT NULL,
            frequency_vph INTEGER NOT NULL,
            jewels INTEGER NOT NULL,
            power_reserve_hours REAL NOT NULL,
            hacking INTEGER NOT NULL,
            hand_winding INTEGER NOT NULL,
            description TEXT NOT NULL
        );

        CREATE TABLE watches (
            watch_id TEXT PRIMARY KEY,
            brand TEXT NOT NULL,
            model_family TEXT NOT NULL,
            model_name TEXT NOT NULL,
            reference_numbers_json TEXT NOT NULL,
            caliber_id TEXT NOT NULL,
            production_year_start INTEGER,
            production_year_end INTEGER,
            notes TEXT,
            FOREIGN KEY (caliber_id) REFERENCES movements(caliber_id)
        );

        CREATE TABLE watch_tests (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            watch_id TEXT NOT NULL,
            standard TEXT NOT NULL,
            accuracy_min_spd REAL,
            accuracy_max_spd REAL,
            water_resistance_bar REAL,
            water_resistance_meters INTEGER,
            magnetic_resistance_gauss INTEGER,
            test_notes TEXT,
            FOREIGN KEY (watch_id) REFERENCES watches(watch_id) ON DELETE CASCADE
        );

        CREATE VIEW v_watch_catalog AS
        SELECT
            w.watch_id,
            w.brand,
            w.model_family,
            w.model_name,
            w.reference_numbers_json AS reference_numbers,
            w.production_year_start,
            w.production_year_end,
            m.manufacturer AS movement_manufacturer,
            m.caliber_number,
            m.base_caliber,
            m.winding_type,
            m.winding_mechanism,
            m.escapement_type,
            m.frequency_vph,
            m.jewels,
            m.power_reserve_hours
        FROM watches w
        JOIN movements m ON w.caliber_id = m.caliber_id;
        """
    )

    for m in movements.values():
        cur.execute(
            """
            INSERT INTO movements VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                m.caliber_id,
                m.manufacturer,
                m.caliber_number,
                m.base_caliber,
                m.winding_type.value,
                m.winding_mechanism.value,
                m.escapement_type,
                m.frequency_vph,
                m.jewels,
                m.power_reserve_hours,
                int(m.hacking),
                int(m.hand_winding),
                m.description,
            ),
        )

    for w in watches:
        cur.execute(
            """
            INSERT INTO watches VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                w.watch_id,
                w.brand,
                w.model_family,
                w.model_name,
                json.dumps(w.reference_numbers),
                w.caliber_id,
                w.production_year_start,
                w.production_year_end,
                w.notes,
            ),
        )
        for t in w.tests_passed:
            acc_min, acc_max = t.rated_accuracy_sec_per_day if t.rated_accuracy_sec_per_day else (None, None)
            cur.execute(
                """
                INSERT INTO watch_tests (
                    watch_id, standard, accuracy_min_spd, accuracy_max_spd,
                    water_resistance_bar, water_resistance_meters,
                    magnetic_resistance_gauss, test_notes
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    w.watch_id,
                    t.standard.value,
                    acc_min,
                    acc_max,
                    t.water_resistance_bar,
                    t.water_resistance_meters,
                    t.magnetic_resistance_gauss,
                    t.test_notes,
                ),
            )

    conn.commit()
    conn.close()


def main() -> None:
    movements = load_movements()
    watches = load_watches(movements)
    compile_sqlite(movements, watches)
    print(
        f"[SUCCESS] Built {DB_PATH.name}: {len(movements)} movement(s), {len(watches)} watch reference(s)."
    )


if __name__ == "__main__":
    main()
