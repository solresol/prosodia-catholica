# prosodia-catholica

Herodian's Περὶ καθολικῆς προσῳδίας (*De Prosodia Catholica*) — database + translation + (eventual) static site generator.

## Origin / goal

This project started from the following note (email from Brady Kiesling):

> If you are a glutton for punishment, I'm fairly sure that a hefty percentage of StephByz
> is salvaged from Herodian's De Prosodia Catholica. I'm attaching the Greek text here, I hope.
> I bet you and Claude could write a script to search Herodian for Steph headwords and pull out
> the phrases that match. To be safe, you'd need to ignore accents and particles, but not
> impossible... Then flag the overlap as a percentage of Meineke....

## Working hypothesis

A substantial portion of the Stephanus of Byzantium tradition ("StephByz", esp. Meineke) overlaps with / is salvaged from Herodian's *De Prosodia Catholica*.

## Concrete next step (analysis idea)

Write a script that:

- takes StephByz headwords (e.g. from Meineke or a derived dataset),
- searches the Herodian Greek text (e.g. `HerodianCathPros.txt`) for matching headwords / phrases,
- normalizes Greek for matching (at minimum: ignore accents; optionally ignore common particles),
- extracts candidate matching phrases for review, and
- reports overlap statistics (e.g. percent of headwords/entries with candidates).

## Current pipeline (DB → translation → static site)

This repo includes a small PostgreSQL-backed pipeline to:
- import `HerodianCathPros.txt` (TSV) into `cathpros_lines`
- translate a few more lines per day with OpenAI (`gpt-5.2` by default)
- generate a static website into `site/`
- deploy it to `merah:/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs`

### Setup (udara / raksasa)

1. Create a per-host config:
   - copy `config.py.example` → `config.py` (gitignored)
   - fill in DB settings + deploy target + model

2. Ensure an OpenAI API key exists at `~/.openai.key` (or set `OPENAI_API_KEY`).

3. Initialize schema and import TSV:
   - `uv run init_db.py`
   - `uv run import_herodian_tsv.py HerodianCathPros.txt`

4. Translate a small batch:
   - `uv run translate_lines.py --limit 5`

5. Generate the site:
   - `uv run generate_site.py`

6. Deploy:
   - `rsync -az --delete site/ merah:/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs/`

### Daily cron (raksasa)

Install the daily pipeline:
- `./setup_cron.sh`

The cron job runs `./run_daily_pipeline.sh` once per day and writes logs under `logs/`.
