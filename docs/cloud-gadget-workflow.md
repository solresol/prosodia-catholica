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

## Revised data flow: private DB stays local

The first revision required cloud access to Raksasa PostgreSQL for both prepare
and apply. That route is **not verified** and must not be assumed. Tailscale is
abandoned; do not set it up or substitute a tunnel or new credential grant.

Preferred staged flow:

1. Raksasa retains the production DB, existing API key, Stephanos read access and
   deployment SSH identity. `run_content_maintenance.sh` preserves translation
   (5), summaries (25), and overlap computation (existing settings) locally.
2. After maintenance, the Herodian account runs `cloud_gadgets.py prepare` locally.
   It exports exactly one pending passage and one randomly selected existing
   gadget, including Greek, translation, gadget source and comparison snapshots.
   No credentials are in the JSON. Prepare uses DB reads and advisory lock only.
3. Deliver that ignored JSON bundle to the cloud through an **existing authorized
   artifact channel**. None was found/configured in this checkout. The existing
   public site exports `passages.json` (including gadget fields), which is a read
   source, not a verified round-trip handoff or daily work assignment mechanism.
   Do not silently publish bundles to Git, Sites, Library or a new service.
4. Cloud Codex authors/tests offline using the bundle and returns the tested
   bundle plus behavioral test evidence through the same authorized channel.
   `cloud_gadgets.py validate` works without DB settings or credentials.
5. Raksasa retrieves the returned bundle through that channel. Herodian runs
   `cloud_gadgets.py apply` locally: short transaction, daily guard, advisory lock,
   stale row comparisons, both gadget results committed together. Site publication
   reads the production DB and uses the existing rsync destination.

**Exact gap:** there is no verified existing mechanism to deliver a local daily
bundle to a scheduled cloud run and return its tested result to the Herodian
account. No such transport, importer trigger or credentials were introduced.
Selecting and verifying this channel (or having the parent perform an explicitly
authorized manual artifact transfer for rehearsal) is required before an actual
cloud test. Do not enable a production schedule that depends on an unspecified
transfer. Direct DB prepare/apply remain local tools; they are not cloud steps.

## Dependencies and existing permissions

Local: Python >=3.11, uv and locked project dependencies, existing Herodian SELECT
and UPDATE on cathpros_lines, current OpenAI key for translations/summaries,
Stephanos reads, existing Git access, flock, rsync and merah deployment rights.
No new grants, security changes or schema migration are required. Daily init_db
DDL is omitted from the staged replacement: existing schema is required and no
migration should run during the ongoing PostgreSQL migration.

Cloud: Python >=3.11 (stdlib is sufficient for bundle validation), a supported
browser tool or Playwright/Chromium, repository read access, incoming artifact
read and outgoing artifact write access in the **verified existing channel**.
No PostgreSQL or OpenAI API credential, deployment SSH key, VPN or access to
Raksasa is needed. Run only offline tests; do not invoke uv sync merely to validate
bundles if installed browser tools suffice. Reusable code fixes may use existing
authorized Git write access, but bundle data must stay out of the repository.

## Exact daily Codex cloud prompt

```text
In the published classical-texts environment, work only on solresol/prosodia-catholica.
Read applicable engineering instructions and docs/cloud-gadget-workflow.md. Verify
the existing authorized repository remote. This job uses an artifact handoff,
not private production DB access. Do not use Tailscale, tunnels, PostgreSQL,
production credentials, schema initialization or deployment commands. Do not
create credentials, grants, network changes or new external destinations.

Obtain today's UTC work bundle from the existing authorized artifact channel
specified and verified by the parent. If the channel or bundle is absent, stale,
or ambiguous, stop and report the exact missing handoff; do not invent a path or
fetch a different past gadget. Preserve the bundle's original snapshots and day.
Run python3 -m unittest discover -s tests -v. If new is null, report exhaustion and
stop without changing an old gadget into a new one.

Author exactly one self-contained educational HTML/CSS/vanilla-JS gadget for the
bundle's new Greek passage and translation. Follow gadgetize_lines.py's format
and gadget_validation.py's offline constraints. Inspect the randomly selected
past gadget. For each, render candidate html/css/js with the same srcdoc document
and sandbox="allow-scripts allow-forms" iframe used in generate_site.py. The
renderer can be copied into the isolated test harness; importing generate_site
requires DB settings and is unnecessary. Block external network requests.
Exercise the main controls with representative Greek input, a second distinct
input, empty input and reset where present. Check visible output against explicit
expected behavior derived from the passage, browser errors and layout at narrow
and desktop widths. Fix broken past gadget behavior and retest. Page load and
absence of errors alone are not behavioral tests. Use browser automation and
assertions tailored to each gadget. If browser tools are unavailable or behavior
cannot be verified, stop and report without returning an apply-ready bundle.

In each bundle item, save candidate {html,css,js} and test_evidence with browser,
interaction, expected and actual (the latter two must match). Preserve original
snapshots. Save detailed browser assertions/results and any reusable test harness.
Run python3 cloud_gadgets.py validate exports/gadgets-YYYY-MM-DD.json (using the
actual bundle location). This command needs no DB or model credentials. Return
the validated bundle and test evidence through the same existing authorized
artifact channel. Do not call prepare or apply in the cloud; Raksasa applies the
returned bundle locally with duplicate and stale-edit checks.

Report the input/output artifact identities, new/past passage IDs, repairs,
browser assertions/results and validation outcome. State that production apply
is pending local verification. Commit and push only scoped reusable code/test
fixes to the verified existing authorized remote, preserving unrelated work;
stop on conflicts or unexpected remote/visibility. Do not create a PR. Never
commit bundles, secrets or generated site output. No undisclosed external
transmissions and no access to unauthorized computers.
```

