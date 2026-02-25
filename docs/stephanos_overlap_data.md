# Using the Herodian ↔ Stephanos overlap data

This repository computes overlaps between:

- **Herodian**, *De Prosodia Catholica* (TSV import: `HerodianCathPros.txt`, stored in `cathpros_lines`)
- **Stephanos of Byzantium (Meineke)**, current “meineke” text in the Stephanos PostgreSQL database

The overlap computation is run on **raksasa** (daily via cron) and the results are stored in the **Herodian PostgreSQL database** (`herodian`).

The **Stephanos project team** can read this overlap data from the Herodian DB using the database role **`stephanos`** (read‑only grants are applied by `init_db.py`).

## Quick start

1. Connect to the Herodian DB (ask Greg for credentials / access if needed):

   - From `raksasa`:
     - `psql -d herodian -U stephanos`
   - From elsewhere (example):
     - `psql -h raksasa -d herodian -U stephanos`

2. Pick the latest finished overlap run:

   ```sql
   SELECT id, metric_version, created_at, finished_at
   FROM stephanos_overlap_runs
   WHERE finished_at IS NOT NULL
   ORDER BY created_at DESC
   LIMIT 1;
   ```

3. Query overlap matches for a Stephanos lemma id or a Herodian passage.

## Data model

### `cathpros_lines`

One row per Herodian “passage line” imported from the TSV.

Key columns:

- `id` (PK)
- `ref` (e.g. `1.17`)
- `greek_text`
- `english_translation` (OpenAI translation; may be NULL)
- `summary` (short index label; may be NULL)

### `stephanos_overlap_runs`

One row per overlap computation run.

- `id` (PK)
- `metric_version` (currently `v1`)
- `created_at`, `finished_at`
- `stephanos_lemmas_count`, `stephanos_meineke_current_count` (counts at run time)

### `stephanos_overlap_matches`

Matches between one Herodian passage (`herodian_line_id`) and one Stephanos lemma (`stephanos_lemma_id`) for a given run.

Key columns:

- `run_id` → `stephanos_overlap_runs.id`
- `herodian_line_id` → `cathpros_lines.id`
- `stephanos_lemma_id` (Stephanos DB lemma id)
- `stephanos_meineke_id` (Meineke reference string, when available)
- `stephanos_headword`

Scoring:

- `char_lcs_len`: length of the longest common **contiguous** block on **normalized Greek letters**
- `char_lcs_ratio`: `char_lcs_len / min(len(herodian_norm_letters), len(stephanos_norm_letters))`
- `word_lcs_len`: length of the longest common contiguous block on **normalized Greek words**
- `word_lcs_ratio`: `word_lcs_len / min(len(herodian_norm_words), len(stephanos_norm_words))`

Highlight / span fields:

- `herodian_char_start`, `herodian_char_end`
- `stephanos_char_start`, `stephanos_char_end`

These spans are **0‑based Python string indices** into the *original un‑normalised* text strings (`cathpros_lines.greek_text` and the Stephanos `text_body`), with **end exclusive**.

They are intended for UI highlight rendering and for computing conservative “coverage” estimates.

## Normalisation details (v1)

The overlap computation normalizes Greek for matching by:

- Unicode NFD decomposition
- stripping combining marks (accents, breathings)
- lowercasing
- final sigma → sigma (`ς` → `σ`)
- ignoring non‑Greek letters for the “letters” stream

See `compute_overlaps.py` for the authoritative implementation.

## Example queries

### Overlaps for one Herodian passage

```sql
WITH latest AS (
  SELECT id
  FROM stephanos_overlap_runs
  WHERE metric_version = 'v1' AND finished_at IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  l.ref,
  m.stephanos_lemma_id,
  m.stephanos_meineke_id,
  m.stephanos_headword,
  m.char_lcs_len,
  m.word_lcs_len,
  m.herodian_char_start,
  m.herodian_char_end
FROM stephanos_overlap_matches m
JOIN latest r ON r.id = m.run_id
JOIN cathpros_lines l ON l.id = m.herodian_line_id
WHERE l.ref = '1.17'
ORDER BY m.char_lcs_ratio DESC, m.word_lcs_ratio DESC, m.char_lcs_len DESC;
```

### Overlaps for one Stephanos lemma id

```sql
WITH latest AS (
  SELECT id
  FROM stephanos_overlap_runs
  WHERE metric_version = 'v1' AND finished_at IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  l.ref,
  m.char_lcs_len,
  m.word_lcs_len
FROM stephanos_overlap_matches m
JOIN latest r ON r.id = m.run_id
JOIN cathpros_lines l ON l.id = m.herodian_line_id
WHERE m.stephanos_lemma_id = 12345
ORDER BY m.char_lcs_ratio DESC, m.word_lcs_ratio DESC, m.char_lcs_len DESC;
```

### Snippet extraction (Herodian side)

PostgreSQL `substring()` is 1‑based, so add 1 to `*_char_start`.

```sql
WITH latest AS (
  SELECT id
  FROM stephanos_overlap_runs
  WHERE metric_version = 'v1' AND finished_at IS NOT NULL
  ORDER BY created_at DESC
  LIMIT 1
)
SELECT
  l.ref,
  m.stephanos_meineke_id,
  substring(l.greek_text FROM m.herodian_char_start + 1 FOR (m.herodian_char_end - m.herodian_char_start)) AS herodian_snippet
FROM stephanos_overlap_matches m
JOIN latest r ON r.id = m.run_id
JOIN cathpros_lines l ON l.id = m.herodian_line_id
WHERE l.ref = '1.17'
ORDER BY m.char_lcs_len DESC
LIMIT 10;
```

## Working with the Stephanos DB

The overlap table stores `stephanos_lemma_id` and (usually) `stephanos_meineke_id`/`stephanos_headword`.

If you need the full Meineke text, query the Stephanos DB:

- Table: `public.lemma_source_text_versions`
- Current Meineke text: `source_document = 'meineke' AND is_current = TRUE`

Note: the Herodian DB and Stephanos DB are separate databases. Cross‑database joins require `postgres_fdw` (or application‑level joins).

## Using the overlap spans

The stored span indices make it possible to:

- highlight the matched region in Herodian and/or Stephanos UIs
- compute “coverage” estimates by taking the **union** of spans per passage/lemma

Remember:

- indices are **0‑based**, **end‑exclusive**
- spans refer to *original text strings* (with punctuation/whitespace preserved)

## Refresh cadence

On `raksasa`, a daily cron job runs the pipeline (`run_daily_pipeline.sh`) which:

- translates/summarizes small batches
- recomputes overlaps vs current Meineke texts
- regenerates the static site and deploys it

The live site provides human-readable examples and highlights:

- https://prosodia-catholica.symmachus.org/
