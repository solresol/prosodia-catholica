# IMPROVEMENTS.md

*Analysis as of 2026-07-11.*

prosodia-catholica is a PostgreSQL-backed pipeline that ingests Herodian's *De Prosodia Catholica* (`HerodianCathPros.txt`), incrementally translates and summarizes it via OpenAI (a few lines per day via `run_daily_pipeline.sh` on cron), computes textual overlap against the Stephanos of Byzantium (Meineke) database, and generates a static site deployed to merah (`prosodia-catholica.symmachus.org`). The repo is already on `uv` + `pyproject.toml` (good), the working tree is clean, and the pipeline appears to be in steady daily production. The core research question — quantifying how much of StephByz is salvaged from Herodian — is partially answered by `compute_overlaps.py`, but the README's original matching plan (accent-insensitive headword search with particle filtering and percent-of-Meineke reporting) deserves a written writeup of results, not just `docs/stephanos_overlap_data.md`.

## Bugs & Fixes

- **`run_daily_pipeline.sh` log handling**: `DATE` is computed but apparently unused near the top, and everything appends to a single unrotated `pipeline.log` while also creating `logs/` (`mkdir -p logs`) that the visible steps don't write into. Either log to `logs/pipeline-$DATE.log` or drop the unused pieces; unbounded `pipeline.log` will grow forever on the cron host.
- **Duplicated config-access helpers**: `generate_site.py` reimplements `_config_int`, `_config_str`, `_env_or_config_int`, `_site_title`, etc. If any other script needs config fallbacks (translate/summarize scripts read env vars too), these belong in a shared `config_utils.py` to avoid drift.
- **`openai_utils.py` key handling**: `load_openai_api_key()` reads `~/.openai.key` with no permission check; consider warning if the file is group/world readable.

## Improvements

- **Split `generate_site.py` (2,185 lines)**: it now contains HTML rendering, Greek normalization (`_greek_casefold_strip`), span merging, progress estimation, and analysis pages. Split into `render/` (shell, index, passage, progress, analysis) and `textutils.py` (Greek normalization, `_merge_spans`, highlighting). This is the file most likely to accrete bugs.
- **Consolidate Greek normalization**: accent-stripping/casefolding logic is central to the overlap hypothesis and likely appears in both `compute_overlaps.py` and `generate_site.py` (`_greek_casefold_strip`). One canonical implementation with unit tests, please — a normalization discrepancy silently skews the headline overlap percentage.
- **Overlap methodology writeup**: the README's stated deliverable ("flag the overlap as a percentage of Meineke") should become a stable, dated report page generated from `compute_overlaps.py` output, with the particle-ignore list documented.
- **`gadgetize_lines.py` / `gadget_srcdoc`**: LLM-generated HTML/JS embedded via `srcdoc` iframes — ensure the iframe carries a restrictive `sandbox` attribute (no `allow-same-origin`), since this is model-generated code served on your domain.

## Testing

- There are **no tests at all**. Highest-value targets, roughly in order:
  1. Greek normalization (`_greek_casefold_strip`) — accents, breathings, iota subscript, final sigma.
  2. `_merge_spans` and `highlight_many_html` — overlapping/adjacent span edge cases produce broken HTML easily.
  3. `ref_to_slug` — slug stability matters because URLs are already deployed.
  4. `import_herodian_tsv.py` parsing on a small fixture.
- Add `pytest` as a dev dependency (`uv add --dev pytest`) and a `uv run pytest` step; consider running it at the top of `run_daily_pipeline.sh` so a bad pull doesn't deploy a broken site.

## Documentation

- README is good on setup but silent on the schema: a short section (or `docs/schema.md`) describing the tables `init_db.py` creates and the `stephanos_overlap_*` tables would help future you.
- Document the cron arrangement (`setup_cron.sh` — which host, what schedule, expected daily spend on OpenAI calls).

## Security

- No committed secrets found: `config.py` is properly gitignored and `config.py.example` contains only `CHANGE_ME` placeholders. Good.
- Real contact email addresses ship in `config.py.example` defaults and presumably onto the public site — fine if intentional, but note it invites scraping.
- The gadget iframe sandboxing point above is the main real exposure.

## Housekeeping / Modernization

- Already on `uv` + `pyproject.toml` with `uv.lock` committed — no requirements.txt to purge. Good.
- `__pycache__/` sits in the repo root; confirm it's gitignored (add `.gitignore` entry if missing).
- `psycopg2-binary` → consider `psycopg` (v3) at some point; not urgent.
- `scikit-learn` is a heavy dependency — if it's only used for the predictors page in `generate_site.py`, note that in pyproject or isolate it so the daily translate/summarize steps don't need it.

## Quick Wins

- Rotate/date the pipeline log (one-line change in `run_daily_pipeline.sh`).
- `uv add --dev pytest` + first test file for `_greek_casefold_strip`.
- Add `sandbox` attribute to gadget iframes if not present.
- Move shared config helpers out of `generate_site.py`.
