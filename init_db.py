#!/usr/bin/env python3
from __future__ import annotations

from db import get_connection


DDL = """
CREATE TABLE IF NOT EXISTS cathpros_lines (
  id BIGSERIAL PRIMARY KEY,
  ref TEXT NOT NULL UNIQUE,
  ref_major INTEGER,
  ref_minor INTEGER,
  src_id INTEGER,
  src_page INTEGER,
  src_line INTEGER,
  greek_text TEXT NOT NULL,
  english_translation TEXT,
  imported_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  translated_at TIMESTAMPTZ,
  translation_model TEXT,
  translation_tokens INTEGER,
  translation_attempts INTEGER NOT NULL DEFAULT 0,
  last_attempted_at TIMESTAMPTZ,
  translation_error TEXT
);

CREATE INDEX IF NOT EXISTS cathpros_lines_pending_idx
  ON cathpros_lines (id)
  WHERE english_translation IS NULL;
"""


def main() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
    finally:
        conn.close()
    print("OK: ensured schema exists (cathpros_lines).")


if __name__ == "__main__":
    main()

