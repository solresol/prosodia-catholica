# Hosted SSH deployment preparation

No runner label or credential is assumed. Existing Raksasa registrations belong to
other repositories/organisations; this personal-account repository currently has
no eligible runner, repository secrets or environments.

The prepared manual publication workflow is OFF unless the explicit repository
variable `HERODIAN_SSH_PUBLICATION_ENABLED` is true. Do not enable it while cron
owns the lifecycle. It accepts only a successful current-main offline-build run,
downloads that exact SHA's artifact, pins SSH host keys, uses the fixed remote user
`herodian`, and compares all deployed checksums before retaining a publication
receipt. No database, host account, runner or credential configuration is changed.
Host, destination and trusted public host keys use repository variables; no private
infrastructure values are committed. The deployment key is an explicitly supplied
repository secret named `HERODIAN_DEPLOY_KEY`, not a personal SSH key.

This is the tested transport/publication component, not the complete controller.
It intentionally cannot retire cron or claim handoff reconciliation. Before enabling
it, finish the hosted lifecycle controller: hourly Sydney-aware daily maintenance
and pending-result polling; explicit manual trigger; trusted current-main check;
content commit/push before result ack; tests/build for the resulting SHA; publication;
then enqueue from the verified published snapshot. Keep maintenance completion and
publication receipts separate, persist the actually consumed handoff snapshot, and
never skip a late result merely because it arrived during publication. Normal-token
Git pushes do not recursively trigger Actions; the controller must explicitly run
checks/build for its resulting SHA. A result push to the orphan data branch does
not by itself execute a main-only workflow. Use polling as recovery even if an event
trigger is later added. One global workflow concurrency group must cover the whole
lifecycle, with no cancellation mid-transaction.

Full hosted maintenance additionally needs the existing model API key made available
as `OPENAI_API_KEY`; currently no such repository secret exists. Keep current prompts,
models, successful-item persistence, daily limits and non-public error handling.
No-pending work must not require an API call. Credential configuration is a separate
explicit approval step, not implied by preparing this code.

Activation requires credential approval, completed/tested controller integration,
exact-SHA checks, duplicate and failure/retry tests, and one complete verified
production cycle. Coordinate cron exclusion before hosted mutations. Preserve its
existing entry and all current Git/DB rollback evidence. Do not merely enable this
manual publisher and remove cron: that would orphan import and enqueue.
