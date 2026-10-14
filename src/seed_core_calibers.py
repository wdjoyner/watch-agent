# src/seed_core_calibers.py
import sys
from pathlib import Path
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR))

from src.schema import MovementSpec, WatchReference

MOVEMENTS = [
    {
        "caliber_id": "eta_6497_1",
        "manufacturer": "ETA / Unitas",
        "caliber_number": "6497-1",
        "winding_type": "Manual",
        "winding_mechanism": "None (Manual)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 18000,
        "jewels": 17,
        "power_reserve_hours": 46.0,
        "diameter_mm": 36.6,
        "height_mm": 4.5,
        "functions": ["Hours", "Minutes", "Small Seconds at 9"],
        "description": "Classic 16.5-ligne hunter pocket watch ebauche featuring a robust three-tier architecture with traditional click spring, crown wheel, and ratchet wheel layout."
    },
    {
        "caliber_id": "seagull_st3600",
        "manufacturer": "Tianjin Sea-Gull",
        "caliber_number": "ST3600",
        "winding_type": "Manual",
        "winding_mechanism": "None (Manual)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 21600,
        "jewels": 17,
        "power_reserve_hours": 45.0,
        "diameter_mm": 36.6,
        "height_mm": 4.5,
        "functions": ["Hours", "Minutes", "Small Seconds at 9"],
        "description": "21,600 vph architectural clone of the Unitas 6497 with three-tier bridge topology ideal for custom watch builds and servicing practice."
    },
    {
        "caliber_id": "omega_1120",
        "manufacturer": "Omega",
        "caliber_number": "1120",
        "winding_type": "Automatic",
        "winding_mechanism": "Bidirectional (Reversing Wheels)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 28800,
        "jewels": 23,
        "power_reserve_hours": 44.0,
        "diameter_mm": 25.6,
        "height_mm": 3.6,
        "functions": ["Hours", "Minutes", "Central Seconds", "Quickset Date", "Hacking"],
        "description": "Heavily refined derivative of the ETA 2892-A2 featuring a rhodium-plated finish, redesigned automatic bridge, and two additional jewels."
    },
    {
        "caliber_id": "valjoux_72",
        "manufacturer": "Valjoux",
        "caliber_number": "72",
        "winding_type": "Manual",
        "winding_mechanism": "None (Manual)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 18000,
        "jewels": 17,
        "power_reserve_hours": 46.0,
        "diameter_mm": 29.5,
        "height_mm": 6.25,
        "functions": ["Hours", "Minutes", "Small Seconds", "12-Hour Column-Wheel Chronograph"],
        "description": "Historic 13-ligne lateral-clutch, 9-pillar column-wheel chronograph movement used in vintage Rolex Daytona, Heuer Carrera, and Breitling Navitimer references."
    },
    {
        "caliber_id": "seiko_7s26",
        "manufacturer": "Seiko",
        "caliber_number": "7S26",
        "winding_type": "Automatic",
        "winding_mechanism": "Bidirectional (Seiko Magic Lever)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 21600,
        "jewels": 21,
        "power_reserve_hours": 41.0,
        "diameter_mm": 27.4,
        "height_mm": 4.9,
        "functions": ["Hours", "Minutes", "Central Seconds", "Day", "Date"],
        "description": "Workhorse automatic caliber utilizing Seiko's 1959 V-shaped Magic Lever bidirectional pawl-winding system with minimal moving parts."
    },
    {
        "caliber_id": "seiko_4r36",
        "manufacturer": "Seiko",
        "caliber_number": "4R36 (NH36)",
        "winding_type": "Automatic",
        "winding_mechanism": "Bidirectional (Seiko Magic Lever)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 21600,
        "jewels": 24,
        "power_reserve_hours": 41.0,
        "diameter_mm": 27.4,
        "height_mm": 5.32,
        "functions": ["Hours", "Minutes", "Central Seconds", "Day", "Date", "Hacking", "Hand-Winding"],
        "description": "Modernized Magic Lever automatic architecture adding manual crown winding and stop-seconds (hacking) to the classic 7S26 foundation."
    },
    {
        "caliber_id": "iwc_8541",
        "manufacturer": "IWC",
        "caliber_number": "8541",
        "winding_type": "Automatic",
        "winding_mechanism": "Bidirectional (Pellaton Pawl)",
        "escapement_type": "Swiss Lever",
        "frequency_vph": 19800,
        "jewels": 25,
        "power_reserve_hours": 44.0,
        "diameter_mm": 28.0,
        "height_mm": 5.9,
        "functions": ["Hours", "Minutes", "Central Seconds", "Date", "Hacking"],
        "description": "Albert Pellaton's heart-cam and dual-pulling ruby-roller rocker pawl winding architecture."
    }
]

