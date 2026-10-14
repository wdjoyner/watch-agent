import sqlite3
import yaml
from pathlib import Path

DB_PATH = "horology.db"
MOVEMENTS_DIR = Path("data/movements")
WATCHES_DIR = Path("data/watches")

def build_database():
    if Path(DB_PATH).exists():
        Path(DB_PATH).unlink()
        
    conn = sqlite3.connect(DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON;")
    cursor = conn.cursor()
    
    # Create tables
    cursor.execute("""
    CREATE TABLE movements (
        caliber_id TEXT PRIMARY KEY,
        manufacturer TEXT NOT NULL,
        family TEXT,
        winding_type TEXT NOT NULL,
        winding_mechanism TEXT NOT NULL,
        escapement_type TEXT NOT NULL,
        frequency_vph INTEGER NOT NULL,
        jewels INTEGER NOT NULL,
        power_reserve_hrs INTEGER NOT NULL,
        diameter_mm REAL NOT NULL,
        height_mm REAL NOT NULL,
        notes TEXT
    );
    """)
    
    cursor.execute("""
    CREATE TABLE watches (
        watch_id TEXT PRIMARY KEY,
        brand TEXT NOT NULL,
        model TEXT NOT NULL,
        family TEXT,
        reference_number TEXT,
        caliber_id TEXT NOT NULL,
        case_diameter_mm REAL NOT NULL,
        FOREIGN KEY (caliber_id) REFERENCES movements(caliber_id)
    );
    """)
    
    # Insert movements
    for yml_file in MOVEMENTS_DIR.glob("*.yaml"):
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        cursor.execute("""
        INSERT INTO movements (caliber_id, manufacturer, family, winding_type, winding_mechanism, escapement_type, frequency_vph, jewels, power_reserve_hrs, diameter_mm, height_mm, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("caliber_id"),
            data.get("manufacturer"),
            data.get("family"),
            data.get("winding_type"),
            data.get("winding_mechanism"),
            data.get("escapement_type"),
            data.get("frequency_vph"),
            data.get("jewels"),
            data.get("power_reserve_hrs"),
            data.get("diameter_mm"),
            data.get("height_mm"),
            data.get("notes")
        ))
        
    # Insert watches
    for yml_file in WATCHES_DIR.glob("*.yaml"):
        data = yaml.safe_load(yml_file.read_text(encoding="utf-8"))
        cursor.execute("""
        INSERT INTO watches (watch_id, brand, model, family, reference_number, caliber_id, case_diameter_mm)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            data.get("watch_id"),
            data.get("brand"),
            data.get("model"),
            data.get("family"),
            data.get("reference_number"),
            data.get("caliber_id"),
            data.get("case_diameter_mm")
        ))
        
    conn.commit()
    conn.close()
    print("[OK] Database built successfully from YAML records.")

def generate_html_index():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT watch_id, brand, model, family, reference_number, caliber_id, case_diameter_mm FROM watches")
    watches = cursor.fetchall()
    
    cursor.execute("SELECT caliber_id, manufacturer, family, winding_type, frequency_vph, power_reserve_hrs FROM movements")
    movements = cursor.fetchall()
    conn.close()

    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Watch-Agent Horology Database</title>
  <style>
    body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #121212; color: #e0e0e0; margin: 0; padding: 2rem; }
    h1, h2 { color: #ffffff; border-bottom: 1px solid #333; padding-bottom: 0.5rem; }
    table { width: 100%; border-collapse: collapse; margin-bottom: 2rem; background: #1e1e1e; border-radius: 6px; overflow: hidden; }
    th, td { padding: 12px 16px; text-align: left; border-bottom: 1px solid #2a2a2a; }
    th { background: #252525; color: #ffffff; font-weight: 600; }
    tr:hover { background: #2a2a2a; }
    .footer { margin-top: 3rem; text-align: center; color: #777; font-size: 0.9rem; }
  </style>
</head>
<body>
  <h1>Watch-Agent Horology Database</h1>
  <p>Local SQLite-backed mechanical watch and movement registry.</p>

  <h2>Reference Watches</h2>
  <table>
    <tr><th>Watch ID</th><th>Brand</th><th>Model</th><th>Family</th><th>Reference</th><th>Caliber</th><th>Diameter</th></tr>
"""
    for w in watches:
        html += f"    <tr><td><code>{w[0]}</code></td><td>{w[1]}</td><td>{w[2]}</td><td>{w[3] or '-'}</td><td>{w[4] or '-'}</td><td><code>{w[5]}</code></td><td>{w[6]} mm</td></tr>\n"

    html += """  </table>

  <h2>Movement Calibers</h2>
  <table>
    <tr><th>Caliber ID</th><th>Manufacturer</th><th>Family</th><th>Winding</th><th>Frequency</th><th>Power Reserve</th></tr>
"""
    for m in movements:
        html += f"    <tr><td><code>{m[0]}</code></td><td>{m[1]}</td><td>{m[2] or '-'}</td><td>{m[3]}</td><td>{m[4]} vph</td><td>{m[5]} hrs</td></tr>\n"

    html += """  </table>

  <div class="footer">
    <p>Generated automatically via Python Pydantic pipeline &bull; <a href="horology.db" style="color: #4da6ff;">Download SQLite DB</a></p>
  </div>
</body>
</html>
"""
    Path("index.html").write_text(html, encoding="utf-8")
    print("[OK] Generated static index.html successfully.")

if __name__ == "__main__":
    build_database()
    generate_html_index()
