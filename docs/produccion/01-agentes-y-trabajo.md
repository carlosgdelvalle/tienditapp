# Agent roles, dispatch, and recovery

## Match the team to the dependencies

One Pro coordinator owns contracts and integration. To investigate independent questions, brief reviewers separately and compare their findings afterward. For money, identity, and synchronization, give one agent ownership of the contract and another responsibility for checking it. Published research compares topologies on specific tasks. Measure the optimal concurrency for Abarpay on this machine. [Agent topology study](https://arxiv.org/abs/2512.08296) · [Multi-agent engineering experience](https://www.anthropic.com/engineering/multi-agent-research-system)

| Agent | Input and deliverable | Verification |
|---|---|---|
| Pro coordinator | Dependency graph, frozen contracts, assignments, conflict resolution, integration | Run gates on the integrated SHA and publish the evidence index |
| Pro industrial engineer | Observe the shop environment, design the sequence before coding, document the workflow and how to resume after distraction | Implementer walks through the card, proposes steps to remove, and raises objections with the designer |
| Pro implementer | Changes affecting money, identity, isolation, disclosure, or recovery | A second Pro starts with fresh context and examples derived from the contract |
| Flash implementer | Screens, fixtures, metrics, predesigned migrations, documentation, and bounded checks | Another agent reproduces the result. Flash is suitable for bounded impact |
| Commercial reviewers | Two Pro and two Flash independently assess the same dataset labeled SIMULADO | Coordinator verifies calculations, corrects unit errors, and records remaining disagreement |
| Verifier | Receive the requirement first, write down expected results, then inspect the candidate commit | Report PASS, FAIL, or BLOCKED with reproduction steps and limitations |

To request a peer check, send the coordinator the package ID, SHA, and question. The coordinator dispatches or schedules a session within the concurrency budget. The verifier can ask the author directly about a contract. Both record the specific case. Use a third opinion for a material disagreement with an answerable question. Every review has an owner responsible for the outcome.

The [coordinator prompt](00-EMPIEZA-AQUI.md) defines when to escalate an unresolved critical question from Pro High to an independent Pro Max verifier. Set effort on the intended session and check the effective setting. The bundled profile patches select the model only.

## Start DSH on Arquimedes

The shipped `headless` profile in DSH Desktop 0.2.2-rc.5 included `subagent`, `subagent_fork`, profile patches, stdin input, and resumption by ID. The default profile selected Flash. Specify the model explicitly for each process. From the repo root, with a signed-in session or provider credential provisioned by the operator for the selected mode:

```sh
DSH_BIN="/Applications/DeepSeek Harness.app/Contents/Resources/runtime/cli/bin/dsh"
PLAN_ROOT="$(pwd)/docs/produccion"
"$DSH_BIN" headless --help
"$DSH_BIN" headless --patch "$PLAN_ROOT/perfiles/pro.yml" --permission-mode workspace-write \
  'Follow the coordinator prompt in docs/produccion/00-EMPIEZA-AQUI.md. Use High by default and assign Max only for the verifier escalations specified there.'
```

For a worktree worker, select the [Flash](perfiles/flash.yml) or [Pro](perfiles/pro.yml) patch explicitly. Set `ASSIGNMENT_FILE` to the coordinator’s local assignment file. The CLI reads the assignment from stdin:

```sh
"$DSH_BIN" headless --patch "$PLAN_ROOT/perfiles/flash.yml" --permission-mode workspace-write - < "$ASSIGNMENT_FILE"
```

Resume from the same directory/profile with `--session-id "$DSH_SESSION_ID"`. The coordinator makes the commits if the worker sandbox cannot access the common Git directory. During E0, run a harmless task and verify the **observed** model in the events or interface, the effective directory, and absence of production secrets. Keep raw prompt or environment traces out of Git. Check what model subcalls actually use. When native dispatch cannot select or confirm it, start separate headless processes with the patches. If headless cannot access Desktop credentials, use Desktop sessions with explicit model selection while Carlos provisions profile access. Keep composed configuration and Keychain credentials private.

## Dispatch and exclusive resources

Start with the coordinator and two workers. After two packages, record elapsed and waiting time, rework, memory pressure, and provider limits. Increase to four lightweight workers if accepted work per hour improves. Reduce concurrency when retries or build waits dominate. On the 16 GB Mac, allow one Gradle build, one ADB owner, one migration-sequence writer, and one production deployment at a time. Other workers can build and verify independent subsystems.

Use one worktree per package with a `cdv/<package>` branch based on the contract SHA. Keep the coordinator checkout for the worklog and integration review. Divide `server/main.py`, `db.py`, and console edits by responsibility or schedule them sequentially. Workers sharing a write path wait for the contract or integrator. Preserve diverging work instead of resetting or cleaning it. Each PR includes its Spanish bitácora entry, a Spanish commit message, and a reference to its package.

**Implementer assignment**

> Package / base SHA / accepted dependency / writable paths / initiating event / input / success example / interrupted case / durable result / time and cost budget / test commands / designated verifier. Return the SHA, decisions made, and any outcome still unverified.

**Verifier assignment**

> From the contract, reproduce two ordinary cases, one relevant failure, and resumption where applicable. In a clean checkout inspect the observable before-and-after state. Record commands and environment. Classify differences by impact and return PASS, FAIL, or BLOCKED. Identify evidence that would change the verdict.

**Minimum worklog entry:** package, state (`ready/leased/implemented/verifying/accepted/blocked`), session and branch, assigned agent, base and candidate SHA, last progress time, evidence, and next action. Before reclaiming a lease, check for a running process, uncommitted edits, active verifier, or uncertain external side effect. Recover existing work. After a crash during a charge, email, or push, check its outcome before retrying.

## Escalation

For a decision from Carlos, open an [AskAstra entry](AskAstra.md). The coordinator runs the [notifier](telegram.md). Carlos answers directly or chooses to consult Astra. Update the affected worklog entries and communicate the decision directly to owners and verifiers. Independent packages continue. Track tokens by model, latency, and the proportion of packages reopened to decide whether another review adds value.
