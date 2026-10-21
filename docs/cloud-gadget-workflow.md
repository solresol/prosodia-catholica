# Staged cloud gadget / local maintenance and publisher split

## Verified state and disclosure scope

Raksasa production is `/home/herodian/prosodia-catholica`, OS user `herodian`.
Its active cron remains `15 1 * * * cd ~/prosodia-catholica && ./run_daily_pipeline.sh`.
`/etc/localtime` resolves to Australia/Sydney. The last inspected October 22 run
completed successfully. Both clean source/production checkouts use the public
`git@github.com:solresol/prosodia-catholica.git`; visibility was reverified through
GitHub. No applicable AGENTS.md or local memories were found in inspected paths.

The existing site `passages.json` contains id, ref, Greek, translation and gadget
HTML/CSS/JS (544 passages, 211 with gadgets when inspected). The queue uses only
those seven passage fields, candidate gadget source intended for the same site,
an Australia/Sydney day, an opaque worker ID, fixed mode/status and bounded
browser test evidence. It excludes DB credentials/settings, generated timestamps,
private annotations, tokens, errors/stack traces, full site, database dumps and
unrelated data. `prepare` requires exact DB-row equality with a snapshot of the
last **successfully published** site. Fresh unpublished translations are skipped.
The publisher advances `logs/published-passages.json` only after successful rsync.

The existing repository is a suitable existing destination within the requested
workflow; no new destination, credential grant or private DB connection is needed.
Public evidence must describe only the public gadget's behavior, never environment,
host/account names, paths, credentials or arbitrary logs/screenshots. The schema
limits evidence to four strings of at most 2,000 characters each per gadget and
rejects unknown fields; each text/source field is limited to 64,000 characters,
each bundle to 512KB. These bounds/allowlists are not a secret detector: Codex
must inspect the actual evidence before submit. Git retains historical records.
One verified public rehearsal request has been transmitted to gadget-handoff;
source code/docs/tests remain on the staged implementation branch. No data-sharing approval gap identified for this
strictly public/intended-for-publication payload.

## Data flow and concurrency

The dedicated **gadget-handoff** Git branch contains only
`handoff/YYYY-MM-DD.json`, one record for each Australia/Sydney logical day:
`{mode, request, claim, result, ack}`. It is created automatically by the first
enqueue; it has no source code, site or credential files. Each process verifies
public repository identity through the unauthenticated GitHub metadata API.
Git transport always uses the existing exact SSH remote above. No API token is
required. Herodian's existing SSH identity passed a dry-run push; public metadata
reads also passed. Its GitHub CLI has no login; the workflow does not require one.
Cloud Git SSH read/write ability remains to be tested using its existing identity.
If absent, stop and report; do not add keys or grants.

1. Raksasa preserves translation (5), summaries (25) and overlap computation in
   `run_content_maintenance.sh`. No gadget generation, schema initialization or
   service restart occurs there. Existing API key/DB/Stephanos reads stay local.
2. Raksasa `enqueue` reads the DB and last successful public snapshot, selects one
   pending passage and one uniformly random existing gadget from matching public
   rows, and pushes a bounded request. Re-enqueue returns the existing request;
   it never changes the chosen past gadget. If older production work is pending,
   enqueue resumes it instead of creating a conflicting daily request. The small
   corpus is read locally.
3. Cloud `claim` pushes a unique opaque worker ID before starting browser work.
   Another worker cannot claim that day. A retry of the same still-running job
   uses its saved worker ID. Claims never expire automatically. A stopped worker
   needs explicit recovery after verifying it is stopped, avoiding duplicate
   work; no automatic release/takeover command is provided.
4. Cloud authors/tests/repairs and `submit`s the result with evidence. Original
   snapshots and assignments must match the request. Submitted results cannot
   change; an identical submit is idempotent. Cloud has no DB/production SSH key.
5. Raksasa `import` validates again and commits new/changed gadgets in one short
   DB transaction. Advisory lock, stable row-lock order, 2-second lock timeout,
   10-second statement timeout, original-row comparisons and Sydney-day duplicate
   guard prevent stale overwrite or multiple daily imports. No model/browser work
   is done while holding DB locks. Legacy generation does not share the advisory
   lock, so activation must be coordinated.
6. Only after DB commit does importer push `ack = SHA256(result)`. Repeated import
   after acknowledgement makes no DB connection. If commit succeeded but the ack
   push failed, retry checks `gadget_model = codex-cloud:SHA256(request)` and all
   gadget/source content before acknowledging, without another write. This can
   recover a prior day's acknowledgement via `import --day YYYY-MM-DD`. Late
   unimported results remain eligible when their original row snapshots still
   match; subsequent edits cause an explicit stale-edit failure.
7. Every staged site rebuild first invokes `import-ready`, selecting the oldest
   pending production request across Sydney days. Missing/not-yet-tested results
   are normal and cause no DB connection or failure. Actual import errors remain
   visible/nonzero but site generation and publication still proceed with the
   last tested DB state. After a late result arrives, any subsequent rebuild
   imports it; pending requests are neither expired at midnight nor overwritten.
   Raksasa then builds/publishes using existing rsync rights.