## Cadence and staged cutover

All entries below are proposals, not installed. Active legacy cron remains at
01:15 server local time and keeps all existing functions, including generation.
The publisher-only entry must never replace it without the companion maintenance
entry and tested artifact round trip.

Proposed daily order once the handoff exists:

- 22:00 Australia/Sydney: local content maintenance (translation, summary, overlaps),
  then local bundle prepare and delivery via the verified artifact channel. This
  is 11:00 UTC AEDT / 12:00 UTC AEST; cloud must receive a fresh current-UTC-day bundle.
- 13:00 UTC: cloud authors one gadget, tests it and the preselected random past
  gadget, corrects failures, validates and returns the artifact.
- Before 01:15 Australia/Sydney: local verified artifact retrieval and atomic apply.
- 01:15 Australia/Sydney: local build/publish only (`run_site_publish.sh`). This
  is 14:15 UTC AEDT / 15:15 UTC AEST, allowing 75/135 minutes after cloud start.
  A late result waits for the next rebuild; never bypass stale/day guards.

The local transport/export/import commands are deliberately unspecified until
an existing authorized handoff is verified; therefore no executable replacement
crontab is supplied yet. Maintenance must not overlap itself (flock), and transport
must deliver only after successful maintenance/prepare. On maintenance or handoff
failure preserve diagnostics and do not silently substitute a different bundle.
The existing heavy overlap job stays local at its existing once-daily rate; do
not run an extra manual overlap test during migration. Content maintenance uses
short per-operation commits as its existing scripts do; a retry after partial
failure can advance another batch, so do not automatically retry the whole daily
maintenance run without inspecting which steps completed.

Before cutover: merge/review staged changes; verify existing handoff permissions,
cloud browser availability and a read-only bundle rehearsal. Coordinate a full
apply in a window when the old generator has not already generated that UTC day,
then confirm new and past gadget tests and local publication. Parent must confirm
readiness before replacing the legacy cron with both local stages and enabling
the cloud schedule. Verify server timezone, exact cron and no running pipeline;
save the original cron entry for rollback. Disable the old generator only as part
of that coordinated handoff. If the trial fails, restore the saved legacy entry
before its next due run and leave cloud scheduling disabled. Never activate both
daily generators. Do not run setup_cron.sh (it installs the legacy pipeline).

Cloud bundle validation and local apply are distinct: evidence is an agent
assertion, not an executed browser test. The parent/local operator must check the
returned artifact and actual browser evidence before apply. Apply uses a shared
PostgreSQL advisory transaction lock, short lock/statement timeouts, UTC-day guard
and row snapshot comparisons; new and repaired gadgets commit together. No locks
are held while Codex authors/tests. The legacy generator does not use this lock,
so coordinated cutover is mandatory. Successful apply then retry is a guarded
skip. UTC midnight invalidates old bundles. No schema/ledger changes are added.

Publisher flock serializes publication. It is silent on success; failed logs are
retained and replayed to stderr with the original failure status. Dirty checkouts,
pull failures, wrong origin/destination and build/rsync failures are fatal. rsync
retains its existing non-atomic deployment behavior. Maintenance has the same
quiet-success/error-reporting behavior and never generates gadgets. Both run only
on Raksasa. Failed logs need normal operator retention management.
