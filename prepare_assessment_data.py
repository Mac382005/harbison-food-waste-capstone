#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import shutil
import sqlite3
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path.cwd()
DATA = ROOT / "data"
OUT = DATA / "deliverable"

SECRET_MARKERS = ("password", "passwd", "secret", "token", "api_key", "apikey", "credential")
SKIP_DIR_NAMES = {".git", ".venv", "venv", "__pycache__", ".pytest_cache"}
SKIP_FILE_SUFFIXES = {".pyc", ".bak"}
SOURCE_DIRS = [
    DATA / "private",
    DATA / "raw",
    DATA / "import",
    ROOT / "real_data",
    ROOT / "harbison_data",
]

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()

def safe_copy_tree(src: Path, dst: Path) -> int:
    if not src.exists():
        return 0
    copied = 0
    for p in src.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(src)
        if any(part in SKIP_DIR_NAMES for part in rel.parts):
            continue
        if p.suffix.lower() in SKIP_FILE_SUFFIXES:
            continue
        if p.name.lower().startswith(".env") or p.suffix.lower() == ".env":
            continue
        if p.suffix.lower() in {".db", ".sqlite", ".sqlite3"}:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        copied += 1
    return copied

def choose_database() -> Path:
    preferred = DATA / "food_waste_v2.db"
    if preferred.exists():
        return preferred
    candidates = [
        p for p in DATA.glob("*.db")
        if "before_" not in p.name.lower() and "backup" not in p.name.lower()
    ]
    if not candidates:
        raise FileNotFoundError("No current SQLite .db file found directly under data/.")
    return max(candidates, key=lambda p: p.stat().st_mtime)

def redact_secret_columns(df: pd.DataFrame):
    redacted = []
    out = df.copy()
    for col in out.columns:
        col_lower = str(col).lower()
        if any(marker in col_lower for marker in SECRET_MARKERS):
            out[col] = "[REDACTED]"
            redacted.append(str(col))
    return out, redacted

def split_real_synthetic(df: pd.DataFrame):
    cols = {str(c).lower(): c for c in df.columns}
    if "is_demo" in cols:
        c = cols["is_demo"]
        values = pd.to_numeric(df[c], errors="coerce")
        return (
            df[values.fillna(0) == 0].copy(),
            df[values.fillna(0) == 1].copy(),
            f"{c}=0 real; {c}=1 synthetic/demo",
        )
    if "synthetic_run_id" in cols:
        c = cols["synthetic_run_id"]
        return (
            df[df[c].isna()].copy(),
            df[df[c].notna()].copy(),
            f"{c} null real; non-null synthetic",
        )
    for key in ("data_source", "source_type", "record_source"):
        if key in cols:
            c = cols[key]
            s = df[c].astype(str).str.lower()
            syn_mask = s.str.contains("synthetic|demo", regex=True, na=False)
            real_mask = s.str.contains("real|operational|harbison", regex=True, na=False)
            if syn_mask.any() or real_mask.any():
                return (
                    df[real_mask].copy(),
                    df[syn_mask].copy(),
                    f"{c} textual source classification",
                )
    return None, None, None

def export_database(db_path: Path):
    csv_dir = OUT / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)

    records = []
    with sqlite3.connect(db_path) as conn:
        tables = pd.read_sql_query(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name",
            conn,
        )["name"].tolist()

        for table in tables:
            safe_table = table.replace('"', '""')
            df = pd.read_sql_query(f'SELECT * FROM "{safe_table}"', conn)
            df, redacted = redact_secret_columns(df)

            df.to_csv(csv_dir / f"{table}.csv", index=False)

            real_df, syn_df, rule = split_real_synthetic(df)
            real_rows = synthetic_rows = None

            if real_df is not None:
                real_df.to_csv(csv_dir / f"{table}__real.csv", index=False)
                real_rows = len(real_df)

            if syn_df is not None:
                syn_df.to_csv(csv_dir / f"{table}__synthetic.csv", index=False)
                synthetic_rows = len(syn_df)

            records.append({
                "table": table,
                "rows": len(df),
                "columns": len(df.columns),
                "real_rows": real_rows,
                "synthetic_rows": synthetic_rows,
                "split_rule": rule or "",
                "redacted_columns": ", ".join(redacted),
            })
    return records