All branch mutations use isolated temporary checkouts and normal guarded
fast-forward pushes; there are no force pushes or rebases. A push race reloads
and revalidates up to three times. Unexpected data-branch files, identity or
visibility stop the operation. A result/import lost race is safe because both
Git mutations and DB imports are idempotent. Other network errors stop and retain
useful diagnostics. No claims or results are silently overwritten.

## Operational setup and rehearsal (not performed/installed)

Requirements: deploy reviewed code to both environments; Python >=3.11 with
Australia/Sydney zoneinfo, Git and the existing GitHub SSH identity; public HTTPS
to api.github.com for visibility checks. Cloud also needs working browser
automation/Chromium. Raksasa retains uv/project dependencies, existing Herodian
SELECT/UPDATE rights, API key for translation/summaries, Stephanos read access,
flock, rsync and merah SSH/destination rights. No new credentials or permissions.

1. Preserve active cron while rehearsing. Seed
   `/home/herodian/prosodia-catholica/logs/published-passages.json` from the existing
   `site/passages.json` **only after confirming that exact export was successfully
   deployed** (or fetch the actual public deployed export). Do not seed from a
   failed build. Subsequent staged publisher runs manage this automatically.
2. As Herodian, in its checkout:
   `uv run --frozen git_gadget_handoff.py enqueue --rehearsal --published-file logs/published-passages.json`
   This is allowed after the legacy generator ran, because rehearsal records can
   never import into the DB. The production daily duplicate guard remains intact.
3. Parent launches the cloud prompt below using existing GitHub auth and a browser.
   For the prepared rehearsal, pass `--day 2026-10-22` explicitly to claim/status;
   submit derives the assigned day from the bundle (explicit matching --day also
   works). Use the latest staged source revision, not the default main branch.
   Cloud `claim` and `submit` create the round trip on the data branch. Local
   `uv run --frozen git_gadget_handoff.py status` must show mode rehearsal and
   result true; inspect its actual browser evidence and submitted code. No import
   or ack is expected for rehearsal. `import` explicitly refuses rehearsal before
   opening any DB connection. Do not reuse the rehearsal day for production.
4. Only after the round trip passes and parent confirms readiness, coordinate
   cutover before the next Sydney-day legacy generation. Save exact old cron;
   confirm no pipeline is running. Install the companion maintenance/queue,
   importer and publisher entries together and remove the old combined entry.
   Do not run setup_cron.sh (it still installs the legacy pipeline). Manual first
   production cloud/import verification can precede recurring schedule activation.
   If it fails, stop the cloud schedule and restore old cron before the next due
   run, checking the day's import marker first to avoid a second gadget.

Recommended final cadence, **all Australia/Sydney** (not installed):

- 00:05 local maintenance then enqueue from the previous successful public export.
  Newly translated lines become eligible after the next successful publication.
- 00:30 daily cloud job, configured with timezone Australia/Sydney.
- 04:15 local import-ready/build/publish. This gives the cloud 3h45m rather than
  treating the original 01:10 as a deadline. It does not add another heavy build.

If retaining the established 01:15 publication time is preferable, it is safe:
that is the first import opportunity, **not** an expiry. A late result imports on
its next rebuild, including the following day. Optional/manual additional rebuilds
can reduce latency. Cloud runs skip work already submitted and wait for import;
new enqueue/claim commands resume the oldest unacknowledged production request
rather than selecting a new passage while a prior job is pending. A stopped
claimed worker still requires explicit recovery after verifying it is stopped.

Proposed Herodian entries, **not installed** (server timezone verified Sydney):

```cron
5 0 * * * cd /home/herodian/prosodia-catholica && ./run_content_maintenance.sh && ./run_handoff_local.sh enqueue
15 4 * * * cd /home/herodian/prosodia-catholica && ./run_site_publish.sh
```

No separate timed importer is required: every rebuild includes repeatable
`import-ready`. Explicit `run_handoff_local.sh import` remains available for manual
checks. Do not redirect wrappers to /dev/null: they are silent on success, retain
and replay failed diagnostics and preserve exit status. flock overlaps return 75.
Late/missing results do not stop independent site rebuilding. A real import error
is reported after publishing the previous tested DB state. Do not rerun maintenance
automatically after partial completion: existing scripts commit incrementally.
All dates and bounds use Australia/Sydney, including its 23/25-hour DST days.
No extra manual heavy overlap computation should compete with the migration.

## Prepared rehearsal evidence

On 2026-10-22 Australia/Sydney, staged source was run in an isolated
`/tmp/prosodia-git-rehearsal-20261022` checkout as Herodian. Production checkout,
cron, generator and DB contents were not changed. The public HTTPS fetch received
Cloudflare 1010; instead the exact configured deployed file was verified via the
existing deployment SSH identity. Both deployed and local public exports have
SHA-256 `e8669707a19b7c87e9df57ebd5a7d192c68e702654ee29e9ec77adf0d480981b`.
That byte-identical snapshot was seeded only in the isolated checkout.

