# Hosted lifecycle

The hosted workflow is gated by `HERODIAN_HOSTED_LIFECYCLE_ENABLED`. It runs on
trusted main pushes, explicit dispatch and hourly at minute 17. Sydney logical dates
remain in the handoff protocol across DST. An orphan handoff-branch push alone is
not assumed to start a main-only workflow; polling recovers delayed results.

One non-cancelling workflow concurrency group covers initial exact-SHA checks,
content reconciliation, resulting-SHA tests/build, SSH publication/checksum verification,
publication receipt and next assignment enqueue. PR code cannot enter this workflow.
Authentication uses the temporary repository token, including temporary queue clones;
no personal Git key or persistent runner is involved. A token-made content push does
not recursively trigger Actions, so resulting-SHA tests/build run explicitly in the
same job. Main advancing causes refusal before publication/enqueue; retry picks up
the new source. No force push or source reset is used.

The importer retains production-mode/identity/candidate checks, retained browser
assertions/harness/review, exact stale snapshots and content receipts. It commits and
pushes before acknowledgement; a failed ack recovers idempotently. Acknowledgement
means stored, not published. No publication cache exists: publication retries use
current content and late results arriving during publication are imported next poll.
A receipt is written only after complete deployed checksum parity, then retained as
a workflow artifact even if enqueue fails. A failed enqueue retries after verified
publication. No later remote handoff HEAD is marked consumed. Repeated builds use
SOURCE_DATE_EPOCH from the exact content commit.

## AI belongs in Codex Cloud

CI and site rendering do not load model clients, generate text/gadgets, or need an
OpenAI key. Existing API utilities remain legacy/manual tools, outside the hosted
workflow. There is deliberately no `OPENAI_API_KEY` secret.

Current public content has 544 translations and 544 summaries: no work is pending.
For future missing text, update the daily Codex Cloud prompt:

> On a clean current-main checkout, first run `python cloud_text.py prepare --bundle
> /tmp/herodian-text.json`. If no work is pending, continue. Otherwise preserve the
> request exactly and produce only its requested missing English translations and
> summaries: at most five translations and 25 summaries for that Sydney day. Follow
> the existing SYSTEM_PROMPT/USER_PROMPT in translate_lines.py and summarize_lines.py,
> preserving Greek interpretation, qualifications and source references. Never replace
> an existing accepted field or change Greek, IDs, references, timestamps or gadgets.
> Fill `candidates` in request order: each contains `id` plus exactly its requested
> fields. Obtain independent source-fidelity review; retain a bounded `review` object
> with `reviewer` and `notes`. Run offline tests, then `python cloud_text.py apply
> --bundle /tmp/herodian-text.json`. This applies only unchanged snapshots, atomically
> stores a daily receipt, commits/pushes content and refuses conflicting retries.
> Report the commit; publication is pending CI. Do not call a model API or load API
> keys. Continue the existing gadget claim/generation, actual browser/CSP testing,
> independent review and submission protocol unchanged. Never import/ack/publish from
> the cloud job, and never regenerate a submitted gadget result.

The text helper has no model client. A late same-day result retains its identity;
receipts prevent additional batches on that day. Missing-text work is assigned only
from existing public rows; no private source attachment or excluded record is added.

## SSH and cutover

Use only the explicitly approved repository deployment key and pinned host-key
variable. Private key material is written to a mode-600 temporary file and removed
on exit. The destination user is fixed to `herodian`; only the existing site's host
and destination variables are used. No database/network/runner privileges change.

Keep cron until independent review, exact-commit checks and an actual complete hosted
production cycle pass. Test during a quiet interval with no local run; both local and
hosted writers must not run concurrently. After success remove only this project's
cron entry, preserving its exact contents privately. No broad runner/account setup.
Rollback disables the hosted lifecycle gate, waits for any run to finish, retains all
Git receipts/new content, then restores the Git-backed local cron. Do not resume the
old DB importer. Preserve deployment artifacts/checksum receipts and database rollback.
