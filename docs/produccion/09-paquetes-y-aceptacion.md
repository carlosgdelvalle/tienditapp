# Work package board and definition of done

The coordinator opens a package when evidence shows its prerequisites are met. Use the stable IDs to track blockers, branches, and reviews. The scope column assigns a logical area. Before dispatch, specify the actual writable files and integration point. An accepted contract lets a client team build against a fixture while the service is under development. For integrated milestones, verify that the fixture and live test service agree.

| ID | Depends on | Owner and scope | Outcome for another session to verify |
|---|---|---|---|
| E0 Environment | Start | Pro coordinator, DSH environment | Verify the effective CLI and model, independent review session, restart, Python/Android baseline, and ignored paths. Record external dependencies such as the phone or bot separately |
| E1 Notifications | E0 environment | Flash local operations | Configure the bundled notifier. Test preview and deduplication in isolation, then confirm one real notification in the authorized private chat. Simulate a failure and process a test resolution without invoking Astra |
| D1 Workflows | E0 | Pro industrial engineer, interaction design before code | Document each journey in guide 03, reconcile the Trello matrix, and cover steps, recovery, and accessibility. A developer discusses and signs off on each card before building its screen |
| D2 Contracts | E0 | Pro domain owners, API and invariants | Inventory routes, jobs, and events. Define tenant, banking, offline journal, and metric contracts using two test tenants with one store each. Freeze each domain contract and notify its consumer |
| D3 Commercial | E0 | Flash commercial analyst with Pro review | Supply copy and offer definitions, funnel, event taxonomy, and the four reviewers’ decisions. Check against the 28-day fixture |
| I1 Tenancy | D2 tenancy | Pro backend/database, sole migration owner | Verify PostgreSQL, store context, RBAC/RLS, clean seed data, two stores, and pooled connections. Counts and totals reconcile in a migration rehearsal |
| I2 Identity | D2 identity + relevant D1 flow | Pro auth, Flash web/mobile in separate worktrees | OIDC signup and recovery, invitations, store selection, QR, manual code, sessions, Entra/MFA. Changing membership or reporting a lost phone revokes access |
| I3 Mobile persistence | D2 sync + D1 checkout | Pro synchronization, Kotlin and server contract | Encrypted local database, atomic outbox, receipts, and resumption. Interrupt acknowledgement and restart. Exactly one durable operation survives |
| I4 Platform | D3 + D2 roles | Flash platform web | Separate navigation for health, growth, revenue, and data, including loading and empty states. Use fixtures labeled SIMULADO until the aggregate data sources are connected |
| I5 CI and infrastructure | E0, plus D2 for database work | Flash CI, Pro integration | CI covers backend, migrations, isolation, and Android changes. Verify workflow behavior for PRs and main. Local infrastructure can proceed before Render budget approval |
| I6 Landing page and APK | D1 access + D3 | Flash public site | Mobile and desktop CTAs, pricing and transparency, owner QR entry, and funnel. Gate publication of the signed APK on G2 |
| M1 Onboarding and CLABE | I1 + I2 + D1 | Pro banking, Flash screens | New store contains no demo data. First cash sale requires no banking information. Show asynchronous status and email. Route collection explicitly to the tenant’s active account |
| M2 Checkout and till close | I1 + I3 + I2 + D1 | Pro checkout, Flash till close | Offline cash, last-unit conflict across two tills, handover, acceptance, audited variance, and retries. Use a physical phone plus a second client |
| M3 Purchasing and replenishment | I1 + I3 + D1 | Pro inventory, Flash client | Follow supplier → order → offline goods receipt → discrepancy → approval → stock. Two receipts for the same shipment create a traceable case without doubling inventory |
| M4 Store credit (fiado) | I1 + I2 + D1 | Pro debt ledger, Flash interface | Due dates and limits, authorized override, partial repayment and payoff, opt-in reminder, permissions, and export on Gratis |
| M5 Email | D2 + I2 contract | Flash services | Sender, queue, and bounce handling for invitation, verification, and recovery. Test TLS against a capture server. Keep OTPs and access links out of telemetry |
| M6 Analytics and Control | I1 + I4 + D3 | Pro metrics, Flash views | Durable event sources, manually billed pilot subscription, campaign and owner, fixture reconciliation, and access separation for analytics, finance, and support |
| M7 Aggregate-data partner | D2 consent + I4 + D3 | Pro privacy, Flash reporting projection | Opt-in and withdrawal, simulator, controlled publication, and delivery ledger. Independent reviewer reproduces one suppressed and one eligible report |
| G1 Integration | I1–I6, M1–M6 | Pro integrator and independent verifiers | Walk through Android and browser journeys in an isolated environment with two independent tenants, one store per tenant. Record latency, slow-network and physical-phone results, incidents, restoration, and rollback |
| G2 Public pilot | G1 + applicable external decisions | Pro operator | Verify automatic CD by SHA, signed upgradable APK, authorized real email, live page, and live metrics. Keep CoDi pending until provider approval and human payment verification |
| G3 Commercial operations | G2, plus M7 for the partner | Business team and Pro data agent | Control with consented charges and segregated real data. Deliver aggregates only with a partner, consent, and legal review. Formalización and dossier research contribute zero money until a real financial event occurs |

