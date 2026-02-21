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

CREATE TABLE IF NOT EXISTS stephanos_overlap_runs (
  id BIGSERIAL PRIMARY KEY,
  metric_version TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  finished_at TIMESTAMPTZ,
  stephanos_lemmas_count INTEGER,
  stephanos_meineke_current_count INTEGER
);

CREATE TABLE IF NOT EXISTS stephanos_overlap_matches (
  id BIGSERIAL PRIMARY KEY,
  run_id BIGINT NOT NULL REFERENCES stephanos_overlap_runs(id) ON DELETE CASCADE,
  herodian_line_id BIGINT NOT NULL REFERENCES cathpros_lines(id) ON DELETE CASCADE,
  stephanos_lemma_id INTEGER NOT NULL,
  stephanos_meineke_id TEXT,
  stephanos_headword TEXT,
  char_lcs_len INTEGER NOT NULL,
  char_lcs_ratio REAL NOT NULL,
  herodian_char_start INTEGER,
  herodian_char_end INTEGER,
  stephanos_char_start INTEGER,
  stephanos_char_end INTEGER,
  word_lcs_len INTEGER NOT NULL,
  word_lcs_ratio REAL NOT NULL,
  shared_char_shingles INTEGER,
  shared_word_shingles INTEGER,
  computed_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  UNIQUE (run_id, herodian_line_id, stephanos_lemma_id)
);

CREATE INDEX IF NOT EXISTS stephanos_overlap_matches_line_idx
  ON stephanos_overlap_matches (run_id, herodian_line_id);

CREATE INDEX IF NOT EXISTS stephanos_overlap_matches_lemma_idx
  ON stephanos_overlap_matches (run_id, stephanos_lemma_id);

ALTER TABLE stephanos_overlap_matches ADD COLUMN IF NOT EXISTS herodian_char_start INTEGER;
ALTER TABLE stephanos_overlap_matches ADD COLUMN IF NOT EXISTS herodian_char_end INTEGER;
ALTER TABLE stephanos_overlap_matches ADD COLUMN IF NOT EXISTS stephanos_char_start INTEGER;
ALTER TABLE stephanos_overlap_matches ADD COLUMN IF NOT EXISTS stephanos_char_end INTEGER;

-- Allow Stephanos read-only access to Herodian overlap data.
GRANT USAGE ON SCHEMA public TO stephanos;
GRANT SELECT ON cathpros_lines TO stephanos;
GRANT SELECT ON stephanos_overlap_runs TO stephanos;
GRANT SELECT ON stephanos_overlap_matches TO stephanos;
"""


def main() -> None:
    conn = get_connection()
    try:
        with conn:
            with conn.cursor() as cur:
                cur.execute(DDL)
    finally:
        conn.close()
    print("OK: ensured schema exists (cathpros_lines, stephanos overlaps).")


if __name__ == "__main__":
    main()