WATCHES = [
    {
        "watch_id": "omega_seamaster_2531_80",
        "brand": "Omega",
        "model_name": "Seamaster Professional 300M Chronometer",
        "model_family": "Seamaster Diver 300M",
        "reference_numbers": ["2531.80.00"],
        "caliber_id": "omega_1120",
        "production_year_start": 1993,
        "production_year_end": 2006,
        "case_diameter_mm": 41.0,
        "tests_passed": [
            {
                "standard": "COSC (ISO 3159)",
                "accuracy_min_spd": -4.0,
                "accuracy_max_spd": 6.0,
                "water_resistance_bar": 30.0,
                "magnetic_resistance_gauss": 60.0,
                "notes": "Official Swiss Chronometer certification with helium escape valve."
            },
            {
                "standard": "ISO 6425 Diver",
                "accuracy_min_spd": None,
                "accuracy_max_spd": None,
                "water_resistance_bar": 30.0,
                "magnetic_resistance_gauss": None,
                "notes": "300m / 1000ft professional diving rating."
            }
        ]
    },
    {
        "watch_id": "rolex_daytona_6263",
        "brand": "Rolex",
        "model_name": "Oyster Cosmograph Daytona",
        "model_family": "Cosmograph Daytona",
        "reference_numbers": ["6263", "6265"],
        "caliber_id": "valjoux_72",
        "production_year_start": 1971,
        "production_year_end": 1987,
        "case_diameter_mm": 37.0,
        "tests_passed": [
            {
                "standard": "COSC (ISO 3159)",
                "accuracy_min_spd": -4.0,
                "accuracy_max_spd": 6.0,
                "water_resistance_bar": 5.0,
                "magnetic_resistance_gauss": None,
                "notes": "Powered by Rolex Caliber 727 (heavily modified Valjoux 72 uprated to 21,600 vph)."
            }
        ]
    },
    {
        "watch_id": "seiko_skx007",
        "brand": "Seiko",
        "model_name": "Prospex Diver Automatic",
        "model_family": "SKX Series",
        "reference_numbers": ["SKX007K", "SKX007J", "7S26-0020"],
        "caliber_id": "seiko_7s26",
        "production_year_start": 1996,
        "production_year_end": 2019,
        "case_diameter_mm": 42.5,
        "tests_passed": [
            {
                "standard": "ISO 6425 Diver",
                "accuracy_min_spd": -20.0,
                "accuracy_max_spd": 40.0,
                "water_resistance_bar": 20.0,
                "magnetic_resistance_gauss": 60.0,
                "notes": "200m ISO-certified diver's watch."
            }
        ]
    },
    {
        "watch_id": "iwc_ingenieur_866",
        "brand": "IWC",
        "model_name": "Ingenieur Automatic",
        "model_family": "Ingenieur",
        "reference_numbers": ["866", "866A", "866AD"],
        "caliber_id": "iwc_8541",
        "production_year_start": 1967,
        "production_year_end": 1976,
        "case_diameter_mm": 37.0,
        "tests_passed": [
            {
                "standard": "DIN 8309 Antimagnetic",
                "accuracy_min_spd": -2.0,
                "accuracy_max_spd": 5.0,
                "water_resistance_bar": 10.0,
                "magnetic_resistance_gauss": 1000.0,
                "notes": "Soft-iron inner Faraday cage rated to 80,000 A/m (~1,000 Gauss)."
            }
        ]
    }
]


def seed_all() -> None:
    mov_dir = ROOT_DIR / "data" / "movements"
    wat_dir = ROOT_DIR / "data" / "watches"
    mov_dir.mkdir(parents=True, exist_ok=True)
    wat_dir.mkdir(parents=True, exist_ok=True)

    for m_data in MOVEMENTS:
        validated = MovementSpec(**m_data)
        out_path = mov_dir / f"{validated.caliber_id}.yaml"
        out_path.write_text(
            yaml.safe_dump(validated.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8"
        )
        print(f"[SEEDED MOVEMENT] {out_path.relative_to(ROOT_DIR)}")

    for w_data in WATCHES:
        validated = WatchReference(**w_data)
        out_path = wat_dir / f"{validated.watch_id}.yaml"
        out_path.write_text(
            yaml.safe_dump(validated.model_dump(mode="json"), sort_keys=False, allow_unicode=True),
            encoding="utf-8"
        )
        print(f"[SEEDED WATCH]    {out_path.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    seed_all()