**Critical path:** E0 → D2 → I1/I2/I3 → M1/M2 → G1 → G2. E1, D1, and D3 run in parallel. Scope external blockers to the affected capability. M1 can implement and verify simulated registration without a real CLABE, E1 can test failures without a token, and M7 can demonstrate suppression and synthetic delivery without a buyer. Record partial completion and the outstanding external proof.

### Dependency between purchasing and margin reports

In M3, record purchase cost in cents and quantity received when a stock receipt is approved. In M6, snapshot the weighted average cost in effect at sale time on each historical sales line. Calculate gross merchandise margin as net sales less attributable cost on the same basis, quantity, and currency. Document discounts and returns. Show lines with unknown cost or offline conflicts separately and report coverage. Never impute zero cost. A later purchase cannot change a closed margin. B5 covers two purchases at different costs, a partial sale, a return, and an item with missing cost. Verified payment reconciliation applies to every plan. Control adds operational tools and reports.

## Acceptance scenarios and evidence

| Scenario | Procedure and expected outcome |
|---|---|
| B0 · Baseline | In a Python 3.12 venv with app and server dependencies, run `./scripts/verificar.sh` and `python -m pytest -q server/tests`. In Android with JDK 21 and SDK 35, run `./gradlew testDebugUnitTest assembleRelease`. November 21 baseline on 75c1f35 was 16 MVP, 183 backend, and 154 Android tests. Recheck the current revision; the counts are reference data |
| B1 · Signup, invitations, isolation | Register A and B from scratch. Create identical product codes and debt records for customers of the same name. Invite employee A. Attempt to read and write B’s resources as A via API, jobs, export, and mobile cache. Deny access without balance changes or disclosure of resource existence |
| B2 · QR and device replacement | With two browsers, scan the QR from one, verify the store and visible code, and approve only its session. Test denial, expiry, manual code, same-device access, recovery, and revoked membership. Audit without recording the secret |
| B3 · Banking and money | Use a FakePey fixture labeled SIMULADO with two active IDs, a pending account, and a replacement account. Verify the exact recipient when creating a QR, reconciliation of the previous charge, duplicates, and provider failure. Record the real payment separately as a human-operated scenario |
| B4 · Offline sale and goods receipt | On the physical Android connected to ADB, enable airplane mode, sell the last unit, receive merchandise, close the app, reboot, and reconnect. A second POS sells the same unit. Lose the ACK and retry. Both distinct sales survive. Retries add neither money nor stock |
| B5 · Till close and debt | Use two operators, an opening float, a sale, a count variance, and an accepted handover. Request credit beyond the limit, authorize as owner, record a partial repayment, settle, then export after returning to Gratis. Verify ledger and audit history |
| B6 · Ergonomics | Record phone model and version without its serial number, along with network state and task. Measure tap-to-feedback and action-to-understandable-status. Repeat with enlarged text, TalkBack, bright lighting, and an interruption. Use keyboard and zoom in the browser. Record task, duration, outcome, and observed failures |
| B7 · Business and privacy | Load the SIMULADO fixture, independently recalculate funnel and money, then reset the filter. Simulate withdrawal between preparation and delivery, dominance, and inference by differencing. Verify an allowed, authorized, recorded delivery as well |
| B8 · Recoverable release | Reinstall and upgrade the APK in place with a pending outbox. Rehearse restoring to a separate database and rolling back to a compatible build. Verify SHA and read-only smoke checks after auto-CD. Document measured RPO/RTO |
| B9 · Coordination | A worker’s lease expires after it commits. Another recovers the work without duplicating it. Create a test question, interrupt the worker after notification, and resume. No second automatic notification. Carlos’s answer unblocks only dependent packages |

Each report includes **question, SHA, environment, data, command or steps, expected and observed outcomes, PASS/FAIL/BLOCKED, and a path to sanitized evidence**. Distinguish physical-device, emulator, and second-client tests. For financial operations, compare ledger and server state. A screenshot alone is insufficient. A change to `apply_payment` requires a new test in `server/tests` and notice to the integrator under AGENTS.

## Completion

The integrator lists deployed capabilities, API/APK versions, outstanding approvals, skipped checks, and reasons. Deliver complete user journeys to the owner. Before resuming any package, reconcile the worklog, Git, and existing evidence.
