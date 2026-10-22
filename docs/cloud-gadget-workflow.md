# Staged minimal Herodian split

## Architecture and activation boundary

Keep the existing Raksasa Herodian cron, `/home/herodian/prosodia-catholica`,
`run_daily_pipeline.sh`, local git pull, schema initialization, translation,
summaries, overlaps, site generation and rsync to Merah. Only the gadget model
call moves to the daily cloud job. The multi-phase prototype scripts have been
removed; no separate maintenance/publisher/import schedules are required.

The staged script defaults to **legacy** via config.py `GADGET_WORKFLOW` (or an
environment override). That retains the existing local `gadgetize_lines.py` call.
Only after rehearsal passes and parent confirms readiness, set the existing
host config's `GADGET_WORKFLOW = "cloud"`. No cron restructure is required.
In cloud mode the old gadget step becomes a small local `import-ready` step;
after successful rsync, enqueue a public work bundle for cloud. Local import is
necessary because production gadgets live in PostgreSQL, which stays private
and inaccessible to cloud. Queue export after rsync guarantees publication of
the exact source fields before Git transmission.

No merge, mode switch or production scheduling has occurred. Default main and
production remain at `0d462afa4172baec01cb6f374830573e6adae4d9` when last checked.
Active cron remains `15 1 * * * cd ~/prosodia-catholica && ./run_daily_pipeline.sh`.
Server timezone is Australia/Sydney. All original per-host credentials remain
local. No new keys, grants, SSH configuration or VPN changes.

Cron success is silent. Existing detailed pipeline/date logs remain. Failures
retain a per-run log, replay useful diagnostics to original stderr and return
nonzero, including the original build failure status. In cloud mode a real
handoff error is recorded but existing overlaps/build/rsync still proceed. A
missing/not-yet-tested result is normal. Existing git pull behavior stays local
and unchanged, including its existing policy of logging a failed pull and
continuing. Default daily limits and original translation/summary API calls stay.

## Existing destination and transport

Existing public repository: `solresol/prosodia-catholica`. The helper verifies
public visibility through unauthenticated GitHub metadata, and resolves the
**existing source checkout origin**, including effective push URL. Supported
forms normalize to that exact identity:

- `https://github.com/solresol/prosodia-catholica[.git]` (optional trailing slash);
- existing local `git@github.com:solresol/prosodia-catholica[.git]`;
- existing local `ssh://git@github.com/solresol/prosodia-catholica[.git]`.

It preserves the configured transport: cloud's verified HTTPS origin stays
HTTPS; Raksasa's existing SSH origin stays SSH. It rejects other repositories,
lookalike hosts, embedded credentials, custom ports, HTTP, multiple origins,
query/fragment components and fetch/push transport mismatches. No remote is
rewritten or SSH setting changed. HTTPS rehearsal reads have passed; this is
not proof of cloud branch-update rights. A successful real claim push is the
next write-permission test, using the environment's existing Git credentials.

Public fields: id, ref, Greek, English translation, gadget HTML/CSS/JS. They
already occur in the site's `passages.json`. Prepare requires exact equality
between DB rows and a successfully published snapshot. No credentials, private
annotations, DB dumps, full site output or arbitrary logs enter Git. Candidates
are intended for the same site's publication. Browser evidence must contain only
public gadget inputs, expected behavior, actual assertions, public test-harness
source and bounded independent-review notes. It must not include paths, account
names, environment details, credentials, screenshots or unrelated data. No
additional data-sharing approval gap is identified within that scope. Allowlists
and size limits are not a secret detector; inspect actual evidence before submit.

## Queue, delayed import and cutover safety

Dedicated branch `gadget-handoff` contains only `handoff/YYYY-MM-DD.json` with
`{mode,request,claim,result,ack}`. Day is always Australia/Sydney. One opaque
worker UUID owns a claim; another worker cannot take it over. No auto-expiring
claims. Submitted results are immutable; identical retries are idempotent even
after midnight. Result day and all original row snapshots must match the request.

Enqueue/claim resume the oldest unacknowledged production work across days rather
than creating conflicting assignments. Late results do not expire at midnight.
Every existing daily cron run in cloud mode attempts ready import before building.
An unchanged late result is imported by the next run (or a manual invocation of
the same pipeline). Already acknowledged imports do not connect to the DB.

