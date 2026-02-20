#!/usr/bin/env python3
from __future__ import annotations

import argparse
import re
from pathlib import Path

from db import get_connection
from psycopg2.extras import execute_values


REF_RE = re.compile(r"^(?P<major>\d+)\.(?P<minor>\d+)$")


def parse_ref(ref: str) -> tuple[int | None, int | None]:
    m = REF_RE.match(ref.strip())
    if not m:
        return None, None
    return int(m.group("major")), int(m.group("minor"))


def main() -> None:
    parser = argparse.ArgumentParser(description="Import HerodianCathPros.txt TSV into PostgreSQL")
    parser.add_argument(
        "path",
        nargs="?",
        default="HerodianCathPros.txt",
        help="Path to HerodianCathPros.txt (default: ./HerodianCathPros.txt)",
    )
    args = parser.parse_args()

    tsv_path = Path(args.path)
    if not tsv_path.exists():
        raise FileNotFoundError(f"TSV not found: {tsv_path}")

    rows: list[tuple] = []
    with tsv_path.open("r", encoding="utf-8") as f:
        for line_num, line in enumerate(f, 1):
            parts = line.rstrip("\n").split("\t")
            if len(parts) != 5:
                raise ValueError(f"{tsv_path}:{line_num}: expected 5 TSV fields, got {len(parts)}")
            src_id_s, ref, src_page_s, src_line_s, text = parts
            ref_major, ref_minor = parse_ref(ref)
            rows.append(
                (
                    ref,
                    ref_major,
                    ref_minor,
                    int(src_id_s),
                    int(src_page_s),
                    int(src_line_s),
                    text.rstrip(),
                )
            )

    conn = get_connection()
    inserted = 0
    updated = 0
    try:
        with conn:
            with conn.cursor() as cur:
                execute_values(
                    cur,
                    """
                    INSERT INTO cathpros_lines
                      (ref, ref_major, ref_minor, src_id, src_page, src_line, greek_text)
                    VALUES %s
                    ON CONFLICT (ref) DO UPDATE SET
                      ref_major = EXCLUDED.ref_major,
                      ref_minor = EXCLUDED.ref_minor,
                      src_id = EXCLUDED.src_id,
                      src_page = EXCLUDED.src_page,
                      src_line = EXCLUDED.src_line,
                      greek_text = EXCLUDED.greek_text
                    RETURNING (xmax = 0) AS inserted;
                    """,
                    rows,
                    page_size=10000,
                )
                # psycopg2 doesn't expose per-row insert/update counts directly; use RETURNING flag
                for (was_inserted,) in cur.fetchall():
                    if was_inserted:
                        inserted += 1
                    else:
                        updated += 1
    finally:
        conn.close()

    print(f"OK: imported {len(rows)} rows ({inserted} inserted, {updated} updated).")


if __name__ == "__main__":
    main()
