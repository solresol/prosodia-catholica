# prosodia-catholica

Herodian's Περὶ καθολικῆς προσῳδίας (*De Prosodia Catholica*) — database + translation + (eventual) static site generator.

## Origin / goal

This project started from the following note (email from Brady Kiesling):

> If you are a glutton for punishment, I'm fairly sure that a hefty percentage of StephByz
> is salvaged from Herodian's De Prosodia Catholica. I'm attaching the Greek text here, I hope.
> I bet you and Claude could write a script to search Herodian for Steph headwords and pull out
> the phrases that match. To be safe, you'd need to ignore accents and particles, but not
> impossible... Then flag the overlap as a percentage of Meineke....

## Current purpose

Translate and present the Lentz reconstruction, with educational gadgets.
The former Herodian–Stephanos comparison is retired: the reconstructed text is
not independent evidence for the relationship the comparison tried to measure.
Historical overlap data remains untouched in the database, but is no longer
computed, queried or displayed by this project.

## Current pipeline (DB → translation → static site)

This repo includes a small PostgreSQL-backed pipeline to:
- translate a few more lines per day with OpenAI (`gpt-6-sol` by default)
- summarize passages into short index labels with OpenAI (`gpt-5.6-luna` by default)
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

5. Summarize a small batch (for the index page):
   - `uv run summarize_lines.py --limit 25`

6. Generate the site:
   - `uv run generate_site.py`

7. Deploy:
   - `rsync -az --delete --chmod=D755,F644 site/ merah:/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs/`
   - `python3 -c 'from ci.ssh_publish import manifest, verify_publication; verify_publication("site", manifest("site"))'`

The site is generated as:
- `site/index.html` (index)
- `site/passages/<ref>.html` (one page per passage)
- `site/analysis/progress.html` (cron-task progress + ETA by task)

### Daily cron (raksasa)

A minimal cloud gadget split is staged but **not active**; the existing local cron
and all non-gadget steps remain in place.
See [handoff design, operational setup and exact cloud prompt](docs/cloud-gadget-workflow.md).
Only the gadget generation API call moves to cloud after verified cutover.


Install the daily pipeline:
- `./setup_cron.sh`

The cron job runs `./run_daily_pipeline.sh` once per day and writes logs under `logs/`.

## Database boundary

The working passage text, translations, summaries and gadgets still use the
Herodian database. The site generator and pipeline no longer read the Stephanos
database. Existing overlap tables/history and existing database permissions have
not been dropped or revoked. The static public site needs no visitor-time DB.

A future Git content migration can therefore be self-contained without importing
the Stephanos corpus. It still needs a reviewed public-field boundary, a file
storage adapter, deterministic serialization and render-parity validation.