Enqueued `refs/heads/gadget-handoff`, record `handoff/2026-10-22.json`, initial
commit `01b614694e2f184bd2d42a994a76a360e0cdd290`. Mode is rehearsal, new passage
241 (`1.244`), past gadget 68 (`1.71`), request SHA-256
`8a3999798914cf2512cf319be2c5f6bb364129972c95811ac1eaf3644571c0d2`.
Record size 46,325 bytes; no claim, result or ack existed after enqueue. Browser
claim/test/submit are pending. Rehearsal mode prohibits production import.

## Exact cloud prompt

```text
Work in the published classical-texts environment on solresol/prosodia-catholica.
Read applicable engineering instructions and docs/cloud-gadget-workflow.md.
Use Australia/Sydney for today's logical day. This is a Git artifact handoff:
no PostgreSQL, Tailscale, tunnels, production credentials, schema changes, service
restarts, site deployment or new external destinations. Preserve unrelated work.
Use only the existing authorized repository Git identity; stop if unavailable,
remote/visibility is unexpected, or browser automation is missing. No new grants.

Run python3 -m unittest discover -s tests -v. Generate a unique opaque worker UUID
for this job attempt; save it in ignored exports/ so an in-job retry uses the same
ID. Do not use a predictable daily worker ID shared by concurrent jobs. Compute
DAY with python3 -c 'from cloud_gadgets import logical_day; print(logical_day())'.
Run python3 git_gadget_handoff.py status first. Resume its pending assignment day
even if older than today; if it already has a result, report waiting for local
import and stop without reauthoring. For the prepared rehearsal pass --day
2026-10-22 to status and claim even after that day ends. Claim with
python3 git_gadget_handoff.py claim --worker WORKER_UUID --bundle
exports/gadgets-DAY.json, substituting actual values on one command line. Claim
push must succeed before authoring. If another worker owns the day, stop; do not
release or take over its claim. If no queue exists, report it and stop. Do not
select new passages or replace the randomly assigned past gadget. A rehearsal
uses the same cloud procedure; local import is prohibited by its record mode.

For the assigned new passage, author one useful self-contained educational
HTML/CSS/vanilla-JS gadget connected to its Greek text and English translation.
Follow gadgetize_lines.py's output format and gadget_validation.py's offline
constraints. Inspect the assigned past gadget and correct any broken behavior.
Render both candidates in the exact srcdoc document and sandbox="allow-scripts
allow-forms" iframe used by generate_site.py. Copy that small renderer into an
isolated test harness if necessary; importing generate_site requires DB settings
and is unnecessary. Block external network requests. Use browser automation to
exercise representative Greek input, a second distinct input, empty input and
reset where available. Assert visible output against explicit passage-derived
expected behavior, no browser errors, and usable narrow/desktop layouts. Page
load alone is not a behavioral test. Repair and retest failures. If actual browser
execution or meaningful checks fail, stop without submitting a result.

Keep original snapshots and day unchanged. Each item must contain candidate
{html,css,js} and test_evidence with browser, interaction, expected and actual;
expected and actual must match. Evidence must describe only public gadget inputs,
behavior and assertions, with at most 2000 characters per field. Do not include
secrets, environment details, private data, paths, account names, screenshots,
arbitrary logs, full site output or dumps. Candidate source is intended for the
same public site. Inspect all submitted fields for this disclosure scope.
Run python3 cloud_gadgets.py validate exports/gadgets-DAY.json. Submit only after
both browser-tested candidates pass: python3 git_gadget_handoff.py submit --worker
WORKER_UUID --bundle exports/gadgets-DAY.json. These commands need no DB or model
credentials. The helper pushes only the bounded daily record to gadget-handoff
on the existing repository; do not commit other artifacts there. If submit fails,
inspect status and retry the identical result with the same worker; never force
push or overwrite another result. Do not call local enqueue/import commands.

Report the Sydney day, worker, new/past passage IDs, repairs, actual browser
assertions/results and submit outcome. Production import remains local and is
confirmed only by its acknowledgement. Commit/push scoped reusable code/tests to
the verified existing authorized source remote only if needed; preserve unrelated
work and stop on conflicts. Do not create a PR. No undisclosed transmissions or
access to unauthorized computers.
```

## Verification limits

Offline tests cover a real local bare-Git round trip and a racing claim, immutable
results, bounded/unknown fields, published-snapshot equality, stale DB snapshots,
daily duplicate guard, commit-before-ack recovery, late-result and prior-day acknowledgement
recovery, rehearsal import refusal, Sydney 23/25-hour DST days, DB-free validation,
maintenance preservation and quiet-success/error-reporting publisher behavior.
DB checks use fakes, not production writes. Real cloud browser execution, cloud
Git permissions, cloud Git claim/browser-test/result return and production apply are still
required. The bounded rehearsal queue has now been pushed and verified. Source code push is not evidence of those actions succeeding.

No production schedule, generator configuration, credentials, services or database
schema have been changed. Existing rsync remains non-atomic; failed transfers may
need retry. Git branch history and failed local logs need normal operator retention.