def build_manifest():
    rows = []
    for p in sorted(OUT.rglob("*")):
        if not p.is_file() or p.name == "MANIFEST.csv":
            continue
        rows.append({
            "path": p.relative_to(ROOT).as_posix(),
            "size_bytes": p.stat().st_size,
            "sha256": sha256_file(p),
        })
    return pd.DataFrame(rows)

def main():
    if not DATA.exists():
        raise FileNotFoundError("data/ directory not found. Run from repository root.")

    if OUT.exists():
        shutil.rmtree(OUT)
    OUT.mkdir(parents=True)

    db_path = choose_database()
    table_info = export_database(db_path)

    approved_root = OUT / "approved_source_files"
    source_copy_counts = {}

    for src in SOURCE_DIRS:
        if not src.exists():
            continue
        label = src.relative_to(ROOT).as_posix().replace("/", "__")
        count = safe_copy_tree(src, approved_root / label)
        source_copy_counts[src.relative_to(ROOT).as_posix()] = count

    template_src = DATA / "templates"
    if template_src.exists():
        safe_copy_tree(template_src, OUT / "templates")

    pd.DataFrame(table_info).to_csv(OUT / "DATABASE_TABLE_SUMMARY.csv", index=False)

    created = datetime.now().astimezone().isoformat(timespec="seconds")
    lines = [
        "# Assessment Data Bundle",
        "",
        f"Generated: `{created}`",
        "",
        "This folder is the assessment/handover data snapshot for the final Harbison Food Waste prototype.",
        "",
        "## Contents",
        "",
        "- `csv/` â€” CSV export of every application database table from the final local prototype state.",
        "- `csv/*__real.csv` and `csv/*__synthetic.csv` â€” split exports where a reliable source marker exists.",
        "- `approved_source_files/` â€” sponsor/reference/raw/import files approved for assessment sharing.",
        "- `templates/` â€” blank import templates.",
        "- `DATABASE_TABLE_SUMMARY.csv` â€” table row counts and source-split information.",
        "- `MANIFEST.csv` â€” file sizes and SHA-256 hashes.",
        "",
        "## Interpretation",
        "",
        "Synthetic records are for development, testing and ML validation and must not be interpreted as actual Harbison operational outcomes.",
        "",
        "## Reproduce synthetic data",
        "",
        "```powershell",
        "python generate_synthetic_data.py --start 2026-03-01 --end 2026-10-18 --seed 42 --intake-days 30 --residents-per-area 12",
        "```",
        "",
        "## Database exported",
        "",
        f"`{db_path.relative_to(ROOT).as_posix()}`",
        "",
        "## Database tables",
        "",
    ]

    for info in table_info:
        extra = ""
        if info["synthetic_rows"] is not None:
            extra = f" â€” real: {info['real_rows']}, synthetic: {info['synthetic_rows']}"
        lines.append(f"- `{info['table']}`: {info['rows']} rows{extra}")

    lines += ["", "## Approved source files copied", ""]
    if source_copy_counts:
        for source, count in source_copy_counts.items():
            lines.append(f"- `{source}`: {count} files")
    else:
        lines.append("- No additional approved source folders were present locally.")

    lines += [
        "",
        "## Security",
        "",
        "Environment files, virtual environments, Python caches, SQLite database binaries/backups, and secret/password/token values are not included in GitHub.",
        "Potential credential columns in CSV exports are replaced with `[REDACTED]`.",
        "",
    ]

    (OUT / "DATA_README.md").write_text("\n".join(lines), encoding="utf-8")

    manifest = build_manifest()
    manifest.to_csv(OUT / "MANIFEST.csv", index=False)

    print("=" * 72)
    print("Assessment data bundle created")
    print("=" * 72)
    print(f"Database: {db_path}")
    print(f"Output:   {OUT}")
    print(f"Tables:   {len(table_info)}")
    print(f"Files:    {len(manifest) + 1}")
    print()
    print("Largest files:")
    for _, row in manifest.sort_values("size_bytes", ascending=False).head(10).iterrows():
        print(f"  {row['size_bytes'] / (1024 * 1024):8.2f} MB  {row['path']}")
    print()
    over_limit = manifest[manifest["size_bytes"] >= 95 * 1024 * 1024]
    if len(over_limit):
        print("WARNING: Files >=95 MB found. Review before pushing to GitHub.")
    else:
        print("No files >=95 MB detected.")

if __name__ == "__main__":
    main()

