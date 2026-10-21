# Staged cloud / publisher split

## Verified on Raksasa (2026-10-22)

Production: `/home/herodian/prosodia-catholica`, OS account `herodian`.
Clean source checkout: `/home/gregb/devel/prosodia-catholica`.
Both use public `git@github.com:solresol/prosodia-catholica.git`.
Active herodian crontab: `15 1 * * * cd ~/prosodia-catholica && ./run_daily_pipeline.sh`.
Server log timezone: AEDT. Last inspected run completed successfully on October 22.
Deployment: `merah:/var/www/vhosts/prosodia-catholica.symmachus.org/htdocs/`.
DB: `localhost:5432`, database/user `herodian` in production.
No applicable AGENTS.md found in inspected checkout/ancestor locations.

The existing pipeline pulls Git, initializes schema, translates 5 passages,
summarizes 25, generates 1 gadget, computes overlaps, rebuilds and rsyncs.
Its gadget regex checks do not exercise a browser; failures are caught and may
still exit zero. Its generator holds row locks across model calls. No existing
browser tests were found. Existing pipeline and cron are intentionally unchanged.

## Dependencies and existing access (must verify in classical-texts)

Python >=3.11, uv, locked project dependencies (`uv sync --frozen`), a supported
browser automation tool or Playwright plus Chromium. Browser tests must run in the
cloud, not on resource-constrained Raksasa. No OpenAI API key is needed when Codex
authors gadgets directly with the bundle workflow. The legacy generator still
uses its existing API key until cutover.

The cloud requires an **already authorized** route to the production Herodian DB
and existing credentials allowing SELECT and UPDATE on `cathpros_lines`.
Use configured `DB_HOST/DB_PORT/DB_NAME/DB_USER/DB_PASSWORD` (or corresponding PG
variables); config.py takes precedence. Cloud localhost does not mean Raksasa.
Do not copy credentials into Git, logs or bundles, grant roles, change network
policy, or create tunnels without separate authorization. These cloud access
requirements have not been verified from this local executor.

Publisher retains existing Herodian DB reads, SSH identity/host verification for
merah, destination write permission, Git read access, rsync, flock and uv.
No new service permissions are required. Production deployment credentials are
not required in the cloud. No live DB writes or external deployment were tested
as part of staging.

## Exact daily Codex cloud prompt

```text
In the published classical-texts environment, work only on solresol/prosodia-catholica.
Read applicable engineering instructions and docs/cloud-gadget-workflow.md. Verify
that this is the existing authorized remote and that the cloud has its existing
authorized route and credentials to the production Herodian database. Stop and
report missing access; do not create grants, credentials, network changes or
access to other computers. Respect the ongoing PostgreSQL migration: no service
restarts, schema initialization, translation/summary/overlap jobs or broad scans.

Run uv sync --frozen and python3 -m unittest discover -s tests -v. Prepare a fresh
ignored daily bundle with uv run cloud_gadgets.py prepare exports/gadgets-YYYY-MM-DD.json
using today's UTC date. If a gadget was already generated today, report that the
run was skipped; do not bypass the guard. Keep the bundle for retries; do not
prepare repeatedly to choose a different past gadget. If no new passage exists,
report exhaustion; do not invent a passage or overwrite an old gadget as new.

Author exactly one self-contained educational HTML/CSS/vanilla-JS gadget for the
bundle's new Greek passage and translation. Follow gadgetize_lines.py's format
and offline validation constraints. Inspect the randomly selected past gadget.
For each, render candidate html/css/js using generate_site.gadget_srcdoc inside
the same sandbox="allow-scripts allow-forms" iframe as production. Block external
network requests. Exercise the main controls with representative Greek input,
a second distinct input, empty input and reset where present. Check visible
output against explicit expected behavior derived from the passage, browser
errors and layout at narrow and desktop widths. Fix broken past gadget behavior
and retest. Never count mere page load or absence of errors as a behavioral test.
Use browser automation and assertions tailored to each gadget. If browser tools
are unavailable or behavior cannot be verified, stop before apply and report.

In each bundle item, save candidate {html,css,js} and test_evidence with browser,
interaction, expected and actual (the latter two must match). Preserve original
snapshots. Save detailed browser results/assertions in ignored exports/. Apply
only after both gadgets pass with uv run cloud_gadgets.py apply exports/gadgets-YYYY-MM-DD.json.
This commits new and repaired gadget data atomically; stale snapshots or another
successful generation today must stop the run. Do not bypass failures. No rsync
or site deployment from the cloud. Report new/past passage IDs, repairs, test
assertions/results and apply outcome. Commit and push scoped reusable code/test
fixes only to the verified existing authorized remote, preserving unrelated work;
stop on conflicts or unexpected remote/visibility. Never commit bundles, secrets
or generated site output. No undisclosed external transmissions.
```

## Cutover and cadence

1. Review/merge these staged additions. Keep active legacy cron unchanged until
   a manual cloud rehearsal is complete. Prepare/browser-test without apply first;
   the existing daily generation guard will normally refuse on a legacy-run day.
   Do not bypass the guard to test a production write. A full cloud apply therefore
   needs a coordinated handoff window before that day's legacy generation.
2. Parent confirms cloud access, browser tests, and readiness. Immediately before
   handoff, verify no legacy pipeline is running and re-read cron/checkout state.
   Do not enable both daily generators. In that controlled window replace the old
   cron command with the publisher, run the cloud job once, verify its apply and
   then run/verify publisher. On cloud failure restore the saved old cron before
   its next due generation and leave cloud scheduling disabled.
3. Only after that succeeds enable daily cloud generation at 13:00 UTC and retain
   site publication at 01:15 Australia/Sydney (14:15 UTC AEDT / 15:15 UTC AEST on
   the preceding UTC date). At the currently observed timezone this gives 75 minutes.
   Explicitly verify server timezone before installing: do not infer it from the
   automation user's timezone. A late cloud result appears on the next rebuild;
   publishing the previous tested DB snapshot remains safe.
4. Replacement entry, **not installed**:
   `15 1 * * * cd /home/herodian/prosodia-catholica && ./run_site_publish.sh`
   Do not redirect to /dev/null: the wrapper is silent on success and retains
   failed logs, replays useful diagnostics to stderr and returns the actual failure.
   An overlap returns 75, never a false success. Do not run setup_cron.sh: it still
   installs the legacy workflow. Save/restore only Herodian's exact cron entry.

The publisher performs no translation, summary, gadget generation, overlap
recomputation or schema migration. Their incremental progress stops at cutover
unless separately scheduled; parent must explicitly account for that desired
scope before activation. Previously computed data stays available to site builds.

Cloud prepare uses a small IDs list (~544 current passages) and one row lookup
for uniform random sampling, avoiding ORDER BY random(). Apply uses a shared
PostgreSQL advisory transaction lock, short lock/statement timeouts, UTC-day guard
and row snapshot comparisons; new and repaired gadgets commit together. No locks
are held while Codex authors/tests. Competing cloud bundles may be prepared but
only the first successful apply per UTC day can publish. The legacy generator
does not participate in this lock, so staged cutover is mandatory. A successful
apply followed by scheduler retry is a guarded skip. UTC midnight invalidates old
bundles. Evidence is a reviewable agent assertion, not a substitute for actual
browser execution. No schema/ledger changes are introduced.

Publisher flock serializes local publication. Git pulls are fast-forward only;
dirty checkouts, pull failures, wrong origin/destination and build/rsync failures
are fatal. Existing rsync publication behavior is retained (not an atomic directory
swap); failed transfers may need a retry. Failed logs require normal operator
retention management.
