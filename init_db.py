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
  summary TEXT,
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

ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summarized_at TIMESTAMPTZ;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary_model TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary_tokens INTEGER;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary_last_attempted_at TIMESTAMPTZ;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS summary_error TEXT;

CREATE INDEX IF NOT EXISTS cathpros_lines_summary_pending_idx
  ON cathpros_lines (id)
  WHERE summary IS NULL;

-- "Toy" gadgets: self-contained HTML/CSS/JS per passage (rendered in a sandboxed iframe).
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_html TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_css TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_js TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_generated_at TIMESTAMPTZ;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_model TEXT;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_tokens INTEGER;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_attempts INTEGER NOT NULL DEFAULT 0;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_last_attempted_at TIMESTAMPTZ;
ALTER TABLE cathpros_lines ADD COLUMN IF NOT EXISTS gadget_error TEXT;

CREATE INDEX IF NOT EXISTS cathpros_lines_gadget_pending_idx
  ON cathpros_lines (id)
  WHERE gadget_html IS NULL;

-- Existing retired overlap tables/history are intentionally left untouched.
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
