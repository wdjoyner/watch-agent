# src/export_latex.py
import json
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
DB_PATH = ROOT_DIR / "horology.db"
OUTPUT_TEX = ROOT_DIR / "horology_catalog.tex"


def escape_tex(text: object) -> str:
    """Escape special LaTeX characters in database strings."""
    if text is None:
        return ""
    s = str(text)
    replacements = {
        "\\": r"\textbackslash{}",
        "&": r"\&",
        "%": r"\%",
        "$": r"\$",
        "#": r"\#",
        "_": r"\_",
        "{": r"\{",
        "}": r"\}",
        "~": r"\textasciitilde{}",
        "^": r"\textasciicircum{}",
    }
    for char, escaped in replacements.items():
        s = s.replace(char, escaped)
    return s


def encode_winding(winding_type: str | None, mechanism: str | None) -> str:
    """Map verbose winding descriptions to 2-4 char horological codes."""
    w = (winding_type or "").strip().lower()
    m = (mechanism or "").strip().lower()
    if w == "manual":
        return "MW"
    if "magic lever" in m:
        return "A-ML"
    if "revers" in m:
        return "A-RG"
    if "pellaton" in m or "pawl" in m:
        return "A-PW"
    if "unidirect" in m:
        return "A-UN"
    if "bidirect" in m:
        return "A-BI"
    if w == "automatic":
        return "AUTO"
    return escape_tex(winding_type or "—")


def encode_escapement(escapement: str | None) -> str:
    """Map escapement names to 2-3 char codes."""
    e = (escapement or "").strip().lower()
    if "swiss" in e:
        return "SL"
    if "co-axial" in e or "coaxial" in e:
        return "CX"
    if "chronergy" in e:
        return "CH"
    if "detent" in e:
        return "DT"
    if "cylinder" in e:
        return "CYL"
    return escape_tex((escapement or "—")[:4].upper())


def encode_standard(standard: str | None) -> str:
    """Map certification standards to compact codes."""
    s = (standard or "").strip().upper()
    if "COSC" in s or "3159" in s:
        return "COSC"
    if "METAS" in s:
        return "MET"
    if "6425" in s or "8306" in s or "DIVER" in s:
        return "ISO-D"
    if "GEN" in s:
        return "GVA"
    if "JLC" in s or "1000" in s:
        return "1000H"
    return escape_tex((standard or "")[:6])


