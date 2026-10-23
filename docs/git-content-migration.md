# Git content migration (staged, not activated)

`content/passages.json` is a canonical UTF-8 JSON snapshot containing the same 544
public records and fields as the existing `passages.json` endpoint. Unicode code
points, IDs, references, ordering and accepted gadget source are preserved. The
original private transcription attachment, operational model errors, credentials,
account metadata and retired overlap tables are excluded. The edition and existing
public site are cited; no new licence is asserted for the transcription.

`content/legacy-lines.json` preserves the existing, already published legacy URL
byte-for-byte. This older endpoint contains 545 four-field records, including E;
it is a frozen compatibility artifact, not an additional editable passage. Its
publication was verified against the existing deployment by SHA-256 before copying.
The private attachment itself is not included. The canonical 544-record corpus
continues to exclude E. New work should use `passages.json`.

## Storage and concurrency

The canonical snapshot has an exact field allowlist, unique IDs/references and
bounded safe provenance. A single atomic JSON replacement includes content and
reconciliation receipts, avoiding multi-file partial transactions. Stable IDs and
references are never renumbered. Translation and summary functions/prompts are
reused with their existing model defaults. Failures never enter public content;
successful items are retained and failure exits nonzero. No work loads an API key
when nothing is pending. The legacy DB utilities remain for rollback only.

Cooperating local writers hold `content/workflow.lock` through generation or the
complete import/commit/push/ack operation. Atomic content writes additionally hold
a content lock and compare the original bytes before replacement. Git pushes use
normal fast-forward semantics. Remote advancement stops publication; inspect and
reconcile, never force push. Before a push, unrelated working changes/unpushed
commits are refused. A retry can push one unpushed content-only reconciliation
commit. Failed pushes retain local evidence and require inspection. After reviewing the
retained diff, run `python git_content_workflow.py recover-content`; this validates
the allowlist, refuses unrelated changes/commits, and pushes only the content file
under the shared lock. It never acknowledges or publishes. Then rerun the pipeline.
This explicit recovery is required after retained dirty content; the normal pipeline
refuses to guess whether an interrupted write has been reviewed.

## Gadget handoff

The existing `gadget-handoff` branch, Sydney dates, worker claim/submit command and
browser assertions/harness/independent review remain unchanged. Static gadget
validation and the renderer CSP remain in force; evidence is retained, not treated
as proof that arbitrary JavaScript is safe. `git_content_workflow.py import-ready`
validates identities and exact original snapshots, atomically applies candidates
plus a receipt, commits and pushes content to main, verifies remote equality, and
only then acknowledges the original handoff result. Acknowledgement means stored
in Git, not published. A receipt makes delayed/retried imports idempotent and
rejects post-import edits or a conflicting result. Rehearsals cannot import.
Already acknowledged DB work without a matching Git receipt stops for explicit
reconciliation rather than guessing. Past/new source checks are unchanged.

The outstanding Oct 23 new241/past181 result must be reconciled exactly once by
this importer only AFTER coordinated cutover, with the DB importer stopped.
Do not regenerate, edit or acknowledge it during preparation. Retain all original
handoff request/result/test evidence. If the old cron imports it before cutover,
re-export the published canonical snapshot and explicitly seed a verified receipt;
do not apply it again. Recheck this state immediately before activation.

## Build and deployment

`python tests/offline_build.py --out site` forbids DB imports and network sockets.
It needs only Python's standard library and repository files. `SOURCE_DATE_EPOCH`
fixes generated timestamps for repeatable builds. The progress page intentionally
counts the 544 authoritative public records, no private TSV inventory or historical
DB processing timestamps; task capacities remain configurable. Passage HTML,
canonical URLs, content and CSP remain unchanged apart from build timestamp.

The hosted workflow runs tests, an offline build and uploads an artifact bound to
its SHA. It does NOT claim publication or provide new deployment access. No runner,
credentials, firewall settings or persistent access are created. Existing private
host deployment configuration remains local.

`run_git_pipeline.sh` is a staged local replacement, not enabled: fast-forward,
translation/summary, commit/push, tested handoff reconciliation, offline build,
existing rsync route, then enqueue from the successfully published snapshot. It
keeps success quiet and failure nonzero. No DB initialization/import/gadget API.
Do not run it alongside the legacy cron. A production activation needs independent
review, a fresh parity check, explicit main integration and coordinated replacement
of the old cron invocation (keep its timing until a verified CI delivery route
replaces it). Keep cloud at 03:00 Australia/Sydney; its claim/submit protocol is
compatible, but update its prompt to the Git authority and forbid DB import or
manual content edits bypassing reconciliation. Results arriving after a rebuild
remain pending until the next successful run; never discard them at midnight.

A true hosted-CI-to-Merah deployment still needs an approved execution route. The
previous self-hosted-runner grant is not assumed. Cron cannot be retired until that
route and exact-SHA deployment verification pass. The old `ci-redacted` DB draft
must not be activated or merged into this migration.

Rollback retains the intact DB and previous source/output. Before resuming the
DB-backed pipeline, pause cloud imports, preserve any newer Git results and
reconcile them explicitly; blindly reverting after new Git writes loses content.
No tables, rows, historical data or credentials are deleted or changed here.
