"""Find and repair text mangled into '?' by a non-UTF-8 shell.

A run of question marks where a word should be is the signature of Cyrillic
that passed through a cp1252/ascii pipe. Nothing legitimate in this database
looks like that, so the pattern is safe to detect on.

Usage:  python fix_encoding.py [--apply]
"""

import re
import sys

from sqlalchemy import inspect, text
from database import SessionLocal, engine

# Three or more '?' in a row, or a lone '?' standing as a whole word.
SUSPECT = re.compile(r"\?{3,}|(?:^|\s)\?(?:\s|$)")

# Known repairs for rows this project created through a mangling shell.
# Each entry: (table, match_column, match_value) -> replacement columns.
REPAIRS = [
    ("custom_field_definitions", "code", "driving_licence", {
        "name_ru": "Водительские права",
        "name_kk": "Жүргізуші куәлігі",
        "name_en": "Driving licence",
        "help_text": "Категория",
    }),
    ("custom_field_definitions", "code", "relocation_ready", {
        "name_ru": "Готовность к релокации",
        "name_kk": "Көшуге дайындық",
        "name_en": "Relocation ready",
    }),
    ("compensation_tables", "id", 2, {
        "name_ru": "Компенсация опыта аналитики",
        "name_kk": "Аналитика тәжірибесінің өтемақысы",
        "name_en": "Analytics experience compensation",
    }),
    ("attachments", "id", 1, {
        "description": "Фото паспорта (тестовый файл)",
    }),
]


def scan(db):
    """Report every text column holding the '?' signature."""
    inspector = inspect(engine)
    findings = []

    for table in inspector.get_table_names():
        columns = [c for c in inspector.get_columns(table)
                   if str(c["type"]).upper().startswith(("VARCHAR", "TEXT"))]
        if not columns:
            continue

        names = [c["name"] for c in columns]
        quoted = ", ".join(f'"{n}"' for n in names)
        try:
            rows = db.execute(text(f'SELECT id, {quoted} FROM "{table}"')).fetchall()
        except Exception:                                        # noqa: BLE001
            continue

        for row in rows:
            mapping = row._mapping
            for name in names:
                value = mapping.get(name)
                if isinstance(value, str) and SUSPECT.search(value):
                    findings.append((table, mapping.get("id"), name, value))
    return findings


def apply_repairs(db):
    applied = 0
    for table, match_column, match_value, values in REPAIRS:
        sets = ", ".join(f'"{k}" = :{k}' for k in values)
        result = db.execute(
            text(f'UPDATE "{table}" SET {sets} '
                 f'WHERE "{match_column}" = :__match'),
            {**values, "__match": match_value},
        )
        applied += result.rowcount
    db.commit()
    return applied


def main():
    db = SessionLocal()
    try:
        findings = scan(db)
        if not findings:
            print("No mangled text found.")
        else:
            print(f"Found {len(findings)} suspect value(s):")
            for table, row_id, column, value in findings:
                print(f"  {table}.{column} (id={row_id}): {value!r}")

        if "--apply" in sys.argv:
            count = apply_repairs(db)
            print(f"\nRepaired {count} row(s).")
            remaining = scan(db)
            print(f"Remaining suspect values: {len(remaining)}")
            for table, row_id, column, value in remaining:
                print(f"  {table}.{column} (id={row_id}): {value!r}")
        elif findings:
            print("\nRe-run with --apply to repair the known rows.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