def generate_latex() -> None:
    if not DB_PATH.exists():
        print(f"[ERROR] Database {DB_PATH} not found. Run src/build_db.py first.", file=sys.stderr)
        sys.exit(1)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    movements = cur.execute("SELECT * FROM movements ORDER BY manufacturer, caliber_number;").fetchall()
    watches = cur.execute("SELECT * FROM watches ORDER BY brand, model_name;").fetchall()
    tests = cur.execute("SELECT * FROM watch_tests;").fetchall()

    conn.close()

    latex_content = r"""\documentclass[10pt,letterpaper]{article}
\usepackage[margin=0.75in]{geometry}
\usepackage[T1]{fontenc}
\usepackage{booktabs}
\usepackage{longtable}
\usepackage{array}
\usepackage{hyperref}
\usepackage{microtype}

\newcolumntype{L}[1]{>{\raggedright\arraybackslash}p{#1}}

\title{Mechanical Horology Database Catalog}
\author{Watch-Agent Automated Archivist}
\date{\today}

\begin{document}
\maketitle

\section*{Nomenclature \& Technical Code Legend}
To maintain compact, readable specification tables, winding mechanisms, escapements, and certification standards are denoted by the following alphanumeric codes:

\vspace{0.5em}
\noindent
\begin{tabular}{@{}ll@{\hspace{2.5em}}ll@{\hspace{2.5em}}ll@{}}
\toprule
\multicolumn{2}{@{}l}{\textbf{Winding (\texttt{Wnd})}} & \multicolumn{2}{l}{\textbf{Escapement (\texttt{Esc})}} & \multicolumn{2}{l}{\textbf{Certification (\texttt{Cert})}} \\
\midrule
\texttt{MW}   & Manual Wind                & \texttt{SL}  & Swiss Lever       & \texttt{COSC}  & ISO 3159 Chronometer \\
\texttt{A-ML} & Auto (Seiko Magic Lever)   & \texttt{CX}  & Co-Axial          & \texttt{MET}   & METAS Master Chronometer \\
\texttt{A-RG} & Auto (Reverser Gears)      & \texttt{CH}  & Chronergy         & \texttt{ISO-D} & ISO 6425 / DIN 8306 Diver \\
\texttt{A-PW} & Auto (Pawl / Pellaton)     & \texttt{DT}  & Detent            & \texttt{GVA}   & Poin\c{c}on de Gen\`{e}ve \\
\texttt{A-UN} & Auto (Unidirectional)      & \texttt{CYL} & Cylinder          & \texttt{—}     & Uncertified / Standard \\
\texttt{A-BI} & Auto (Bidirectional)       &              &                   &                & \\
\bottomrule
\end{tabular}

\vspace{1em}

\section{Movement Specifications}
\noindent Index of mechanical and automatic calibers, winding architectures, escapements, and beat rates.

{\small
\setlength{\tabcolsep}{5pt}
\begin{longtable}{@{}l L{4.2cm} c c r r r@{}}
\toprule
\textbf{Caliber ID} & \textbf{Manufacturer \& Caliber} & \textbf{Wnd} & \textbf{Esc} & \textbf{Freq (vph)} & \textbf{Jwl} & \textbf{Pwr (h)} \\
\midrule
\endfirsthead
\toprule
\textbf{Caliber ID} & \textbf{Manufacturer \& Caliber} & \textbf{Wnd} & \textbf{Esc} & \textbf{Freq (vph)} & \textbf{Jwl} & \textbf{Pwr (h)} \\
\midrule
\endhead
\bottomrule
\endfoot
"""

    for m in movements:
        cal_id = escape_tex(m["caliber_id"])
        mfg_model = f"{escape_tex(m['manufacturer'])} {escape_tex(m['caliber_number'])}"
        wnd_code = encode_winding(m["winding_type"], m["winding_mechanism"])
        esc_code = encode_escapement(m["escapement_type"])
        freq = f"{int(m['frequency_vph']):,}"
        jewels = str(m["jewels"])
        pwr = f"{float(m['power_reserve_hours']):.0f}"

        latex_content += (
            f"\\texttt{{{cal_id}}} & {mfg_model} & "
            f"\\texttt{{{wnd_code}}} & \\texttt{{{esc_code}}} & {freq} & {jewels} & {pwr} \\\\\n"
        )

    latex_content += r"""\end{longtable}
}

\section{Watch References \& Certifications}
\noindent Tracked wristwatch references, production eras, and passed test standards.

{\small
\setlength{\tabcolsep}{5pt}
\begin{longtable}{@{}L{4.0cm} L{3.6cm} l c l@{}}
\toprule
\textbf{Brand \& Model} & \textbf{References} & \textbf{Caliber ID} & \textbf{Era} & \textbf{Cert} \\
\midrule
\endfirsthead
\toprule
\textbf{Brand \& Model} & \textbf{References} & \textbf{Caliber ID} & \textbf{Era} & \textbf{Cert} \\
\midrule
\endhead
\bottomrule
\endfoot
"""

    for w in watches:
        brand = escape_tex(w["brand"])
        model = escape_tex(w["model_name"])
        try:
            ref_list = json.loads(w["reference_numbers_json"])
            refs = escape_tex(", ".join(ref_list))
        except Exception:
            refs = escape_tex(w["reference_numbers_json"])

        cal_id = escape_tex(w["caliber_id"])
        start_yr = escape_tex(w["production_year_start"] or "?")
        end_yr = escape_tex(w["production_year_end"] or "Pres.")
        era = f"{start_yr}\\textendash{{}}{end_yr}"

        w_tests = [encode_standard(t["standard"]) for t in tests if t["watch_id"] == w["watch_id"]]
        test_summary = ", ".join(w_tests) if w_tests else "—"

        latex_content += (
            f"\\textbf{{{brand}}} {model} & \\texttt{{{refs}}} & "
            f"\\texttt{{{cal_id}}} & {era} & \\texttt{{{test_summary}}} \\\\\n"
        )

    latex_content += r"""\end{longtable}
}
\end{document}
"""

    OUTPUT_TEX.write_text(latex_content, encoding="utf-8")
    print(f"[SUCCESS] Generated compact LaTeX catalog -> {OUTPUT_TEX.name}")


if __name__ == "__main__":
    generate_latex()
