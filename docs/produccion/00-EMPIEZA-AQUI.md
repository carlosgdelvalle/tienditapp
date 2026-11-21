# Abarpay · Start here, Pro coordinator

**Outcome:** A shopkeeper in Mexico can open a store from an Android phone, take payment during a network interruption, reconcile CoDi payments to their own bank account, and manage the store from a browser. Carlos and his team operate the SaaS through a separate console. Delivery includes measurable pilots and reproducible recovery evidence.

## First instruction for DSH

> Read this file and the [work package board](09-paquetes-y-aceptacion.md). Act as the DeepSeek Pro coordinator on Arquimedes. Recover the worklog and compare its revision with Git. Start at E0. Dispatch ready packages and have a separate session verify each implementation. Execute the work and record evidence. When a decision requires Carlos, record the question, notify him, and continue independent work. Carlos alone decides when to consult Astra.

## Working languages

Write agent assignments, designs, implementation instructions, and verification reports in English. Write every interface string in Mexican Spanish, including the Android app, both consoles, the landing page, receipts, email, notifications, and accessibility announcements. In acceptance criteria, describe behavior in English and quote the exact Spanish string the user should see or hear. Use the [English–Mexican Spanish glossary](glossary.md) for workflow terminology. Respect existing Spanish project records, bitácora entries, and commit conventions. Retain established API identifiers, package IDs, paths, and notifier fields.

## First run and resumption

1. On Arquimedes, open the checkout containing **this packet**. The product assessment used `75c1f35` as its baseline. Keep the current checkout and preserve unrelated changes. Read the [project rules](../../AGENTS.md), current decisions, and bitácora. Android and `server/` are the active product. Decision 0005 superseded the earlier MVP in `app/`.
2. Read [agents and worktrees](01-agentes-y-trabajo.md). Check models, the Python environment, and permissions with fictional data. Verify the [direct Telegram notification](telegram.md). If a token, phone, or budget is missing, record the specific dependency in [Carlos’s checklist](../../PendientesCarlos.md) and continue packages that can proceed.
3. Maintain **one** local `docs/worklog.md` in the coordinator checkout. If the clone has none, create it there with the goal, instructions, decisions, owner, statuses, dependencies, and checks. Keep it out of commits. Use `AskAstra.md` in this directory for decisions. Only the coordinator edits the working queue. Workers send their findings to the coordinator.
4. Select a ready row, copy its assignment contract, create a worktree, and appoint a separate verifier. Accept a package when checks pass on the integrated SHA. On restart, recover leases, sessions, branches, and outcomes before calling providers again.
5. Close delivery by running the journeys in the acceptance table. A Trello label, successful build, or configured provider alone cannot demonstrate the business outcome.

## Arquimedes inventory and dependencies

The November 21 SSH check found Apple silicon, 16 GB RAM, over 170 GiB free, Git, Python 3.12 in `.venv`, `uv`, Gitleaks, JDK 21, Android SDK 35/build-tools 35.0.0, ADB, and DSH Desktop 0.2.2-rc.5. The installed CLI resolved both Pro and Flash patches. A live run still needs to verify billing access and the model that actually ran. The machine’s checkout was at `75c1f35` before receiving the packet.

Run these checks from the integration checkout:

```sh
export PATH="$HOME/.local/bin:$HOME/Library/Android/sdk/platform-tools:$PATH"
export JAVA_HOME="$HOME/.local/share/tienditapp/jdk-21/Contents/Home"
export ANDROID_HOME="$HOME/Library/Android/sdk"
source .venv/bin/activate
./scripts/verificar.sh
python -m pytest -q server/tests
adb devices
(cd android && ./gradlew testDebugUnitTest assembleRelease)
```

**New dependency for I1:** a real development PostgreSQL instance and a migration client for diagnostics. The usual PATH entries contained no `psql`, `pg_ctl`, or Docker. Default to local PostgreSQL matching Render’s major version. Install server/client for the test user or use an ephemeral PostgreSQL CI service while preparing the Mac. Keep isolation tests away from production. Git, Actions, and an accessible database suffice; Docker and the GitHub CLI are optional. For G1, provision browser automation and accessibility tools in the project environment. A second session or emulator can serve as the second POS while the physical phone runs acceptance scenarios. Direct Telegram delivery works without OpenClaw.

## Where to find a decision

| Need | Document |
|---|---|
| Domain terms and approved bilingual usage | [Glossary](glossary.md) |
| Identity, isolation, API, migration | [Tenancy](02-contratos-y-tenencia.md) |
| Fewer checkout steps, resuming interrupted work, Trello suggestions | [Ergonomics](03-flujos-y-ergonomia.md) · [Card crosswalk](trello-cobertura.md) |
| Store registration, login QR, CLABE registration, payment collection | [Identity and pey](04-identidad-onboarding-y-pey.md) |
| Offline sale, goods receipt, till close, replenishment, store credit | [Mobile operations](05-caja-offline-e-inventario.md) |
| Public page, APK, commercial experiment | [Landing page and sales](06-landing-y-comercial.md) |
| SaaS operators, indicators, campaigns, data partner | [Platform console](07-consola-saas-y-datos.md) |
| Email, CI, production, releases, backup, rollback | [Operations](08-operacion-y-despliegue.md) |
| Question requiring a decision | [Manual queue](AskAstra.md) · [Telegram](telegram.md) |

## Execution authority

Carlos selected DeepSeek Pro and Flash for this repository and requested CD without routine human approval for each release. Use those two models for the program. The demo decisions on SQLite, PINs, portal-based CLABE registration, and manual deployment require a superseding decision under the steering group’s existing approval procedure. Request one policy transition. Once enabled, a passing integration on main deploys automatically. Keep the active demo isolated during migration.

Obtain approval for the quote before provisioning paid resources. Real partner exports require consent, review, and agreement. A person carries out each live MXN 0.01 payment test. Use fixtures labeled **SIMULADO** until each integration meets its prerequisites. Keep secrets, CLABEs, databases, customer messages, and identifiable commercial data out of model inputs. Check that published evidence contains only safe fixtures. Enable live pilots and signups as each capability is verified.