Import has a shared PostgreSQL transaction advisory lock, stable row-lock order,
2-second lock timeout, 10-second statement timeout, source snapshot comparisons,
and an atomic new/repair commit. The staged legacy generator uses the same lock,
so it cannot run concurrently with import. A legacy-generated gadget on the
actual Sydney import day blocks production import; prior acknowledged cloud
imports do not prevent enqueue of the next daily cloud assignment. One assignment
per request day is enforced by the immutable Git record, not by expiring results.

After commit, import pushes ack = SHA256(result). If the DB commit succeeds and
ack push fails, retry verifies `gadget_model = codex-cloud:SHA256(request)` and
full candidate/source equality before acknowledging without another update.
Further source edits cause a stale failure, never overwrite. Git mutations use
isolated temporary checkouts, normal guarded pushes and at most three race
reloads; no force pushes or rebases. Real transaction rollback/concurrent DB
behavior has not been tested against production; current DB tests use fakes.

Transition must still verify **no old-version generator process is running**
before enabling cloud mode/import. Old production processes do not retroactively
acquire the new shared lock. Keep legacy mode and existing cron until the actual
cloud rehearsal is complete, then confirm readiness and coordinate the switch.
Do not run both generators. Save old config for rollback; inspect import markers
before returning to legacy to avoid generating a second gadget that day.

## Prepared rehearsal (ID already known)

- Mode rehearsal; import prohibited before any DB connection.
- `refs/heads/gadget-handoff`, initial commit
  `01b614694e2f184bd2d42a994a76a360e0cdd290`.
- Record `handoff/2026-10-22.json`; new 241 (`1.244`), past 68 (`1.71`).
- Request SHA-256
  `8a3999798914cf2512cf319be2c5f6bb364129972c95811ac1eaf3644571c0d2`.
- Queue was created from a byte-identical deployed/public snapshot, SHA-256
  `e8669707a19b7c87e9df57ebd5a7d192c68e702654ee29e9ec77adf0d480981b`.
  HTTPS fetch received Cloudflare 1010; exact deployed-file equality was verified
  with the existing authorized Merah deployment identity instead.
- Prepared in isolated `/tmp/prosodia-git-rehearsal-20261022`; production checkout,
  cron and DB contents unchanged. Latest HTTPS read found it unclaimed/no result.

From latest staged source with the cloud's existing verified HTTPS origin:

```sh
mkdir -p exports
# Generate once per attempt; save and reuse this UUID for in-job retries.
WORKER=$(python3 -c 'import uuid; print(uuid.uuid4())')
printf '%s\n' "$WORKER" > exports/rehearsal-worker.txt
python3 git_gadget_handoff.py claim --day 2026-10-22 --worker "$WORKER" --bundle exports/gadgets-2026-10-22.json
# Perform actual browser tests and independent review described below.
python3 cloud_gadgets.py validate exports/gadgets-2026-10-22.json
python3 git_gadget_handoff.py submit --day 2026-10-22 --worker "$WORKER" --bundle exports/gadgets-2026-10-22.json
```

Keep the existing 01:15 Sydney cron. A daily cloud run at **03:00 Australia/Sydney**
allows it to consume that run's queued public data; its tested result imports on
the following daily cron. This is intentionally asynchronous, with no tight
same-night deadline. A delayed result waits for a later cron, never disappears.
Parent configures the cloud automation timezone; no hardcoded UTC/DST conversion.

## Browser confinement, evidence and limits

The actual production srcdoc renderer now installs CSP **before** gadget content:
no default resources, connections, external scripts, frames, objects, media,
forms or base URL changes; inline gadget JS/CSS and data images are allowed.
Existing iframe sandbox prevents top navigation/popups. Static checks additionally
reject protocol-relative URLs, navigation/resource HTML attributes, sendBeacon,
location and common window.open forms, besides existing network APIs.

This is defense in depth, not an offline JavaScript proof. CSP does not reliably
forbid every possible self-navigation, and obfuscated JS can evade regex checks.
Browser testing must intercept/abort all external requests and independently
review the submitted source. Runtime CSP confinement itself must also be tested
in the actual cloud browser; source/unit tests are not a substitute.

For each new/past gadget, evidence must retain:

