# Staged CI replacement

This is a draft, not an active deployment. Existing scheduling remains in place
until an explicitly approved project runner and a real deployment test succeed.
No access registration, credential change or production cutover is performed by
these files.

## Local configuration boundary

The approved runner must receive HERODIAN_DEPLOY_ROOT and HERODIAN_DEPLOY_USER
through host-local configuration. Values are not committed or supplied through
cloud secrets. The deployment wrapper checks the existing checkout, expected
execution identity, clean main branch and authorized origin. Actual destination
settings come from the existing local config module. No host paths, account
values, access-grant descriptions or private diagnostics are published here.

The existing build uses PostgreSQL while the visitor-facing site is static.
Working data and credentials stay local; Git handoff records contain only the
previously approved public passage/gadget/evidence fields. CI does not migrate
the database or author replacement gadgets.

## Execution design

- Hosted checks validate the exact public source commit without production access.
- Trusted-main deployment supports scheduled polling, an explicit manual trigger,
  source pushes and repository_dispatch type gadget-result. Automatic deployment
  stays disabled unless HERODIAN_CI_ENABLED=true; manual main execution is intended
  for the approved pre-cutover trial.
- Merely adding push filtering for the orphaned gadget-handoff branch would not
  run a workflow present only on main. Result notifications require a verified
  existing dispatch capability; hourly polling is the fallback without new tokens.
- All local pipeline callers share the same file lock, including an inherited
  descriptor validated against that lock inode. Source updates are fast-forward
  only and must match the workflow's exact trusted commit.
- Daily maintenance records started/done receipts by Australia/Sydney date.
  Repeated daily triggers use publish-only mode; incomplete source receipts need
  inspection instead of a blind second batch. This handles delayed triggers and
  either DST offset. Hourly polls after 01:00 request daily work, but run it once.
- Publish-only mode imports ready results, builds, publishes and queues public
  work without repeating source maintenance. Existing request identity, stale-edit
  checks, DB transaction locking, marker/ack recovery and rehearsal exclusion stay.
- A successful import/ack is not a successful publication. After the pipeline
  succeeds, CI compares a live deployment manifest checksum with local output.
  Only then is a local publication receipt written. Unchanged verified inputs can
  skip a repeat build. Detailed failures remain local; public logs show only a
  bounded status, source SHA and public manifest hash.

## Preconditions and cutover order

1. Obtain any required project-runner registration approval separately. Configure
   the two host-local settings above. Do not borrow another project's execution
   rights or change privileges as part of this draft.
2. Review/merge the source and safely fast-forward the existing production checkout
   with no old pipeline running. Install shared locking before the first CI trial.
   Keep existing scheduling active.
3. If maintenance already ran using the older unreceipted script, seed today's
   completion receipt only after independently verifying its successful log.
4. Test a manual publish-only deployment at the exact reviewed commit, including
   ready-result import, acknowledgement and live manifest verification. Inspect
   actual CI and live evidence; a handoff result alone does not meet this condition.
5. Test daily-mode responsibility coverage and future schedule windows while the
   previous scheduler remains present. Enable automatic CI only after that passes.
6. Save the existing scheduler/config/source rollback snapshot, confirm the next
   tested CI window, and only then remove this project's previous schedule entry.

Rollback disables automatic CI and waits for a running job before restoring the
saved schedule. Preserve daily receipts and queue records; inspect incomplete
source work and publication state separately. Do not duplicate an uncertain batch,
force-reset claims or discard a pending result. Existing periodic execution can
continue to consume pending results while runner access remains unresolved.

## Verification limits

Local tests cover shared/inherited lock contention, publish-only responsibility
separation, Sydney daily deduplication, refusal of uncertain source retries,
existing queue/import idempotency and invalid deployment-commit rejection.
Optional isolated PostgreSQL tests remain available. No production deployment
through the proposed runner has succeeded yet; registration/access approval is
still a prerequisite. The existing production schedule remains unchanged.
