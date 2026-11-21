# Operations, continuous deployment, and recovery

## Starting state and target

The current Blueprint starts a FastAPI process against a pre-existing SQLite database on disk and has `autoDeployTrigger: 'off'`. The current CI checks for secrets and runs two Python suites; the local script checks for secrets and the previous MVP. The APK does not pass through that CI. [Current Blueprint](../../render.yaml) · [Workflow](../../.github/workflows/ci.yml) · [Demo runbook](../despliegue-render.md)

Keep the demo accessible and isolated. For the pilot, use a Render web service with HTTPS and managed PostgreSQL in the same region. Use different secrets and identities per environment, with appropriate sender and OIDC realm. Agent access to local work does not require access to production keys. Price the web instance, database, copies, identity, and traffic; obtain budget approval before creating new paid resources. Apply the decision transition specified in the startup manual.

## Pipeline to implement

1. PR to main: redacted secret scan, backend Python tests, and MVP regressions while supported; migration and isolation testing with disposable PostgreSQL, web tests for affected flows, and Android debug unit tests/build for Android changes or shared contracts. Add stable required checks that also resolve documentation changes; a skipped job must not leave a required check perpetually pending.
2. Rehearse every migration from a controlled copy without exporting the database to models. The migrator process uses an identity different from the service. Serialize migrations and deployments; use expand → resumable backfill → switch reads → contract once the previous version and its APKs are out of support. Preserve indexes, foreign keys, and reconciliations from the cutoff.
3. After green integration of main, enable automatic deployment after checks, without human approval per release. Confirm the effective service, branch, and policy in the Blueprint and dashboard; avoid two different triggers for the same SHA. Expose the compiled version and database health without sensitive data. Production smoke tests are read-only: landing page, version, available databases, and anonymous denial of restricted views. The synthetic end-to-end test with writes goes to a segregated test tenant and is excluded from metrics.
4. The integrator associates SHA, CI run, deployment, and metrics window. If readiness or smoke tests fail, stop promotion or restore the previous application that is compatible with the expanded schema. Verify queue, data, and health; open an incident. An application rollback does not undo sales or migrate a database backward by default.
5. Pilot APK: release build signed by a custodian or protected job, publish version, changes, certificate fingerprint, and SHA-256 of the file on the product domain. Test clean installation and in-place update with pending offline work. Configure App Links with the distribution certificate fingerprint. Keep the key and a recoverable backup outside the repository. Maintain the contract for the previous supported version; a mandatory update allows exporting or recovering pending work first.

Render and its deployment behavior are revalidated during execution. [Render Deploys](https://render.com/docs/deploys) · [Android App Links](https://developer.android.com/training/app-links)

## SMTP2GO email

- Sender `mailer@abarpay.app`, host `mail.smtp2go.com`, port `2525`, mandatory STARTTLS, and certificate and hostname validation. Separate the sender name from the SMTP identity. Define `SMTP_HOST`, `SMTP_PORT`, `SMTP_USERNAME`, and `SMTP_PASSWORD` in the environment that actually sends email. For the identity provider, configure its custom sender if it delivers verification and recovery. No plaintext fallback.
- Replace the exposed password and load the replacement directly into Render. In the Blueprint, version only secret references without values. Resolve DKIM and domain verification in SMTP2GO; check SPF/DKIM/DMARC alignment through the headers of a test message in an authorized mailbox. Verify real connectivity from the selected Render plan. [SMTP2GO setup](https://www.smtp2go.com/setup/)
- Generate email through a transactional outbox tied to event, recipient, and template. Use a stable unique ID and expiration for invitations and recovery. Avoid invitation references or access links in logs. Record queued, accepted by provider, bounced, expired, and retryable-failure states; SMTP acceptance does not prove inbox delivery. Use independent consent and opt-out for credit-sale reminders; templates must not reveal balances in the subject line.
- Tests: local capture SMTP with fictional mailboxes, missing STARTTLS, timeout, bounce, and expired link. Then perform one authorized real delivery, confirmed by the recipient. An uncertain result after DATA requires reconciliation; limit retries and do not generate different valid links in a cascade. Separate email tests from the local Telegram notifier.

## Backup, restoration, and observability

**Initial pilot objectives:** propose RPO ≤1 h and RTO ≤4 h, and compare them with the effective coverage of the contracted plan. If they are not met, show the gap and cost to Carlos before public launch. Encrypt backups, restrict access, and rehearse an isolated restoration without affecting the service. Validate counts by tenant and references, amounts, debt, inventory, latest available event, and time to a healthy service. Record **measured** RPO/RTO. Inject an event after the restored point to demonstrate how to detect and reconcile the gap. Never overwrite the demo's active disk with an old copy.

| Initial signal | Owner / action |
|---|---|
| Consecutive health failure or 5xx >2% for 5 min with ≥20 requests | Operations: check release and database; if deployment caused a regression, apply a compatible rollback |
| Bank registration older than five business days, recurrent invalid webhook, or unresolved CoDi difference | Payments: query pey by reference and tenant; preserve traceability without bodies or CLABE |
| Email, sync, or job queue with no progress for 15 min while connectivity is demonstrated | Operations: identify the consumer, review the typed error, and resume from the operation; do not duplicate business |
| Database/disk >80%, backup failure, or restoration without evidence within 30 days | Infrastructure: review growth, retention, and recovery; raise budget before expanding resources |
| Campaign without attribution, suppressed report, or pending consent withdrawal | Business/privacy: show coverage and reason, and block delivery when appropriate |

Distinguish a sale that occurred on a disconnected phone from a server synchronization backlog. Measure latency percentiles, age, and count with window, version, and region. In the drill, induce a reversible error in tests and observe notification, response, recovery, and time. In public evidence, use only fixtures and redacted metrics. Avoid session tokens, CLABE, email, payment payload, debt, or phone serial number. Identifiable support records require audited access.

## Operational runbook delivery

Document domain/DNS owner, access by role, rotation, retention policy, user offboarding, access/deletion requests, support contact, compromised-account procedure, bank replacement, isolation incident, phone loss, and restoration. Verify device and session revocation; an offboarding must resolve pending offline sales with traceability. Each incident includes containment, preservation of movements, communication to the responsible owner, and recovery proof.