- `browser`, `interaction`, `expected`, `actual` strings (each <=2000 chars);
- `candidate_sha256 = cloud_gadgets.digest(candidate)` to bind evidence to source;
- `assertions`: 3–20 real browser assertion records, each
  `{case,expected,actual,passed}`, with matching expected/actual and passed true;
- `harness`: the actual executable browser test source (<=32000 chars);
- `review`: `{reviewer,notes}` from a reviewer independent of the author UUID
  (bounded public notes, no personal/private identity details).

The helper validates schema, bounds, source binding and consistent results. It
**cannot authenticate browser execution or reviewer independence**. Fabricated
strings/harnesses are not proof. Actual browser execution, retained assertions
and independent inspection are mandatory before submit; if unavailable, stop
and report rather than inventing evidence. Parent must inspect this evidence
before approving production activation. Each source/text field <=64000 chars;
each bundle <=512KB; unknown fields are rejected.

## Exact daily cloud prompt

```text
In classical-texts, work only on solresol/prosodia-catholica. Read applicable
engineering instructions and docs/cloud-gadget-workflow.md. Keep existing local
Raksasa cron, git pull, translation, summaries, overlaps and Merah publication
local. Use the existing verified HTTPS origin and existing Git credentials; do
not change remotes, SSH config, credentials, grants or security settings. No
PostgreSQL, VPN, production SSH, schema jobs or site deployment from cloud.

Run python3 -m unittest discover -s tests -v. Inspect git_gadget_handoff.py status.
Resume its oldest pending Sydney assignment, even if older than today. If result
already exists, report waiting for local import and stop without reauthoring.
For rehearsal, explicitly use --day 2026-10-22 for status/claim; its ID is known.
Create/save a unique opaque author worker UUID in ignored exports/ and reuse it
for retries. Claim with git_gadget_handoff.py claim --worker UUID --bundle
exports/gadgets.json (plus rehearsal --day when applicable). Claim push must
succeed before work; stop on missing access or another owner's claim. Never
force push, reset another claim, or alter the assigned day/original snapshots.

Author one self-contained useful educational HTML/CSS/vanilla-JS gadget for the
assigned new Greek/translation passage. Inspect the assigned random past gadget,
correct broken behavior and retest. Use the actual production gadget_srcdoc
renderer/CSP and same sandbox iframe in an isolated harness; extract the renderer
without importing DB helpers if necessary. Intercept/abort external browser
requests. Exercise representative Greek input, a distinct second input, empty
input/reset, narrow/desktop layouts and browser errors. Assert passage-derived
expected visible behavior, not merely page load. Verify runtime CSP blocks
resource/connection/form probes in a separate confinement test. Static regex
checks alone are insufficient. Stop if actual browser testing is unavailable.

Retain the actual executable harness, 3–20 actual passing assertions per gadget,
and bounded browser/interaction/expected/actual summaries in test_evidence. Bind
them with candidate_sha256 = cloud_gadgets.digest(candidate). Obtain actual
independent source/assertion review; record its distinct opaque reviewer and
public notes. Do not self-review or invent execution/review evidence. If an
independent reviewer is unavailable, stop before submit and report that blocker.
Keep only already-public gadget inputs, behavior and test source in evidence;
exclude secrets, environments, paths, account names, screenshots and arbitrary
logs. Fix failures and rerun actual tests/review before changing the source hash.

Run python3 cloud_gadgets.py validate exports/gadgets.json, then submit via
python3 git_gadget_handoff.py submit --worker UUID --bundle exports/gadgets.json.
The helper pushes only the bounded record to gadget-handoff using existing HTTPS
auth. Identical late retries use the same worker/result; never overwrite a stored
result. Do not call local enqueue/import. Report assignment day/IDs, actual browser
assertions, repairs, independent review and submit outcome. Rehearsal can never
import into production. No PR, undisclosed transmissions or unauthorized hosts.
```

Unit/local-Git tests cover normalized remotes, real local Git claim races, delayed
work, immutable midnight retries, request/day binding, evidence/source binding,
rehearsal isolation, DB-fake stale/duplicate/recovery behavior, Sydney DST, actual
renderer CSP presence and the original pipeline's complete step order, quiet
success and failure reporting. Real cloud write/browser tests, independent review,
and real DB rollback/concurrency remain unverified. No production activation.
